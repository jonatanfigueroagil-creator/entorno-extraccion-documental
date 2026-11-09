"""Lote público real: empresa y fecha de presentación de políticas de dividendos, medidas contra la ficha de cada documento.

El lote real viaja con el curso y queda en una carpeta local (por defecto ``curso/datos/14_Publico_Real`` en la
unidad del sistema, o la que indique la variable de entorno ``SBS_LOTE_REAL``). Si la carpeta no existe, las funciones devuelven
None y el cuaderno omite la sección. Solo se usan organizaciones (ORG) y fechas: las personas (PER) se descartan y nunca se muestran.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from ..calidad.f1 import f1_por_campo
from ..calidad.puntuar import MESES
from .ner import entidades_a_campos, ner_spacy, ner_transformers

RE_EMPRESA_MAYUSCULAS = re.compile(r"((?:[A-ZÁÉÍÓÚÑ]{2,}\s+){2,6}S\.\s?A\.(?:\s?A\.)?)")
RE_EMPRESA_TITULO = re.compile(r"[Pp]ol[ií]tica de [Dd]ividendos de ([A-ZÁÉÍÓÚÑ]\w*(?: [A-ZÁÉÍÓÚÑ]\w*){0,3}) para")
RE_EMPRESA_MIXTA = re.compile(r"((?:[A-ZÁÉÍÓÚÑ]\w+\s+){1,6}S\.\s?A\.(?:\s?A\.)?)")
RE_FECHA_SELLO = re.compile(r"Fecha:\s*(\d{1,2}/\d{1,2}/\d{4})")
RE_FECHA_NUMERICA = re.compile(r"(?<!\d)(\d{1,2}/\d{1,2}/\d{4})(?!\d)")
RE_FECHA_LARGA = re.compile(r"(\d{1,2}) de ([A-Za-záéíóú]+) de (\d{4})")


def localizar_lote(carpeta: str = "curso/datos/14_Publico_Real") -> Path | None:
    """Busca la carpeta local del lote real: la variable ``SBS_LOTE_REAL`` o ``carpeta`` en la unidad del sistema.

    Returns:
        La carpeta si existe y trae ``00_FICHAS.json``; en otro caso None.
    """
    candidatas = [os.environ.get("SBS_LOTE_REAL"), Path(os.environ.get("SystemDrive", "C:") + os.sep) / carpeta]
    for candidata in candidatas:
        if candidata and (Path(candidata) / "00_FICHAS.json").is_file():
            return Path(candidata)
    return None


def documentos_legibles(lote: Path) -> list[dict[str, Any]]:
    """Políticas de dividendos que se leen sin OCR (PDF o DOCX con texto): id, ruta, empresa y fecha de la ficha."""
    fichas = json.loads((lote / "00_FICHAS.json").read_text(encoding="utf-8"))
    return [{"id": f["id"], "ruta": lote / "01_Dividendos" / f["archivo"], "empresa": f["empresa"], "fecha": f["fecha_presentacion"]}
            for f in fichas if f["id"].startswith("DIV") and not f["escaneado"] and f["formato"] in ("pdf", "docx")]


def leer_texto_documento(ruta: str | Path) -> str:
    """Lee el texto de un PDF (PyMuPDF) o de un DOCX (python-docx: párrafos y tablas)."""
    ruta = Path(ruta)
    if ruta.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(str(ruta)) as pdf:
            return "\n".join(pagina.get_text() for pagina in pdf)
    import docx

    documento = docx.Document(str(ruta))
    celdas = [c.text for tabla in documento.tables for fila in tabla.rows for c in fila.cells]
    return "\n".join([p.text for p in documento.paragraphs] + celdas)


def normalizar_empresa(texto: str | None) -> str | None:
    """Lleva un nombre de empresa a una forma comparable: mayúsculas, sin tildes, sin paréntesis «(ANTES …)» ni «S.A.A.» o «S.A.»."""
    if not texto:
        return None
    base = unicodedata.normalize("NFD", texto.split("(")[0].upper())
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    base = re.sub(r"\bS\.?\s?A\.?\s?A?\.?(?=\s|$)", " ", base)
    base = re.sub(r"[^A-Z0-9 ]", " ", base)
    return re.sub(r"\s+", " ", base).strip() or None


def texto_a_fecha(texto: str) -> str | None:
    """Convierte ``16/03/2026`` o ``31 de marzo de 2010`` en ``AAAA-MM-DD``; None si no es una fecha válida."""
    numerica = RE_FECHA_NUMERICA.search(texto)
    larga = RE_FECHA_LARGA.search(texto)
    try:
        if numerica:
            return datetime.strptime(numerica.group(1), "%d/%m/%Y").date().isoformat()
        if larga and larga.group(2).lower() in MESES:
            return datetime(int(larga.group(3)), MESES[larga.group(2).lower()], int(larga.group(1))).date().isoformat()
    except ValueError:
        return None
    return None


def extraer_empresa(texto: str) -> str | None:
    """Regla: encabezado en mayúsculas que termina en S.A., título «Política de Dividendos de X para…» o nombre con S.A. en el texto."""
    inicio = re.sub(r"\s+", " ", texto[:500])
    for patron, zona in ((RE_EMPRESA_MAYUSCULAS, inicio), (RE_EMPRESA_TITULO, inicio), (RE_EMPRESA_MIXTA, re.sub(r"\s+", " ", texto))):
        encontrado = patron.search(zona)
        if encontrado:
            return encontrado.group(1).strip()
    return None


def extraer_fecha_presentacion(texto: str) -> str | None:
    """Regla: la fecha del sello «Fecha: dd/mm/aaaa» y, si no hay, la primera fecha escrita «31 de marzo de 2010»."""
    sello = RE_FECHA_SELLO.search(texto)
    if sello:
        return texto_a_fecha(sello.group(1))
    larga = RE_FECHA_LARGA.search(texto)
    return texto_a_fecha(larga.group(0)) if larga else None


def campos_desde_ner(entidades: list[dict[str, Any]]) -> dict[str, str | None]:
    """Resume entidades en ``empresa`` (la organización que más se repite) y ``fecha`` (la primera entidad DATE válida). Descarta PER."""
    utiles = [e for e in entidades if e["etiqueta"] != "PER"]
    fechas = [texto_a_fecha(e["texto"]) for e in utiles if e["etiqueta"] == "DATE"]
    return {"empresa": entidades_a_campos(utiles)["entidad"], "fecha": next((f for f in fechas if f), None)}


def medir_lote_real(lote: Path | None, dispositivo: str = "auto") -> dict[str, Any] | None:
    """Corre reglas, spaCy y Transformers sobre las políticas legibles y calcula el F1 de empresa y fecha contra la ficha.

    Args:
        lote: carpeta del lote real (de ``localizar_lote``); None si no existe.
        dispositivo: ``auto``, ``cpu`` o ``cuda`` para Transformers.

    Returns:
        ``{"documentos", "f1": {enfoque: {campo: F1}}, "aciertos": {enfoque: {campo: n}}}``; None si no hay lote.
        spaCy no tiene etiqueta de fecha: su F1 de fecha es 0.
    """
    if lote is None:
        return None
    documentos = documentos_legibles(lote)
    textos = [leer_texto_documento(d["ruta"]) for d in documentos]
    correctos = [{"empresa": normalizar_empresa(d["empresa"]), "fecha": texto_a_fecha(d["fecha"])} for d in documentos]
    enfoques = {
        "reglas": [{"empresa": extraer_empresa(t), "fecha": extraer_fecha_presentacion(t)} for t in textos],
        "spaCy": [{"empresa": entidades_a_campos(ner_spacy(t))["entidad"], "fecha": None} for t in textos],
        "Transformers": [campos_desde_ner(ner_transformers(t, dispositivo=dispositivo)) for t in textos],
    }
    f1, aciertos = {}, {}
    for nombre, predichos in enfoques.items():
        normalizados = [{"empresa": normalizar_empresa(p["empresa"]), "fecha": p["fecha"]} for p in predichos]
        medidas = f1_por_campo(normalizados, correctos, ["empresa", "fecha"])
        f1[nombre] = {campo: m["f1"] for campo, m in medidas.items()}
        aciertos[nombre] = {campo: m["aciertos"] for campo, m in medidas.items()}
    return {"documentos": [d["id"] for d in documentos], "f1": f1, "aciertos": aciertos}
