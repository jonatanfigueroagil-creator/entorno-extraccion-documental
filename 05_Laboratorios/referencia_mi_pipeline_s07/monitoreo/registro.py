"""Registro (logging) del pipeline: el libro de actas de cada corrida.

S01: formato simple. S02: formato JSON, un evento por línea. S07: datos personales enmascarados (correo, CCI, RUC, cuenta,
teléfono y DNI), claves sensibles y secretos ocultos, y la versión del código que produjo cada resultado.
El registro dice qué pasó con cada documento, pero nunca escribe sus datos: solo cuántos campos quedaron llenos o vacíos.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Atributos que todo LogRecord trae: lo que no esté aquí vino de ``extra={...}`` y se agrega al evento.
_ATRIBUTOS_ESTANDAR = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime", "taskName"}
_RE_DNI = re.compile(r"(?<!\d)(\d{6})(\d{2})(?!\d)")
OCULTO = "[OCULTO]"

# S07: patrones en este orden, del más largo al más corto, para que un RUC no se lea como DNI ni un CCI como RUC
PATRONES: list[tuple[str, re.Pattern, Any]] = [
    ("correo", re.compile(r"\b([\w.+-])[\w.+-]*@([\w-]+(?:\.[\w-]+)+)"), lambda m: f"{m[1]}***@{m[2]}"),
    ("cci", re.compile(r"(?<!\d)\d{16}(\d{4})(?!\d)"), lambda m: "*" * 16 + m[1]),
    ("ruc", re.compile(r"(?<!\d)(?:10|15|17|20)\d{7}(\d{2})(?!\d)"), lambda m: "*" * 9 + m[1]),
    ("cuenta", re.compile(r"(?<!\d)(\d{3})-\d{6}(\d{4})(?!\d)"), lambda m: f"{m[1]}-******{m[2]}"),
    ("telefono", re.compile(r"(?<!\d)9\d{2} \d{3} (\d{3})(?!\d)"), lambda m: f"*** *** {m[1]}"),
    ("dni", _RE_DNI, lambda m: "******" + m[2]),
]
# Claves cuyo valor nunca se escribe: datos de personas y secretos
CLAVES_SENSIBLES = ("dni", "ruc", "correo", "telefono", "cuenta", "cci", "cliente", "asegurado", "beneficiario", "nombre",
                    "titular", "depositante", "firmante")
PALABRAS_SECRETAS = ("clave", "key", "token", "password", "secret", "contrasena")
_SECRETOS: set[str] = set()   # valores de secretos leídos en esta corrida: si aparecen en un texto, se ocultan
CLAVES_TECNICAS = {"sha256", "corrida_id", "version", "config_sha"}   # huellas e identificadores: se escriben tal cual


def enmascarar_dni(texto: str) -> str:
    """Oculta los 6 primeros dígitos de todo número de 8 dígitos (posible DNI): ``99386133`` -> ``******33``."""
    return _RE_DNI.sub(lambda m: "******" + m.group(2), texto)


def ocultar_valor(valor: str) -> None:
    """Anota el valor de un secreto: desde ahora, si aparece en un evento, sale como ``[OCULTO]``."""
    if valor and len(valor) >= 4:
        _SECRETOS.add(valor)


def clave_sensible(clave: str) -> bool:
    """True si la clave nombra un dato personal (``dni``, ``cuenta_destino``…) o un secreto (``api_key``, ``token``…)."""
    c = clave.lower()
    personal = any(c == s or c.startswith(s + "_") or c.endswith("_" + s) for s in CLAVES_SENSIBLES)
    return personal or any(p in c for p in PALABRAS_SECRETAS)


def enmascarar_texto(texto: str) -> str:
    """Aplica los patrones en orden: correo, CCI, RUC, cuenta, teléfono y DNI. Los secretos conocidos salen como ``[OCULTO]``."""
    for secreto in _SECRETOS:
        texto = texto.replace(secreto, OCULTO)
    for _nombre, patron, reemplazo in PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto


def enmascarar(valor: Any) -> Any:
    """Recorre textos, diccionarios, listas y tuplas: enmascara los textos y oculta el valor de las claves sensibles."""
    if isinstance(valor, str):
        return enmascarar_texto(valor)
    if isinstance(valor, dict):
        return {k: OCULTO if clave_sensible(str(k)) else enmascarar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [enmascarar(v) for v in valor]
    return valor


class FormateadorJson(logging.Formatter):
    """Convierte cada evento de logging en una línea JSON con ``json.dumps``, ya enmascarada.

    Campos fijos: ``ts`` (UTC, ISO 8601), ``nivel``, ``logger`` y ``mensaje``. Los campos de ``extra={...}`` se agregan
    después de enmascararlos; el valor de una clave sensible (``dni``, ``ruc``, ``api_key``…) sale como ``[OCULTO]``.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Devuelve el evento como una línea JSON (sin saltos de línea: ``json.dumps`` los escapa)."""
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": enmascarar_texto(record.getMessage()),
        }
        for clave, valor in vars(record).items():
            if clave in _ATRIBUTOS_ESTANDAR or clave.startswith("_"):
                continue
            if clave in CLAVES_TECNICAS:
                evento[clave] = valor
            else:
                evento[clave] = OCULTO if clave_sensible(clave) else enmascarar(valor)
        if record.exc_info:
            evento["excepcion"] = enmascarar_texto(self.formatException(record.exc_info))
        return json.dumps(evento, ensure_ascii=False, default=str)


def obtener_logger(nombre: str, nivel: str = "INFO", formato: str = "simple") -> logging.Logger:
    """Devuelve un logger con salida a la consola, sin duplicar manejadores.

    Args:
        nombre: nombre del logger (normalmente ``__name__``).
        nivel: nivel mínimo ("DEBUG", "INFO", "WARNING" o "ERROR").
        formato: "simple" (texto) o "json" (una línea JSON por evento).

    Returns:
        Logger configurado.

    Raises:
        ValueError: si el nivel o el formato no existen.
    """
    numero = logging.getLevelName(nivel.upper())
    if not isinstance(numero, int):
        raise ValueError(f"Nivel de logging desconocido: {nivel}")
    if formato not in ("simple", "json"):
        raise ValueError(f"Formato de logging desconocido: {formato}")
    logger = logging.getLogger(nombre)
    logger.setLevel(numero)
    formateador = FormateadorJson() if formato == "json" else logging.Formatter(FORMATO)
    manejadores = [h for h in logger.handlers if getattr(h, "_pipeline_sbs", False)]
    if manejadores:
        for manejador in manejadores:
            manejador.setFormatter(formateador)
    else:
        manejador = logging.StreamHandler()
        manejador.setFormatter(formateador)
        manejador._pipeline_sbs = True  # type: ignore[attr-defined]
        logger.addHandler(manejador)
    return logger


# ------------------------------------------------------------------------------------------------ S07: el libro de actas
def version_git() -> str:
    """Qué versión del código corre: ``git describe --tags --always --dirty`` (``s07-v1-2-g1a2b3c4-dirty``).

    Dentro de un contenedor no hay Git: se usa la variable ``MI_PIPELINE_VERSION`` que fija la construcción. Sin Git ni
    variable, la versión del paquete instalado.
    """
    if os.environ.get("MI_PIPELINE_VERSION"):
        return os.environ["MI_PIPELINE_VERSION"]
    try:
        corrida = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=10)
        if corrida.returncode == 0 and corrida.stdout.strip():
            return corrida.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    from .. import __version__

    return f"paquete-{__version__}"


def abrir_registro(ruta: str | Path | None, consola: bool = False) -> logging.Logger:
    """Logger del libro de actas: una línea JSON por evento en ``ruta`` (se agrega al final) y, si se pide, en la consola.

    Args:
        ruta: archivo ``registro.jsonl``; ``None`` escribe solo en la consola.
        consola: además, cada evento sale por la salida de errores (la consola, o el registro de un contenedor).
    """
    logger = logging.getLogger(f"{__name__}.actas")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    cerrar_registro(logger)
    destinos: list[logging.Handler] = []
    if ruta is not None:
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        destinos.append(logging.FileHandler(ruta, mode="a", encoding="utf-8"))
    if consola or ruta is None:
        destinos.append(logging.StreamHandler(sys.stderr))
    for manejador in destinos:
        manejador.setFormatter(FormateadorJson())
        logger.addHandler(manejador)
    return logger


def cerrar_registro(logger: logging.Logger) -> None:
    """Cierra los archivos del registro (en Windows, un archivo abierto no se puede mover ni borrar)."""
    for manejador in list(logger.handlers):
        manejador.close()
        logger.removeHandler(manejador)


def evento_documento(resultado: dict[str, Any], umbral_confianza: float) -> dict[str, Any]:
    """El evento de un documento: qué pasó, cuánto tardó y cuán completo quedó. Nunca lleva los valores de los campos.

    ``confianza`` es la proporción de campos llenos sin ambigüedad; por debajo del umbral, el documento va a ``revisar``.
    Las causas de revisión que trae el resultado (por ejemplo ``texto_insuficiente``) se conservan.
    """
    estado = resultado.get("estado", "error")
    nombre = {"ok": "documento_procesado", "duplicado": "documento_duplicado"}.get(estado, "documento_fallido")
    campos = resultado.get("campos") or {}
    nulos = sum(valor is None for valor in campos.values())
    evento: dict[str, Any] = {"evento": nombre, "archivo": resultado.get("archivo", ""), "sha256": str(resultado.get("sha256", ""))[:16],
                              "tipo": resultado.get("tipo", ""), "estado": estado, "segundos": resultado.get("segundos_total")}
    if nombre == "documento_fallido":
        detalle = str(resultado.get("detalle", ""))
        evento.update(error=resultado.get("motivo", "desconocido"), excepcion=detalle.split(":")[0] if ":" in detalle else "", detalle=detalle[:200])
        return evento
    if nombre == "documento_duplicado":
        return evento
    confianza = round((len(campos) - nulos - len(resultado.get("ambiguos", []))) / len(campos), 3) if campos else None
    causas = list(resultado.get("causas_revision", []))
    if confianza is not None and confianza < umbral_confianza and "confianza_baja" not in causas:
        causas.append("confianza_baja")
    evento.update(paginas=resultado.get("paginas"), paginas_ocr=resultado.get("paginas_ocr", 0), caracteres=resultado.get("caracteres", 0),
                  campos=len(campos), campos_nulos=nulos, confianza=confianza, ruta="revisar" if causas else "aceptar", causas_revision=causas)
    return evento


def huella_config(cfg: Any) -> str:
    """Huella corta de la configuración usada: si alguien cambia el YAML sin avisar, la huella cambia."""
    datos = cfg.model_dump(mode="json") if hasattr(cfg, "model_dump") else cfg
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def ejecutar_registrado(entrada: str | Path, cfg: Any, ruta_registro: str | Path | None, avisar: Any = None, consola: bool = False) -> Any:
    """Corre el lote de S06 y deja constancia en el libro de actas: inicio, un evento por documento y fin.

    Args:
        entrada: carpeta con los archivos recibidos.
        cfg: configuración validada (``cargar_config``).
        ruta_registro: archivo ``registro.jsonl`` (se agrega al final: el libro no se borra).
        avisar: función para los mensajes de avance (por ejemplo ``print``).
        consola: además, cada evento sale por la consola.

    Returns:
        El ``Resumen`` del lote, con ``corrida_id`` agregado.
    """
    from ..orquestacion.lote import ejecutar_lote

    logger = abrir_registro(ruta_registro, consola)
    corrida = uuid.uuid4().hex[:12]
    umbral = float(((getattr(cfg, "calidad", None) or {}).get("umbral_score", 0.85)))
    try:
        orq = cfg.orquestacion
        logger.info("corrida_inicio", extra={"evento": "corrida_inicio", "corrida_id": corrida, "version": version_git(),
                                             "config_sha": huella_config(cfg), "entrada": Path(entrada).name, "modo": orq.modo,
                                             "trabajadores": orq.trabajadores, "etapas": list(orq.etapas), "operador": getpass.getuser()})
        resumen = ejecutar_lote(entrada, cfg, avisar=avisar)
        for resultado in resumen.resultados:
            evento = evento_documento(resultado, umbral)
            nivel = logging.WARNING if evento["evento"] == "documento_fallido" else logging.INFO
            logger.log(nivel, evento["evento"], extra={"corrida_id": corrida, **evento})
        logger.info("corrida_fin", extra={"evento": "corrida_fin", "corrida_id": corrida, "archivos": resumen.archivos,
                                          "saltados": resumen.saltados, "ok": resumen.ok, "cuarentena": resumen.cuarentena,
                                          "duplicados": resumen.duplicados, "errores": resumen.errores, "segundos": round(resumen.segundos, 2)})
    finally:
        cerrar_registro(logger)
    resumen.corrida_id = corrida
    return resumen
