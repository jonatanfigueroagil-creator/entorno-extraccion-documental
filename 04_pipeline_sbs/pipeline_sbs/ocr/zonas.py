"""Zonas de la página por coordenadas: encabezado, cuerpo y pie como fracciones de la altura."""
from __future__ import annotations

import numpy as np

ZONAS = {"encabezado": (0.0, 0.22), "cuerpo": (0.22, 0.88), "pie": (0.88, 1.0)}


def recortar_zona(imagen: np.ndarray, desde: float, hasta: float) -> np.ndarray:
    """Recorta una franja horizontal de la página.

    Args:
        imagen: página en gris o RGB.
        desde: inicio de la franja, como fracción de la altura (0.0 = borde superior).
        hasta: fin de la franja, como fracción de la altura (1.0 = borde inferior).

    Returns:
        La franja recortada (una vista de la imagen original).

    Raises:
        ValueError: si no se cumple 0 <= desde < hasta <= 1.
    """
    if not 0.0 <= desde < hasta <= 1.0:
        raise ValueError(f"Fracciones inválidas: desde={desde}, hasta={hasta}")
    alto = imagen.shape[0]
    return imagen[int(alto * desde): int(alto * hasta)]


def zonas_de_pagina(imagen: np.ndarray) -> dict[str, np.ndarray]:
    """Separa la página en encabezado, cuerpo y pie según ``ZONAS``."""
    return {nombre: recortar_zona(imagen, desde, hasta) for nombre, (desde, hasta) in ZONAS.items()}
