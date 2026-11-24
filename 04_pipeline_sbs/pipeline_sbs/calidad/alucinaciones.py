"""Límites del LLM: ¿el valor figura en el texto? ¿Es coherente con los demás campos? Si no, pasa a revisión humana."""
from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz

from ..ingesta.leer_documento import formas_de_fecha, plano

ES_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERSONAS = {"firmante", "cliente", "titular", "depositante", "asegurado", "beneficiario", "nombre"}
UMBRAL_PARECIDO = 92  # de 0 a 100: cuánto debe parecerse un nombre al tramo más parecido del texto


def aparece(valor: Any, texto: str) -> bool:
    """Dice si el valor figura en el texto (evidencia literal, sin tildes ni mayúsculas).

    Un número se busca sin comas de miles (``39317`` coincide con ``39,317``); una fecha, en sus formas escritas;
    la moneda PEN, como «S/» o «soles»; un nombre, también con un parecido de 92 o más (tolera una letra distinta).
    """
    if valor is None or isinstance(valor, bool):
        return True
    llano = plano(texto)
    if isinstance(valor, (int, float)):
        formas = {f"{valor:.2f}", f"{valor:g}", str(int(valor)) if float(valor).is_integer() else str(valor)}
        return any(forma in llano.replace(",", "") for forma in formas)
    if ES_FECHA.match(str(valor)):
        return any(plano(forma) in llano for forma in formas_de_fecha(str(valor)))
    if valor in ("PEN", "USD"):
        return ("s/" in llano or "soles" in llano) if valor == "PEN" else ("us$" in llano or "dolar" in llano)
    return plano(valor) in llano or fuzz.partial_ratio(plano(valor), llano) >= UMBRAL_PARECIDO


def validar_campo(campo: str, valor: Any, campos: dict[str, Any]) -> bool:
    """Validadores de coherencia, los que haría un supervisor: la moneda es un código (PEN o USD), el emisor de un
    oficio es una intendencia, una persona no es una entidad DEMO y la TEA es menor que la TCEA."""
    if valor is None:
        return True
    if campo == "moneda":
        return valor in ("PEN", "USD")
    if campo == "emisor":
        return "intendencia" in plano(valor)
    if campo in PERSONAS:
        return "demo" not in plano(valor) and 2 <= len(str(valor).split()) <= 5
    if campo == "tea" and campos.get("tcea") is not None:
        return valor < campos["tcea"]
    if campo == "tcea" and campos.get("tea") is not None:
        return valor > campos["tea"]
    return True


def a_revisar(campo: str, valor: Any, texto: str, campos: dict[str, Any]) -> str | None:
    """La causa por la que un valor del LLM no se acepta solo, o None si se acepta."""
    if not aparece(valor, texto):
        return "no figura en el texto"
    if not validar_campo(campo, valor, campos):
        return "no pasa el validador"
    return None
