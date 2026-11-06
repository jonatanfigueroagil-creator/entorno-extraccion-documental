"""Convierte la página de un PDF en una imagen (arreglo de NumPy) lista para el OCR."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf


def pdf_a_imagen(ruta: str | Path, pagina: int = 0, dpi: int = 300) -> np.ndarray:
    """Dibuja una página de un PDF como imagen RGB.

    Args:
        ruta: archivo PDF.
        pagina: número de página, desde 0.
        dpi: resolución; Tesseract rinde mejor con 300 o más.

    Returns:
        Arreglo de alto x ancho x 3: números de 0 a 255 por color (rojo, verde, azul).

    Raises:
        FileNotFoundError: si el PDF no existe.
        IndexError: si la página no existe.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el PDF: {ruta}")
    with pymupdf.open(str(ruta)) as documento:
        if not 0 <= pagina < len(documento):
            raise IndexError(f"El PDF tiene {len(documento)} páginas; se pidió la {pagina}")
        pix = documento[pagina].get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
