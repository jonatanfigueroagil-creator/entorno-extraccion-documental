"""Registro (logging) del pipeline. En S01 el formato es simple; el formato JSON llega en S02."""
from __future__ import annotations

import logging

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def obtener_logger(nombre: str, nivel: str = "INFO") -> logging.Logger:
    """Devuelve un logger con formato simple a la consola, sin duplicar manejadores.

    Args:
        nombre: nombre del logger (normalmente ``__name__``).
        nivel: nivel mínimo ("DEBUG", "INFO", "WARNING" o "ERROR").

    Returns:
        Logger configurado.

    Raises:
        ValueError: si el nivel no existe.
    """
    numero = logging.getLevelName(nivel.upper())
    if not isinstance(numero, int):
        raise ValueError(f"Nivel de logging desconocido: {nivel}")
    logger = logging.getLogger(nombre)
    logger.setLevel(numero)
    if not any(getattr(h, "_pipeline_sbs", False) for h in logger.handlers):
        manejador = logging.StreamHandler()
        manejador.setFormatter(logging.Formatter(FORMATO))
        manejador._pipeline_sbs = True  # type: ignore[attr-defined]
        logger.addHandler(manejador)
    return logger
