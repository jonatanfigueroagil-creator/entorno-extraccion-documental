"""Registro (logging) del pipeline: formato simple (S01) y formato JSON, un evento por línea (desde S02)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Atributos que todo LogRecord trae: lo que no esté aquí vino de ``extra={...}`` y se agrega al evento.
_ATRIBUTOS_ESTANDAR = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime", "taskName"}
_RE_DNI = re.compile(r"(?<!\d)(\d{6})(\d{2})(?!\d)")


def enmascarar_dni(texto: str) -> str:
    """Oculta los 6 primeros dígitos de todo número de 8 dígitos (posible DNI): ``99386133`` -> ``******33``.

    Args:
        texto: cadena que puede contener un DNI.

    Returns:
        Cadena con los números de 8 dígitos enmascarados.
    """
    return _RE_DNI.sub(lambda m: "******" + m.group(2), texto)


class FormateadorJson(logging.Formatter):
    """Convierte cada evento de logging en una línea JSON con ``json.dumps``.

    Campos fijos: ``ts`` (UTC, ISO 8601), ``nivel``, ``logger`` y ``mensaje``. Los campos de ``extra={...}``
    (por ejemplo ``archivo``, ``estado``, ``motivo``, ``formato``, ``segundos``) se agregan tal cual.
    Si el mensaje o algún texto contiene un DNI, se enmascara.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Devuelve el evento como una línea JSON (sin saltos de línea)."""
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": enmascarar_dni(record.getMessage()),
        }
        for clave, valor in vars(record).items():
            if clave in _ATRIBUTOS_ESTANDAR or clave.startswith("_"):
                continue
            evento[clave] = enmascarar_dni(valor) if isinstance(valor, str) else valor
        if record.exc_info:
            evento["excepcion"] = enmascarar_dni(self.formatException(record.exc_info))
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
