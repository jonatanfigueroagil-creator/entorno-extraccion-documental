"""Primer pipeline de punta a punta (S02): leer, normalizar, registrar errores y calcular estadísticas.

Cada etapa es una función con una sola responsabilidad. ``ejecutar_pipeline`` las encadena y devuelve
una tabla con un registro por archivo. Un archivo defectuoso nunca detiene el lote y repetir la corrida
sobre la misma carpeta produce el mismo resultado.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.ingesta.cargador import (
    TIPO_POR_EXTENSION,
    calcular_sha256,
    detectar_formato,
    enviar_a_cuarentena,
    validar_formato_y_extension,
    verificar_apertura,
)
from pipeline_sbs.ingesta.errores import ErrorIngesta, traducir_excepcion
from pipeline_sbs.ingesta.extractores import extraer_texto
from pipeline_sbs.preprocesamiento.normalizacion import normalizar_texto

registro = logging.getLogger(__name__)

FORMATOS_IMAGEN = ("png", "jpg", "tif")
COLUMNAS = ["archivo", "tipo", "formato", "estado", "motivo", "detalle", "paginas", "caracteres", "segundos",
            "requiere_ocr", "sha256", "duplicado_de"]


def _parametros(config: dict[str, Any] | None) -> dict[str, Any]:
    """Une la configuración recibida con la sección ``ingesta`` de ``pipeline.yaml``.

    Args:
        config: valores propios (``cuarentena``, ``umbral_ocr``) que reemplazan a los del YAML.

    Returns:
        Diccionario con ``cuarentena`` y ``umbral_ocr``.
    """
    ingesta = cargar_configuracion()["ingesta"]
    parametros = {
        "cuarentena": ingesta.get("carpeta_cuarentena", "cuarentena"),
        "umbral_ocr": ingesta.get("umbral_ocr_caracteres_por_pagina", 20),
    }
    parametros.update(config or {})
    return parametros


def leer_lote(carpeta: str | Path) -> list[dict[str, Any]]:
    """Etapa 1: abre cada archivo de la carpeta y extrae su texto sin detener el lote.

    Calcula la huella SHA-256, detecta el formato por la firma, valida contra la extensión, comprueba
    que el archivo abre y detecta duplicados por huella. El texto queda sin normalizar (``texto_crudo``).

    Args:
        carpeta: carpeta con los archivos recibidos (sin subcarpetas), leída en orden alfabético.

    Returns:
        Un diccionario por archivo con las columnas de ``COLUMNAS`` y ``texto_crudo``; ``ruta`` conserva
        el archivo original para la cuarentena.

    Raises:
        NotADirectoryError: si la carpeta no existe.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No existe la carpeta: {carpeta}")
    archivos = sorted(p for p in carpeta.iterdir() if p.is_file() and not p.name.startswith("."))
    vistos: dict[str, str] = {}        # huella -> nombre del primer archivo con ese contenido
    registros: list[dict[str, Any]] = []
    for ruta in archivos:
        inicio = time.perf_counter()
        fila: dict[str, Any] = {
            "archivo": ruta.name, "tipo": TIPO_POR_EXTENSION.get(ruta.suffix.lower(), "otro"), "formato": "desconocido",
            "estado": "ok", "motivo": "", "detalle": "", "paginas": 0, "caracteres": 0, "segundos": 0.0,
            "requiere_ocr": False, "sha256": "", "duplicado_de": "", "texto_crudo": "", "ruta": ruta,
        }
        try:
            fila["sha256"] = calcular_sha256(ruta)
            fila["formato"] = detectar_formato(ruta)
            validar_formato_y_extension(ruta, fila["formato"])
            verificar_apertura(ruta, fila["formato"])
            if fila["sha256"] in vistos:
                fila.update(estado="duplicado", motivo="duplicado", duplicado_de=vistos[fila["sha256"]],
                            detalle=f"mismo contenido que {vistos[fila['sha256']]}")
            else:
                extraccion = extraer_texto(ruta, fila["formato"])
                fila.update(texto_crudo=extraccion.texto, paginas=extraccion.paginas)
                vistos[fila["sha256"]] = ruta.name
        except Exception as error:  # noqa: BLE001 - un archivo malo no debe detener el lote
            tipificado = error if isinstance(error, ErrorIngesta) else traducir_excepcion(error)
            detalle = (tipificado.detalle or str(tipificado)).replace(str(ruta), ruta.name)
            fila.update(estado="fallo", motivo=tipificado.motivo, detalle=detalle)
        fila["segundos"] = time.perf_counter() - inicio
        registros.append(fila)
    return registros


def normalizar_lote(registros: list[dict[str, Any]], umbral_ocr: int = 20) -> list[dict[str, Any]]:
    """Etapa 2: normaliza el texto de los archivos ok y decide cuáles requieren OCR.

    Un archivo ok requiere OCR si es una imagen o un PDF con menos de ``umbral_ocr`` caracteres por página.

    Args:
        registros: salida de ``leer_lote``.
        umbral_ocr: caracteres por página por debajo de los cuales un PDF requiere OCR.

    Returns:
        Los mismos registros, con ``texto`` normalizado, ``caracteres`` y ``requiere_ocr`` completos.
    """
    for fila in registros:
        fila["texto"] = ""
        if fila["estado"] != "ok":
            continue
        texto = normalizar_texto(fila["texto_crudo"])
        por_pagina = len(texto) / max(fila["paginas"], 1)
        fila["texto"] = texto
        fila["caracteres"] = len(texto)
        fila["requiere_ocr"] = fila["formato"] in FORMATOS_IMAGEN or (fila["formato"] == "pdf" and por_pagina < umbral_ocr)
    return registros


def registrar_errores(registros: list[dict[str, Any]], cuarentena: str | Path) -> int:
    """Etapa 3: copia los archivos con fallo a la cuarentena y deja un evento por cada uno.

    Escribe además ``registro_errores.jsonl`` (una línea JSON por fallo) dentro de la cuarentena. Es
    idempotente: repetir la etapa reemplaza las copias y el registro.

    Args:
        registros: salida de ``normalizar_lote``.
        cuarentena: carpeta de cuarentena (se crea si hace falta).

    Returns:
        Cantidad de archivos con fallo.
    """
    cuarentena = Path(cuarentena)
    fallos = [fila for fila in registros if fila["estado"] == "fallo"]
    lineas = []
    for fila in fallos:
        try:
            enviar_a_cuarentena(fila["ruta"], cuarentena, fila["motivo"], fila["detalle"])
        except OSError as error:
            registro.error("cuarentena_fallida", extra={"archivo": fila["archivo"], "detalle": str(error)})
        registro.warning("archivo_con_error", extra={"archivo": fila["archivo"], "motivo": fila["motivo"]})
        lineas.append(json.dumps({"archivo": fila["archivo"], "motivo": fila["motivo"], "detalle": fila["detalle"]},
                                 ensure_ascii=False))
    if fallos:
        (cuarentena / "registro_errores.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return len(fallos)


def calcular_estadisticas(tabla: pd.DataFrame) -> pd.DataFrame:
    """Etapa 4: resume el lote por tipo de archivo, con una fila final ``TOTAL``.

    Columnas: n, ok, fallo, duplicado, requiere_ocr y pct_requiere_ocr (solo sobre los archivos ok).

    Args:
        tabla: tabla con un registro por archivo (columnas ``tipo``, ``estado`` y ``requiere_ocr``).

    Returns:
        DataFrame indexado por tipo.
    """
    def resumir(grupo: pd.DataFrame) -> dict[str, Any]:
        ok = int((grupo["estado"] == "ok").sum())
        con_ocr = int(((grupo["estado"] == "ok") & grupo["requiere_ocr"]).sum())
        return {"n": len(grupo), "ok": ok, "fallo": int((grupo["estado"] == "fallo").sum()),
                "duplicado": int((grupo["estado"] == "duplicado").sum()), "requiere_ocr": con_ocr,
                "pct_requiere_ocr": round(100 * con_ocr / ok, 1) if ok else 0.0}

    columnas = ["n", "ok", "fallo", "duplicado", "requiere_ocr", "pct_requiere_ocr"]
    if tabla.empty:
        return pd.DataFrame(columns=columnas)
    filas = {tipo: resumir(grupo) for tipo, grupo in tabla.groupby("tipo", sort=True)}
    filas["TOTAL"] = resumir(tabla)
    return pd.DataFrame.from_dict(filas, orient="index")[columnas]


def ejecutar_pipeline(carpeta: str | Path, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Encadena leer, normalizar, registrar errores y estadísticas sobre una carpeta de archivos.

    Args:
        carpeta: carpeta con el lote (sin subcarpetas).
        config: valores que reemplazan a ``ingesta`` de ``pipeline.yaml``: ``cuarentena`` (carpeta de
            cuarentena) y ``umbral_ocr`` (caracteres por página).

    Returns:
        DataFrame con un registro por archivo (columnas de ``COLUMNAS``). Las estadísticas por tipo
        quedan en ``tabla.attrs["estadisticas"]``.

    Raises:
        NotADirectoryError: si la carpeta no existe.
    """
    parametros = _parametros(config)
    registros = leer_lote(carpeta)
    registros = normalizar_lote(registros, parametros["umbral_ocr"])
    errores = registrar_errores(registros, parametros["cuarentena"])
    tabla = pd.DataFrame([{columna: fila[columna] for columna in COLUMNAS} for fila in registros], columns=COLUMNAS)
    tabla.attrs["estadisticas"] = calcular_estadisticas(tabla)
    registro.info("pipeline_terminado", extra={"archivos": len(tabla), "errores": errores})
    return tabla
