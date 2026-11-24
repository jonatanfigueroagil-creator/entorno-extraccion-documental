"""Montos en soles: en cifras (``S/ 2,643.00``), en palabras («dos mil seiscientos cuarenta y tres soles») o en la tabla."""
from __future__ import annotations

import re
import unicodedata

UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
    "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
CENTENAS = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
            "quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900}
PALABRAS_NUMERO = {**UNIDADES, **DECENAS, **CENTENAS, "mil": 1000, "millon": 10**6, "millones": 10**6}

_ALTERNATIVAS = "|".join(sorted(PALABRAS_NUMERO, key=len, reverse=True))
RE_PALABRAS = re.compile(rf"\b((?:(?:y\s+)?(?:{_ALTERNATIVAS})\s+)+)soles?\b")
RE_SOLES = re.compile(r"S/\.?\s*(\d[\d,]*(?:\.\d{1,2})?)")
RE_FILA_CARGO = re.compile(r"Cargo reclamado\s*\([^)]*\)\s*S?/?\s*(\d[\d,]*\.\d{2})", re.IGNORECASE)


def sin_tildes(texto: str) -> str:
    """Pasa a minúscula y quita las tildes (``dieciséis`` queda ``dieciseis``)."""
    base = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def monto_a_numero(texto: str) -> int | None:
    """Convierte un número escrito en palabras en español a entero.

    Args:
        texto: por ejemplo ``dos mil seiscientos cuarenta y tres`` (puede terminar en «soles»).

    Returns:
        El número (2643), o None si alguna palabra no es un número.
    """
    palabras = [p for p in sin_tildes(texto).split() if p not in ("y", "sol", "soles")]
    if not palabras:
        return None
    total, actual = 0, 0
    for palabra in palabras:
        valor = PALABRAS_NUMERO.get(palabra)
        if valor is None:
            return None
        if valor >= 1000:
            total += (actual or 1) * valor
            actual = 0
        else:
            actual += valor
    return total + actual


def extraer_monto_cifras(texto: str) -> float | None:
    """Busca un monto escrito con cifras detrás de ``S/`` (``S/ 2,643.00`` o ``S/ 450``)."""
    encontrado = RE_SOLES.search(texto)
    return float(encontrado.group(1).replace(",", "")) if encontrado else None


def extraer_monto_palabras(texto: str) -> float | None:
    """Busca un monto escrito en palabras y seguido de «soles», y lo convierte a número."""
    encontrado = RE_PALABRAS.search(sin_tildes(texto))
    if not encontrado:
        return None
    valor = monto_a_numero(encontrado.group(1))
    return float(valor) if valor is not None else None


def extraer_monto_tabla(texto: str) -> float | None:
    """Lee el importe de la fila «Cargo reclamado (motivo) 2,643.00» del estado de cuenta del adjunto."""
    encontrado = RE_FILA_CARGO.search(texto)
    return float(encontrado.group(1).replace(",", "")) if encontrado else None


def extraer_monto(texto: str, palabras: bool = True) -> float | None:
    """Busca el monto reclamado: primero en cifras, luego en palabras y por último en la tabla del adjunto.

    Args:
        texto: cuerpo del correo y, si se desea, el texto del OCR del adjunto.
        palabras: si es False, solo busca en cifras (así se mide cuánto pierde una regla simple).

    Returns:
        El monto como número decimal, o None.
    """
    monto = extraer_monto_cifras(texto)
    if monto is None and palabras:
        monto = extraer_monto_palabras(texto)
    if monto is None and palabras:
        monto = extraer_monto_tabla(texto)
    return monto
