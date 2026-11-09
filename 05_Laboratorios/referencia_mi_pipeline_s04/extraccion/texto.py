"""Texto de entrada de la extracción: cuerpo del correo, texto del OCR y análisis con spaCy."""
from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path
from typing import Any

import spacy
from spacy.language import Language
from spacy.tokens import Doc


def leer_correo(ruta: str | Path) -> dict[str, Any]:
    """Abre un correo .eml y separa su asunto, su cuerpo de texto y sus adjuntos.

    Args:
        ruta: archivo .eml.

    Returns:
        Diccionario con ``asunto``, ``remitente`` (la dirección de correo de quien escribe), ``cuerpo`` (texto plano) y ``adjuntos``
        (lista de pares nombre y bytes).
    """
    with open(ruta, "rb") as archivo:
        mensaje = BytesParser(policy=policy.default).parse(archivo)
    parte = mensaje.get_body(preferencelist=("plain",))
    cuerpo = parte.get_content().strip() if parte is not None else ""
    adjuntos = [(p.get_filename(), p.get_content()) for p in mensaje.iter_attachments()]
    return {"asunto": str(mensaje["Subject"] or ""), "remitente": parseaddr(str(mensaje["From"] or ""))[1], "cuerpo": cuerpo,
            "adjuntos": adjuntos}


def cargar_texto(ruta: str | Path) -> str:
    """Devuelve el texto de un archivo: el campo ``texto`` de un .json de OCR, el cuerpo de un .eml o un .txt.

    Args:
        ruta: archivo .json (salida del OCR de S03), .eml o .txt.

    Returns:
        El texto, sin espacios sobrantes en los extremos.

    Raises:
        ValueError: si la extensión no es una de las tres.
    """
    ruta = Path(ruta)
    sufijo = ruta.suffix.lower()
    if sufijo == ".json":
        return json.loads(ruta.read_text(encoding="utf-8"))["texto"].strip()
    if sufijo == ".eml":
        return leer_correo(ruta)["cuerpo"]
    if sufijo == ".txt":
        return ruta.read_text(encoding="utf-8").strip()
    raise ValueError(f"Extensión no admitida: {sufijo}")


@lru_cache(maxsize=4)
def cargar_modelo(nombre: str = "es_core_news_md", respaldo: str = "es_core_news_sm") -> Language:
    """Carga un modelo de spaCy y lo guarda en memoria; si el principal no está instalado, usa el de respaldo.

    Args:
        nombre: modelo principal.
        respaldo: modelo más pequeño que se usa si el principal no existe.

    Returns:
        El objeto ``Language`` listo para analizar texto.
    """
    try:
        return spacy.load(nombre)
    except OSError:
        return spacy.load(respaldo)


def analizar(texto: str, nombre: str = "es_core_news_md") -> Doc:
    """Divide el texto en palabras (tokens) y les asigna forma base, clase gramatical y entidades.

    Args:
        texto: texto de un correo o de un adjunto.
        nombre: modelo de spaCy.

    Returns:
        Documento de spaCy: cada token trae ``text``, ``lemma_`` y ``pos_``; el documento trae ``ents``.
    """
    return cargar_modelo(nombre)(texto)


def formas_base(texto: str, nombre: str = "es_core_news_md") -> list[str]:
    """Lista las formas base (lemas) de las palabras del texto, sin signos de puntuación.

    Args:
        texto: texto a analizar.
        nombre: modelo de spaCy.

    Returns:
        Los lemas en minúscula, por ejemplo ``cobros`` queda como ``cobro``.
    """
    return [t.lemma_.lower() for t in analizar(texto, nombre) if not t.is_punct and not t.is_space]
