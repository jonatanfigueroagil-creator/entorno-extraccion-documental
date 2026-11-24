"""Ejecución de un lote completo: control en el proceso principal, reparto del trabajo y una cola con un solo escritor.

1. Huella y registro: lo que ya tiene un estado final no se procesa de nuevo (idempotencia).
2. Control en el proceso principal: lo dañado va a cuarentena con su motivo y lo repetido se marca como duplicado.
3. Reparto: en serie o con procesos (``ProcessPoolExecutor``); cada proceso devuelve su resultado y no escribe nada.
4. Cola de escritura: los resultados entran a una ``queue.Queue`` y un solo hilo consumidor los anota en el registro.
"""
from __future__ import annotations

import logging  # solo referencia
import os
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .etapas import ETAPAS
from .registro import a_cuarentena, abrir_registro, anotar_corrida, huella, marcar, reintentar, ya_procesado
from .trabajo import procesar_archivo

FIN = None  # señal que cierra la cola: después de ella el escritor termina
registro_eventos = logging.getLogger(__name__)  # solo referencia


@dataclass
class Resumen:
    """Lo que pasó en una corrida del lote."""

    carpeta: str
    modo: str
    trabajadores: int
    inicio: str = ""
    archivos: int = 0
    saltados: int = 0      # ya tenían un estado final en el registro: no se procesan de nuevo
    ok: int = 0
    cuarentena: int = 0
    duplicados: int = 0
    errores: int = 0
    segundos: float = 0.0
    segundos_por_etapa: dict[str, float] = field(default_factory=dict)
    escritos: int = 0      # resultados que el escritor anotó en el registro
    max_en_cola: int = 0   # el mayor número de resultados que esperaron a la vez en la cola
    resultados: list[dict[str, Any]] = field(default_factory=list)

    @property
    def documentos_por_minuto(self) -> float:
        """Archivos atendidos en esta corrida (sin los saltados) por minuto."""
        return round((self.archivos - self.saltados) / self.segundos * 60, 1) if self.segundos else 0.0

    def como_fila(self) -> dict[str, Any]:
        """La corrida en una fila, para una tabla o para la tabla ``corridas``."""
        return {"inicio": self.inicio, "modo": self.modo, "trabajadores": self.trabajadores, "archivos": self.archivos, "saltados": self.saltados,
                "ok": self.ok, "cuarentena": self.cuarentena, "duplicados": self.duplicados, "errores": self.errores,
                "segundos": round(self.segundos, 1), "documentos_por_minuto": self.documentos_por_minuto}


def tipo_de(nombre: str, cfg: Config) -> str:
    """Tipo de documento según el prefijo del nombre (``POL-0001.pdf`` -> ``poliza``), con la tabla del YAML; vacío si no figura."""
    return cfg.orquestacion.tipo_por_prefijo.get(nombre.split("-")[0].upper(), "")


def _escritor(cola: queue.Queue, con: Any, resumen: Resumen) -> None:
    """El hilo consumidor: saca los resultados de la cola, uno por uno, y es el único que escribe en el registro."""
    while (resultado := cola.get()) is not FIN:
        marcar(con, resultado["sha256"], resultado["archivo"], resultado["estado"], resultado.get("motivo", ""),
               resultado.get("intentos", 1), resultado.get("segundos_total", 0.0))
        resumen.escritos += 1
        for etapa, segundos in resultado.get("segundos", {}).items():  # solo referencia
            registro_eventos.info("etapa", extra={"componente": "lote", "archivo": resultado["archivo"], "etapa": etapa,  # solo referencia
                                                  "estado": resultado["estado"], "segundos": segundos})  # solo referencia


def ejecutar_lote(carpeta: str | Path, cfg: Config, avisar: Callable[[str], None] | None = None) -> Resumen:
    """Procesa todos los archivos de una carpeta según la configuración y deja el registro al día.

    Args:
        carpeta: carpeta con los archivos recibidos (sin subcarpetas).
        cfg: configuración validada; ``orquestacion.modo`` (``secuencial`` o ``procesos``) y ``trabajadores`` deciden el reparto.
        avisar: función que recibe los mensajes de avance (por ejemplo ``print``); sin ella, la corrida es silenciosa.

    Returns:
        Un ``Resumen`` con los conteos por estado, los segundos, los documentos por minuto, el tiempo por etapa y los resultados.
    """
    avisar = avisar or (lambda mensaje: None)
    orq = cfg.orquestacion
    resumen = Resumen(carpeta=Path(carpeta).name, modo=orq.modo, trabajadores=orq.trabajadores if orq.modo == "procesos" else 1,
                      inicio=datetime.now().isoformat(timespec="seconds"))
    inicio = time.perf_counter()
    archivos = sorted(ruta for ruta in Path(carpeta).iterdir() if ruta.is_file() and not ruta.name.startswith("."))
    resumen.archivos = len(archivos)
    con = abrir_registro(cfg.almacenamiento.duckdb)

    # 1. Huella y registro: lo ya procesado se salta
    por_hacer = []
    for ruta in archivos:
        sha256, _ = reintentar(lambda: huella(ruta), cfg.reintentos.intentos, cfg.reintentos.espera_s)
        if ya_procesado(con, sha256):
            resumen.saltados += 1
        else:
            por_hacer.append((ruta, sha256))
    avisar(f"Archivos: {resumen.archivos} | ya procesados: {resumen.saltados} | por procesar: {len(por_hacer)}")

    # La cola de escritura y su único consumidor
    cola: queue.Queue = queue.Queue()
    escritor = threading.Thread(target=_escritor, args=(cola, con, resumen), name="escritor")
    escritor.start()

    def entregar(resultado: dict[str, Any]) -> None:
        """Pone un resultado en la cola y lo cuenta."""
        resumen.resultados.append(resultado)
        cola.put(resultado)
        resumen.max_en_cola = max(resumen.max_en_cola, cola.qsize())
        for etapa, segundos in resultado.get("segundos", {}).items():
            resumen.segundos_por_etapa[etapa] = resumen.segundos_por_etapa.get(etapa, 0.0) + segundos

    try:
        # 2. Control en el proceso principal: cuarentena y duplicados, antes de repartir
        vistos: dict[str, str] = {}
        aceptados = []
        for ruta, sha256 in por_hacer:
            previo = {"ruta": str(ruta), "archivo": ruta.name, "tipo": tipo_de(ruta.name, cfg), "sha256": sha256, "formato": "", "estado": "ok", "motivo": ""}
            medido = time.perf_counter()
            if "control" in orq.etapas:
                previo, _ = reintentar(lambda: ETAPAS["control"].funcion(previo, cfg), cfg.reintentos.intentos, cfg.reintentos.espera_s)
            previo["segundos"] = {"control": round(time.perf_counter() - medido, 4)}
            previo.pop("ruta")
            if previo["estado"] == "cuarentena":
                a_cuarentena(ruta, cfg.cuarentena.carpeta, previo["motivo"], previo.get("detalle", ""))
                entregar(previo)
            elif sha256 in vistos:
                entregar({**previo, "estado": "duplicado", "motivo": f"mismo contenido que {vistos[sha256]}"})
            else:
                vistos[sha256] = ruta.name
                aceptados.append((ruta, previo))
        avisar(f"Control: {len(aceptados)} aceptados | {len(por_hacer) - len(aceptados)} apartados (cuarentena o duplicado)")

        # 3. Reparto: las etapas que siguen al control, en serie o con procesos
        sin_control = cfg.con(etapas=[etapa for etapa in orq.etapas if etapa != "control"])
        hechos = 0

        def recibir(previo: dict[str, Any], resultado: dict[str, Any]) -> None:
            nonlocal hechos
            entregar({**previo, **resultado, "segundos": {**previo["segundos"], **resultado.get("segundos", {})}})
            hechos += 1
            if hechos % 25 == 0 or hechos == len(aceptados):
                avisar(f"  {hechos} de {len(aceptados)} | esperan en la cola: {cola.qsize()}")

        os.environ["OMP_THREAD_LIMIT"] = "1"  # un hilo de Tesseract por página: el reparto lo hacen los procesos, no Tesseract
        if orq.modo == "secuencial":
            for ruta, previo in aceptados:
                recibir(previo, procesar_archivo(ruta, previo["tipo"], sin_control))
        else:
            with ProcessPoolExecutor(max_workers=orq.trabajadores) as grupo:
                futuros = {grupo.submit(procesar_archivo, str(ruta), previo["tipo"], sin_control): previo for ruta, previo in aceptados}
                for futuro in as_completed(futuros):
                    try:
                        resultado = futuro.result()
                    except Exception as error:  # noqa: BLE001 - un proceso caído no detiene el lote
                        resultado = {"estado": "error", "motivo": "proceso_caido", "detalle": f"{type(error).__name__}: {error}"[:300]}
                    recibir(futuros[futuro], resultado)
    finally:
        # 4. Se cierra la cola: el escritor termina lo que falta y recién entonces se sigue
        cola.put(FIN)
        escritor.join()

    resumen.resultados.sort(key=lambda r: r["archivo"])
    for estado, contador in (("ok", "ok"), ("cuarentena", "cuarentena"), ("duplicado", "duplicados"), ("error", "errores")):
        setattr(resumen, contador, sum(r["estado"] == estado for r in resumen.resultados))
    resumen.segundos_por_etapa = {etapa: round(segundos, 1) for etapa, segundos in resumen.segundos_por_etapa.items()}
    resumen.segundos = time.perf_counter() - inicio
    anotar_corrida(con, resumen.como_fila())
    con.close()
    avisar(f"Listo en {resumen.segundos:.1f} s | {resumen.documentos_por_minuto} documentos por minuto | escritos por la cola: {resumen.escritos}")
    return resumen
