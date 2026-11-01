"""Extractores de texto por formato: PDF (tres bibliotecas), DOCX, correo EML, HTML e imagen.

Cada extractor devuelve una ``Extraccion`` y deja subir las excepciones de la biblioteca; el cargador
las traduce a errores tipificados con ``traducir_excepcion``. Se usa ``import pymupdf`` (no ``fitz``).
"""
from __future__ import annotations

import logging
import re
import warnings
import zipfile
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import pymupdf
import pypdf
from bs4 import BeautifulSoup
from PIL import Image

from pipeline_sbs.ingesta.errores import (
    ErrorCorreoInvalido,
    ErrorDocxCorrupto,
    ErrorFormatoNoSoportado,
    ErrorImagenInvalida,
    ErrorPdfCifrado,
    ErrorPdfDanado,
)

registro = logging.getLogger(__name__)

# MuPDF escribe sus avisos en la consola; los errores se capturan como excepciones y se registran.
pymupdf.TOOLS.mupdf_display_errors(False)

BIBLIOTECAS_PDF = ("pypdf", "pdfplumber", "pymupdf")


@dataclass(frozen=True)
class Extraccion:
    """Resultado de extraer un archivo.

    Attributes:
        texto: texto completo (páginas unidas con salto de línea), sin normalizar.
        paginas: número de páginas (1 para DOCX, correo, HTML e imagen).
        caracteres_por_pagina: caracteres (sin espacios en los extremos) de cada página.
        metadatos: datos propios del formato (asunto y adjuntos del correo, tamaño de la imagen, etc.).
    """

    texto: str
    paginas: int
    caracteres_por_pagina: tuple[int, ...] = ()
    metadatos: dict[str, Any] = field(default_factory=dict)

    @property
    def caracteres(self) -> int:
        """Total de caracteres del texto sin espacios en los extremos."""
        return len(self.texto.strip())


def extraccion_desde_paginas(textos_por_pagina: list[str]) -> Extraccion:
    """Arma una ``Extraccion`` a partir del texto de cada página.

    Args:
        textos_por_pagina: una cadena por página (puede ser vacía).

    Returns:
        Extraccion con el texto unido, el número de páginas y los caracteres de cada una.
    """
    return Extraccion(
        texto="\n".join(textos_por_pagina),
        paginas=len(textos_por_pagina),
        caracteres_por_pagina=tuple(len(t.strip()) for t in textos_por_pagina),
    )


# ---------------------------------------------------------------- PDF

def extraer_pdf_pypdf(ruta: str | Path) -> Extraccion:
    """Extrae el texto de un PDF con pypdf (BSD-3).

    Args:
        ruta: archivo PDF.

    Returns:
        Extraccion con una entrada por página.

    Raises:
        ErrorPdfCifrado: si el PDF pide contraseña.
    """
    lector = pypdf.PdfReader(str(ruta))
    if lector.is_encrypted:
        raise ErrorPdfCifrado("el PDF pide contraseña")
    return extraccion_desde_paginas([pagina.extract_text() or "" for pagina in lector.pages])


def extraer_pdf_pdfplumber(ruta: str | Path) -> Extraccion:
    """Extrae el texto de un PDF con pdfplumber (MIT).

    Args:
        ruta: archivo PDF.

    Returns:
        Extraccion con una entrada por página.
    """
    import pdfplumber

    with pdfplumber.open(str(ruta)) as pdf:
        return extraccion_desde_paginas([pagina.extract_text() or "" for pagina in pdf.pages])


def extraer_pdf_pymupdf(ruta: str | Path) -> Extraccion:
    """Extrae el texto de un PDF con PyMuPDF (AGPL-3.0 o licencia comercial).

    PyMuPDF repara en silencio los PDF truncados y devuelve el texto parcial; aquí un PDF reparado
    se trata como dañado.

    Args:
        ruta: archivo PDF.

    Returns:
        Extraccion con una entrada por página.

    Raises:
        ErrorPdfCifrado: si el PDF pide contraseña.
        ErrorPdfDanado: si el PDF solo se abrió tras una reparación o no tiene páginas.
    """
    try:
        doc = pymupdf.open(str(ruta))
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
        raise ErrorPdfDanado(f"{type(error).__name__}: no se pudo abrir el PDF") from error
    with doc:
        if doc.needs_pass:
            raise ErrorPdfCifrado("el PDF pide contraseña")
        if doc.is_repaired:
            raise ErrorPdfDanado("el PDF estaba dañado y solo se abrió tras una reparación automática")
        if doc.page_count == 0:
            raise ErrorPdfDanado("el PDF no tiene páginas")
        return extraccion_desde_paginas([pagina.get_text() for pagina in doc])


def extraer_pdf(ruta: str | Path, biblioteca: str = "pymupdf") -> Extraccion:
    """Extrae el texto de un PDF con la biblioteca indicada.

    Args:
        ruta: archivo PDF.
        biblioteca: "pypdf", "pdfplumber" o "pymupdf".

    Returns:
        Extraccion del PDF.

    Raises:
        ValueError: si la biblioteca no existe.
    """
    funciones = {"pypdf": extraer_pdf_pypdf, "pdfplumber": extraer_pdf_pdfplumber, "pymupdf": extraer_pdf_pymupdf}
    if biblioteca not in funciones:
        raise ValueError(f"Biblioteca desconocida: {biblioteca}. Usa una de {BIBLIOTECAS_PDF}")
    return funciones[biblioteca](ruta)


# ---------------------------------------------------------------- DOCX

def extraer_docx(ruta: str | Path) -> Extraccion:
    """Extrae párrafos y tablas de nivel superior de un .docx, en el orden del documento.

    Las celdas combinadas se repiten en ``row.cells``; aquí se comparan por identidad para no duplicarlas.

    Args:
        ruta: archivo .docx.

    Returns:
        Extraccion de una sola página.

    Raises:
        ErrorDocxCorrupto: si el archivo no es un ZIP de Word válido.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    ruta = Path(ruta)
    if not zipfile.is_zipfile(ruta):
        raise ErrorDocxCorrupto("el archivo no es un ZIP válido")
    with zipfile.ZipFile(ruta) as paquete:
        if "word/document.xml" not in paquete.namelist():
            raise ErrorDocxCorrupto("el ZIP no contiene word/document.xml")
    documento = Document(str(ruta))
    bloques: list[str] = []
    for hijo in documento.element.body.iterchildren():
        if hijo.tag.endswith("}p"):
            bloques.append(Paragraph(hijo, documento).text)
        elif hijo.tag.endswith("}tbl"):
            for fila in Table(hijo, documento).rows:
                vistas: set[int] = set()
                celdas: list[str] = []
                for celda in fila.cells:
                    if id(celda._tc) in vistas:      # celda combinada repetida
                        continue
                    vistas.add(id(celda._tc))
                    celdas.append(celda.text.strip())
                bloques.append(" | ".join(celdas))
    texto = "\n".join(bloques)
    return Extraccion(texto=texto, paginas=1, caracteres_por_pagina=(len(texto.strip()),),
                      metadatos={"tablas": len(documento.tables)})


# ---------------------------------------------------------------- correo EML

def extraer_eml(ruta: str | Path) -> Extraccion:
    """Extrae el cuerpo de un correo .eml y lista sus adjuntos (sin abrirlos).

    Args:
        ruta: archivo .eml.

    Returns:
        Extraccion con el cuerpo; en ``metadatos``: asunto, remitente, adjuntos y defectos.

    Raises:
        ErrorCorreoInvalido: si el archivo no tiene cabeceras de correo.
    """
    with Path(ruta).open("rb") as archivo:
        mensaje = BytesParser(policy=policy.default).parse(archivo)
    if not mensaje.keys():
        raise ErrorCorreoInvalido("el archivo no tiene cabeceras de correo")
    cuerpo = mensaje.get_body(preferencelist=("plain", "html"))
    texto = ""
    if cuerpo is not None:
        contenido = cuerpo.get_content()
        texto = _html_a_texto(contenido) if cuerpo.get_content_type() == "text/html" else contenido
    adjuntos = [Path(parte.get_filename() or "sin_nombre").name for parte in mensaje.iter_attachments()]
    return Extraccion(
        texto=texto, paginas=1, caracteres_por_pagina=(len(texto.strip()),),
        metadatos={"asunto": str(mensaje.get("Subject", "")), "remitente": str(mensaje.get("From", "")),
                   "adjuntos": adjuntos, "defectos": len(mensaje.defects)},
    )


# ---------------------------------------------------------------- HTML

def decodificar_html(contenido: bytes) -> str:
    """Convierte los bytes de un HTML en texto sin adivinar mal la codificación.

    Orden: marca de orden de bytes UTF-8, ``charset`` declarado en la cabecera, UTF-8 estricto y,
    como último recurso, cp1252 (superconjunto práctico de latin-1).

    Args:
        contenido: bytes del archivo.

    Returns:
        Texto decodificado.
    """
    if contenido.startswith(b"\xef\xbb\xbf"):
        return contenido.decode("utf-8-sig")
    declarado = re.search(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9_\-]+)", contenido[:2048], re.IGNORECASE)
    if declarado:
        try:
            return contenido.decode(declarado.group(1).decode("ascii"))
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def _html_a_texto(html: str) -> str:
    """Devuelve el texto visible de un HTML, sin ``script``, ``style`` ni ``template``."""
    sopa = BeautifulSoup(html, "html.parser")
    for etiqueta in sopa(["script", "style", "template"]):
        etiqueta.decompose()
    return sopa.get_text("\n", strip=True)


def extraer_html(ruta: str | Path) -> Extraccion:
    """Extrae el texto visible de un archivo HTML (parser ``html.parser`` de la biblioteca estándar).

    Args:
        ruta: archivo HTML.

    Returns:
        Extraccion de una sola página.
    """
    texto = _html_a_texto(decodificar_html(Path(ruta).read_bytes()))
    return Extraccion(texto=texto, paginas=1, caracteres_por_pagina=(len(texto.strip()),))


# ---------------------------------------------------------------- imagen

def extraer_imagen(ruta: str | Path) -> Extraccion:
    """Valida una imagen con Pillow. No tiene texto seleccionable: requiere OCR (S03).

    Args:
        ruta: archivo de imagen (PNG, JPG, TIFF).

    Returns:
        Extraccion con texto vacío, una página y el tamaño en ``metadatos``.

    Raises:
        ErrorImagenInvalida: si Pillow no puede identificarla o es una posible bomba de descompresión.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(ruta) as imagen:
                imagen.verify()                      # comprueba la estructura sin decodificar los píxeles
            with Image.open(ruta) as imagen:
                ancho, alto = imagen.size
                formato = imagen.format or ""
    except (Image.UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ErrorImagenInvalida(f"{type(error).__name__}: {error}") from error
    return Extraccion(texto="", paginas=1, caracteres_por_pagina=(0,),
                      metadatos={"ancho": ancho, "alto": alto, "formato_pillow": formato})


# ---------------------------------------------------------------- despacho

def extraer_texto(ruta: str | Path, formato: str) -> Extraccion:
    """Elige el extractor según el formato detectado por la firma del contenido.

    Args:
        ruta: archivo a leer.
        formato: "pdf", "docx", "eml", "html", "png", "jpg" o "tif".

    Returns:
        Extraccion del archivo.

    Raises:
        ErrorFormatoNoSoportado: si no hay extractor para el formato.
    """
    if formato == "pdf":
        return extraer_pdf_pymupdf(ruta)
    if formato == "docx":
        return extraer_docx(ruta)
    if formato == "eml":
        return extraer_eml(ruta)
    if formato == "html":
        return extraer_html(ruta)
    if formato in ("png", "jpg", "tif"):
        return extraer_imagen(ruta)
    raise ErrorFormatoNoSoportado(f"no hay extractor para el formato '{formato}'")
