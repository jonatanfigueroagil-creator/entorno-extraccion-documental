"""Lectura de una imagen con Tesseract, con la confianza de cada palabra."""
from __future__ import annotations

import numpy as np
import pytesseract


def leer_con_confianza(imagen: np.ndarray, lang: str = "spa", oem: int = 1, psm: int = 6) -> dict:
    """Lee el texto de la imagen y mide qué tan seguro está Tesseract de cada palabra.

    Args:
        imagen: imagen en gris, binaria o RGB.
        lang: idioma de Tesseract ("spa" = español).
        oem: motor (1 = red neuronal LSTM).
        psm: modo de segmentación (6 = un bloque uniforme de texto; 3 = página con varias zonas).

    Returns:
        Diccionario con ``texto`` (con saltos de línea), ``palabras`` (lista con ``texto``, ``conf`` de 0 a 100
        y ``caja`` = (x1, y1, x2, y2)) y ``confianza`` (promedio de 0 a 1; 0.0 si no leyó nada).
    """
    datos = pytesseract.image_to_data(
        imagen, lang=lang, config=f"--oem {oem} --psm {psm}", output_type=pytesseract.Output.DICT
    )
    palabras, lineas = [], {}
    for i, texto in enumerate(datos["text"]):
        if float(datos["conf"][i]) < 0 or not texto.strip():
            continue
        x, y, ancho, alto = datos["left"][i], datos["top"][i], datos["width"][i], datos["height"][i]
        palabras.append({"texto": texto, "conf": float(datos["conf"][i]), "caja": (x, y, x + ancho, y + alto)})
        lineas.setdefault((datos["block_num"][i], datos["par_num"][i], datos["line_num"][i]), []).append(texto)
    confianza = sum(p["conf"] for p in palabras) / len(palabras) / 100 if palabras else 0.0
    texto_total = "\n".join(" ".join(partes) for partes in lineas.values())
    return {"texto": texto_total, "palabras": palabras, "confianza": confianza}
