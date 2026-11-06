"""Lectura de la configuración YAML del pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

RUTA_POR_DEFECTO = Path(__file__).with_name("pipeline.yaml")

CLAVES_OBLIGATORIAS: tuple[tuple[str, str], ...] = (
    ("ocr", "idioma"),
    ("ingesta", "extensiones"),
    ("llm", "backend"),
    ("logging", "nivel"),
)


def cargar_configuracion(ruta: str | Path | None = None) -> dict[str, Any]:
    """Lee el archivo YAML de configuración y valida las claves obligatorias.

    Args:
        ruta: archivo YAML. Si es None se usa el pipeline.yaml incluido en el paquete.

    Returns:
        Diccionario con la configuración (por ejemplo ``cfg["ocr"]["idioma"] == "spa"``).

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si el YAML no es un mapa o falta alguna clave obligatoria.
    """
    archivo = Path(ruta) if ruta is not None else RUTA_POR_DEFECTO
    if not archivo.is_file():
        raise FileNotFoundError(f"No existe el archivo de configuración: {archivo}")
    with archivo.open(encoding="utf-8") as f:
        datos = yaml.safe_load(f)
    if not isinstance(datos, dict):
        raise ValueError(f"La configuración debe ser un mapa YAML: {archivo}")
    for seccion, clave in CLAVES_OBLIGATORIAS:
        if not isinstance(datos.get(seccion), dict) or clave not in datos[seccion]:
            raise ValueError(f"Falta la clave obligatoria '{seccion}.{clave}' en {archivo}")
    return datos
