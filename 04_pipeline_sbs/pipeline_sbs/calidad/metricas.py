"""Métricas para medir el OCR: tasa de error de caracteres (CER) e intersección dividida entre unión (IoU)."""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz.distance import Levenshtein


def _limpiar(texto: str) -> str:
    """Unifica la escritura de las tildes, junta los espacios y recorta los extremos."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", texto)).strip()


def cer(referencia: str, hipotesis: str) -> float:
    """Tasa de error de caracteres: ediciones necesarias / largo de la referencia.

    Args:
        referencia: texto correcto.
        hipotesis: texto que leyó el OCR.

    Returns:
        0.0 si son iguales; puede superar 1.0 si el OCR inventa mucho texto.
        Con referencia vacía: 0.0 si la hipótesis también es vacía y 1.0 si no.
    """
    referencia, hipotesis = _limpiar(referencia), _limpiar(hipotesis)
    if not referencia:
        return 0.0 if not hipotesis else 1.0
    return Levenshtein.distance(referencia, hipotesis) / len(referencia)


def iou(caja_a: tuple[float, float, float, float], caja_b: tuple[float, float, float, float]) -> float:
    """Intersección dividida entre unión de dos cajas ``(x1, y1, x2, y2)``: 1.0 = coinciden; 0.0 = no se tocan."""
    x1, y1 = max(caja_a[0], caja_b[0]), max(caja_a[1], caja_b[1])
    x2, y2 = min(caja_a[2], caja_b[2]), min(caja_a[3], caja_b[3])
    interseccion = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (caja_a[2] - caja_a[0]) * (caja_a[3] - caja_a[1])
    area_b = (caja_b[2] - caja_b[0]) * (caja_b[3] - caja_b[1])
    union = area_a + area_b - interseccion
    return interseccion / union if union > 0 else 0.0
