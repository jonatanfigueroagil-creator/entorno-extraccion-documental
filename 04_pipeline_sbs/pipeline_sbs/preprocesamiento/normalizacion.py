"""Normalización de texto extraído: Unicode, espacios, guiones de corte, fechas y montos en soles."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# Espacios "especiales" que NFC no toca: NBSP, espacio fino, espacio de cifra, espacio estrecho, etc.
ESPACIOS_ESPECIALES = "               　"
# Caracteres invisibles que se eliminan: guion blando, ancho cero, marca de orden de bytes.
INVISIBLES = "­​‌‍﻿"
# Ligaduras tipográficas que se expanden de forma explícita (en vez de aplicar NFKC a todo el texto).
LIGADURAS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_LETRA = "a-zA-ZáéíóúüñÁÉÍÓÚÜÑ"
_RE_GUION_CORTE = re.compile(rf"(?<=[{_LETRA}])-[ \t]*\n[ \t]*(?=[a-záéíóúüñ])")
_RE_FECHA_NUMERICA = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)")
_RE_FECHA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_RE_FECHA_LARGA = re.compile(r"(?<!\d)(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})(?!\d)", re.IGNORECASE)


def normalizar_texto(texto: str) -> str:
    """Normaliza el texto extraído sin cambiar su contenido: NFC, espacios y caracteres invisibles.

    Aplica NFC (no NFKC: NFKC convierte ``Nº`` en ``No``), cambia los espacios especiales por un espacio,
    elimina caracteres invisibles, expande ligaduras, unifica saltos de línea y colapsa espacios repetidos.

    Args:
        texto: texto tal como lo entregó la biblioteca de extracción.

    Returns:
        Texto normalizado, sin espacios en los extremos de cada línea ni en los extremos del texto.

    Raises:
        TypeError: si ``texto`` no es una cadena.
    """
    if not isinstance(texto, str):
        raise TypeError("normalizar_texto espera una cadena")
    texto = unicodedata.normalize("NFC", texto)
    for caracter in INVISIBLES:
        texto = texto.replace(caracter, "")
    for ligadura, reemplazo in LIGADURAS.items():
        texto = texto.replace(ligadura, reemplazo)
    for espacio in ESPACIOS_ESPECIALES:
        texto = texto.replace(espacio, " ")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = [re.sub(r"[ \t]+", " ", linea).strip() for linea in texto.split("\n")]
    return "\n".join(lineas).strip()


def unir_guiones(texto: str) -> str:
    """Une las palabras cortadas con guion al final de línea (``pala-`` + ``bra`` -> ``palabra``).

    Es una heurística: solo une si la línea siguiente empieza en minúscula. Falla con los compuestos
    legítimos: ``socio-`` + ``economico`` queda ``socioeconomico``.

    Args:
        texto: texto con saltos de línea.

    Returns:
        Texto con las palabras unidas.
    """
    return _RE_GUION_CORTE.sub("", texto)


def parsear_fecha(texto: str) -> date | None:
    """Convierte una fecha escrita en el formato del corpus en ``date``.

    Reconoce ``DD/MM/AAAA``, ``DD-MM-AAAA``, ``AAAA-MM-DD`` y ``11 de agosto de 2026`` (con o sin
    texto alrededor). El día va antes que el mes.

    Args:
        texto: texto que contiene la fecha.

    Returns:
        La fecha, o None si no hay una fecha reconocible o no existe en el calendario (``31/02/2026``).
    """
    if not isinstance(texto, str):
        return None
    texto = normalizar_texto(texto)
    candidatas: list[tuple[int, int, int]] = []
    iso = _RE_FECHA_ISO.search(texto)
    if iso:
        candidatas.append((int(iso.group(1)), int(iso.group(2)), int(iso.group(3))))
    numerica = _RE_FECHA_NUMERICA.search(texto)
    if numerica:
        candidatas.append((int(numerica.group(3)), int(numerica.group(2)), int(numerica.group(1))))
    larga = _RE_FECHA_LARGA.search(texto)
    if larga and larga.group(2).lower() in MESES:
        candidatas.append((int(larga.group(3)), MESES[larga.group(2).lower()], int(larga.group(1))))
    for anio, mes, dia in candidatas:
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue
    return None


def parsear_monto(texto: str) -> Decimal | None:
    """Convierte un monto en soles escrito de varias formas en ``Decimal``.

    Acepta ``S/ 1 250,00``, ``S/ 8,861.00``, ``1.250,50``, ``S/. 1250`` y negativos entre paréntesis
    o con signo. Regla del separador: si aparecen coma y punto, el último es el decimal; si hay uno
    solo y le siguen exactamente 3 dígitos (``1,250``) es separador de miles; en otro caso es decimal.

    Args:
        texto: texto con el monto.

    Returns:
        El monto como ``Decimal``, o None si no hay un número.
    """
    if not isinstance(texto, str):
        return None
    limpio = normalizar_texto(texto)
    negativo = (limpio.startswith("(") and limpio.endswith(")")) or bool(re.search(r"(^|\s)-\s*\d", limpio))
    limpio = re.sub(r"S/\.?|PEN|USD|US\$|\$", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"[^\d.,]", "", limpio.replace(" ", ""))
    if not re.search(r"\d", limpio):
        return None
    if "," in limpio and "." in limpio:
        decimal = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        miles = "." if decimal == "," else ","
        limpio = limpio.replace(miles, "").replace(decimal, ".")
    elif "," in limpio or "." in limpio:
        separador = "," if "," in limpio else "."
        partes = limpio.split(separador)
        if len(partes) > 2 or len(partes[-1]) == 3:
            limpio = "".join(partes)          # separador de miles
        else:
            limpio = ".".join(partes)         # separador decimal
    try:
        valor = Decimal(limpio.strip("."))
    except InvalidOperation:
        return None
    return -valor if negativo else valor
