"""Extracción por reglas: expresiones regulares y EntityRuler de spaCy para los campos de un reclamo o un oficio."""
from __future__ import annotations

import re
from datetime import date, datetime

import spacy
from spacy.language import Language

from ..calidad.puntuar import RE_RUC, validar_ruc

PRODUCTOS = ("tarjeta de credito", "tarjeta de debito", "cuenta de ahorros", "cuenta sueldo", "prestamo personal")
CONFUSIONES = str.maketrans("OolIS", "00115")   # letras que el OCR confunde con cifras

RE_DNI = re.compile(r"(?<![\w])99\d{6}(?![\w])")
RE_DNI_OCR = re.compile(r"(?<![\w])99[\dOolIS]{6}(?![\w])")
RE_TELEFONO = re.compile(r"(?<!\d)999 000 \d{3}(?!\d)")
RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_ENTIDAD = re.compile(r"\b(?:Banco|Financiera|Caja|Edpyme|Aseguradora|Seguros)(?: (?!DEMO\b)\w+){1,4} DEMO S\.A\.?")
RE_FECHA_NUMERICA = re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{4}(?!\d)")
RE_OFICIO = re.compile(r"\b(\d{4})-(\d{4})-[I1l]D/([A-Z]{3})\b")
RE_MOTIVO = re.compile(r"Cargo reclamado \(([^)]+)\)", re.IGNORECASE)
PALABRA = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
RE_NOMBRES = (
    re.compile(rf"(?:soy|Atte\.|Cliente:)\s+({PALABRA}(?: {PALABRA}){{1,3}})"),
    re.compile(rf"({PALABRA}(?: {PALABRA}){{1,3}})(?=,? \(?DNI)"),
)


def extraer_dni(texto: str) -> str | None:
    """Busca un DNI del corpus (``99`` más seis cifras). Si no hay uno exacto, corrige las letras que el OCR
    confunde con cifras (O por 0, l o I por 1, S por 5).

    Returns:
        El DNI de 8 cifras, o None.
    """
    exacto = RE_DNI.search(texto)
    if exacto:
        return exacto.group()
    tolerante = RE_DNI_OCR.search(texto)
    return tolerante.group().translate(CONFUSIONES) if tolerante else None


def a_fecha(texto: str) -> date | None:
    """Convierte ``10/09/2026`` en fecha; devuelve None si el día o el mes no existen en el calendario."""
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def extraer_fecha(texto: str) -> str | None:
    """Busca la fecha del cargo reclamado y la devuelve como ``AAAA-MM-DD``.

    Prefiere la fila «Cargo reclamado» del estado de cuenta; si el OCR la partió, toma la fecha más reciente
    de todas las que encuentra.

    Returns:
        La fecha en formato ISO, o None si el texto no trae una fecha completa (``10/09`` no cuenta).
    """
    for linea in texto.splitlines():
        if "cargo reclamado" in linea.lower():
            fechas = [a_fecha(f) for f in RE_FECHA_NUMERICA.findall(linea)]
            if fechas and fechas[0]:
                return fechas[0].isoformat()
    validas = [f for f in (a_fecha(f) for f in RE_FECHA_NUMERICA.findall(texto)) if f]
    return max(validas).isoformat() if validas else None


def extraer_ruc(texto: str) -> str | None:
    """Busca un número de 11 cifras y lo acepta solo si su dígito verificador cumple el módulo 11.

    Returns:
        El primer RUC válido, o None si ninguno lo es (un RUC con una cifra mal leída no se devuelve).
    """
    for candidato in RE_RUC.findall(texto):
        if validar_ruc(candidato):
            return candidato
    return None


def extraer_numero_oficio(texto: str) -> str | None:
    """Busca el número de oficio ``0230-2026-ID/DSF`` y corrige la confusión de ``ID`` con ``1D`` del OCR."""
    encontrado = RE_OFICIO.search(texto)
    return f"{encontrado.group(1)}-{encontrado.group(2)}-ID/{encontrado.group(3)}" if encontrado else None


def extraer_telefono(texto: str) -> str | None:
    """Busca un teléfono del corpus (``999 000`` más tres cifras)."""
    encontrado = RE_TELEFONO.search(texto)
    return encontrado.group() if encontrado else None


def extraer_correo_electronico(texto: str) -> str | None:
    """Busca una dirección de correo electrónico."""
    encontrado = RE_CORREO.search(texto)
    return encontrado.group() if encontrado else None


def extraer_entidad(texto: str) -> str | None:
    """Busca el nombre de una entidad ficticia: una palabra de tipo (Banco, Financiera…) y ``DEMO S.A.``."""
    encontrado = RE_ENTIDAD.search(texto)
    return encontrado.group() if encontrado else None


def extraer_nombre(texto: str) -> str | None:
    """Busca el nombre del cliente: después de «soy», «Atte.» o «Cliente:», o justo antes de «DNI»."""
    for patron in RE_NOMBRES:
        encontrado = patron.search(texto)
        if encontrado:
            return encontrado.group(1)
    return None


def extraer_producto(texto: str) -> str | None:
    """Busca el primer producto financiero de la lista (tarjeta de crédito, cuenta sueldo…)."""
    minuscula = texto.lower()
    encontrados = [(minuscula.find(p), p) for p in PRODUCTOS if p in minuscula]
    return min(encontrados)[1] if encontrados else None


def extraer_motivo(texto: str) -> str | None:
    """Lee el motivo escrito en la fila «Cargo reclamado (motivo)» del estado de cuenta del adjunto."""
    encontrado = RE_MOTIVO.search(texto)
    return encontrado.group(1).strip().lower() if encontrado else None


def modelo_con_reglas(nombre: str = "es_core_news_md") -> Language:
    """Carga un modelo de spaCy nuevo y le agrega un ``EntityRuler`` con patrones de DNI, teléfono y producto.

    El ruler va antes del NER del modelo y sobrescribe sus entidades cuando coinciden. Se carga una copia
    aparte para no alterar el modelo que otras funciones guardan en memoria.

    Args:
        nombre: modelo de spaCy (si no está instalado se usa es_core_news_sm).

    Returns:
        El modelo con el componente ``entity_ruler``.
    """
    try:
        nlp = spacy.load(nombre)
    except OSError:
        nlp = spacy.load("es_core_news_sm")
    ruler = nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": True})
    patrones = [
        {"label": "DNI", "pattern": [{"TEXT": {"REGEX": r"^99\d{6}$"}}]},
        {"label": "TELEFONO", "pattern": [{"TEXT": "999"}, {"TEXT": "000"}, {"TEXT": {"REGEX": r"^\d{3}$"}}]},
    ]
    patrones += [{"label": "PRODUCTO", "pattern": [{"LOWER": palabra} for palabra in producto.split()]}
                 for producto in PRODUCTOS]
    ruler.add_patterns(patrones)
    return nlp
