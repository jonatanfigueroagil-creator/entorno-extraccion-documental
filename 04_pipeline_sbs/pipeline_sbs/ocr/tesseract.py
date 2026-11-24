"""OCR con Tesseract: texto a partir de una imagen."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytesseract
from PIL import Image


class TesseractNoDisponibleError(RuntimeError):
    """El programa Tesseract no está instalado o no está en el PATH."""


def ocr_imagen(ruta: str | Path, idioma: str = "spa") -> str:
    """Extrae el texto de una imagen con Tesseract.

    Args:
        ruta: imagen (PNG, JPG, TIFF...). Un PDF escaneado debe convertirse antes a imagen.
        idioma: código de idioma de Tesseract; "spa" para español.

    Returns:
        Texto reconocido.

    Raises:
        FileNotFoundError: si la imagen no existe.
        TesseractNoDisponibleError: si el programa Tesseract no está instalado.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe la imagen: {ruta}")
    if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None:
        raise TesseractNoDisponibleError(
            "El programa tesseract no está en el PATH: el participante avisa al docente o indica la ruta de tesseract.exe "
            "en pytesseract.pytesseract.tesseract_cmd."
        )
    with Image.open(ruta) as imagen:
        return pytesseract.image_to_string(imagen, lang=idioma)
