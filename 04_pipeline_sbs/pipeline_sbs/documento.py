"""Contrato de datos del pipeline: la ficha de un documento inventariado."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Documento:
    """Ficha mínima de un archivo recibido en la Mesa de Partes.

    Attributes:
        ruta: ruta del archivo tal como se recibió (relativa o absoluta).
        tipo: familia del archivo: "pdf", "imagen", "correo", "word", "html" u "otro".
        extension: extensión en minúsculas, con punto (por ejemplo ".pdf").
        paginas: número de páginas (imágenes: 1; archivos sin páginas o ilegibles: 0).
        tiene_capa_texto: True si el texto se puede leer sin OCR.
        sha256: huella del contenido, para detectar duplicados y reprocesos.
    """

    ruta: str
    tipo: str
    extension: str
    paginas: int
    tiene_capa_texto: bool
    sha256: str
