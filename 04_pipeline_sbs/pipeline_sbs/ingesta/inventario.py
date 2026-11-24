"""Inventario de documentos: qué llegó, de qué tipo es y si necesita OCR."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pypdf

from pipeline_sbs.documento import Documento

registro = logging.getLogger(__name__)


def tiene_capa_texto(ruta: str | Path, minimo_caracteres: int = 20) -> bool:
    """Indica si un PDF trae texto seleccionable (capa de texto) en alguna página.

    Args:
        ruta: ruta del archivo PDF.
        minimo_caracteres: caracteres (sin espacios en los extremos) para considerar que hay texto.

    Returns:
        True si alguna página tiene al menos ``minimo_caracteres``; False si es una imagen.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si el archivo no es un PDF.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    if ruta.suffix.lower() != ".pdf":
        raise ValueError(f"tiene_capa_texto solo revisa PDF: {ruta.name}")
    lector = pypdf.PdfReader(str(ruta))
    for pagina in lector.pages:
        if len((pagina.extract_text() or "").strip()) >= minimo_caracteres:
            return True
    return False


def inventariar(carpeta: str | Path) -> list[Documento]:
    """Recorre una carpeta (sin subcarpetas) y devuelve una ficha por archivo, ordenada por nombre.

    Un PDF dañado no detiene el inventario: se registra una advertencia y se
    devuelve con 0 páginas y sin capa de texto.

    Args:
        carpeta: carpeta con los archivos recibidos.

    Returns:
        Lista de Documento.

    Raises:
        NotADirectoryError: si la carpeta no existe.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No existe la carpeta: {carpeta}")
    familias = {".pdf": "pdf", ".png": "imagen", ".jpg": "imagen", ".jpeg": "imagen", ".tif": "imagen",
                ".eml": "correo", ".docx": "word", ".html": "html"}
    fichas: list[Documento] = []
    for ruta in sorted(p for p in carpeta.iterdir() if p.is_file()):
        extension = ruta.suffix.lower()
        paginas, con_texto = 0, False
        if extension == ".pdf":
            try:
                paginas = len(pypdf.PdfReader(str(ruta)).pages)
                con_texto = tiene_capa_texto(ruta)
            except Exception as error:  # PDF dañado: se informa y se sigue
                registro.warning("PDF ilegible %s: %s", ruta.name, error)
        elif familias.get(extension) == "imagen":
            paginas = 1
        elif familias.get(extension) in ("correo", "word", "html"):
            con_texto = True
        fichas.append(Documento(
            ruta=str(ruta),
            tipo=familias.get(extension, "otro"),
            extension=extension,
            paginas=paginas,
            tiene_capa_texto=con_texto,
            sha256=hashlib.sha256(ruta.read_bytes()).hexdigest(),
        ))
    return fichas
