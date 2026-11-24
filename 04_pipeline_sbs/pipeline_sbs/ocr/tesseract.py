"""OCR con Tesseract: texto a partir de una imagen."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytesseract
from PIL import Image


class TesseractNoDisponibleError(RuntimeError):
    """El programa Tesseract no está instalado o no está en el PATH."""

# Aquí se exporta la función del LAB (ocr_imagen).
