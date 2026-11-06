"""Puntaje de calidad de una lectura OCR: confianza de Tesseract más validadores de campos."""
from __future__ import annotations

import re
from datetime import date, datetime

PESOS_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
RE_RUC = re.compile(r"(?<!\d)\d{11}(?!\d)")
RE_FECHA = re.compile(r"\b\d{1,2} de [a-z]+ de \d{4}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", re.IGNORECASE)
RE_MONTO = re.compile(r"\d+(?:[.,]\d+)+")
RE_MONTO_VALIDO = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?")


def validar_ruc(ruc: str) -> bool:
    """Un RUC es válido si tiene 11 dígitos, empieza con 10, 15, 16, 17 o 20 y su dígito final cumple el módulo 11."""
    ruc = ruc.strip()
    if not re.fullmatch(r"\d{11}", ruc) or ruc[:2] not in ("10", "15", "16", "17", "20"):
        return False
    suma = sum(int(d) * p for d, p in zip(ruc[:10], PESOS_RUC))
    return (11 - suma % 11) % 10 == int(ruc[10])


def validar_fecha(texto: str) -> bool:
    """Una fecha es válida si existe en el calendario: 24/06/2026, 2026-06-24 o 24 de junio de 2026."""
    texto = texto.strip().lower()
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", texto):
            valor = datetime.strptime(texto, "%d/%m/%Y").date()
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
            valor = datetime.strptime(texto, "%Y-%m-%d").date()
        else:
            dia, _, mes, _, anio = texto.split()
            valor = date(int(anio), MESES[mes], int(dia))
    except (ValueError, KeyError):
        return False
    return 1990 <= valor.year <= 2100


def validar_monto(texto: str) -> bool:
    """Un monto es válido si la coma separa miles y el punto separa decimales: 1,250.00 o 35,569."""
    limpio = re.sub(r"^S/\.?\s*", "", texto.strip())
    return RE_MONTO_VALIDO.fullmatch(limpio) is not None


def puntuar(texto: str, confianza: float) -> dict:
    """Combina la confianza del OCR (0 a 1) con la tasa de campos que pasan su validador.

    Busca RUC, fechas y montos en el texto. Si no halla ninguno, la tasa de validadores es 0: un oficio,
    un comprobante o un estado financiero siempre traen alguno, así que no hallarlos indica una mala lectura.

    Returns:
        Diccionario con ``confianza``, ``validos``, ``invalidos`` y ``score`` = 0.5 * confianza + 0.5 * tasa.
    """
    sin_ruc = RE_RUC.sub(" ", texto)
    revisados = [(validar_ruc, r) for r in RE_RUC.findall(texto)]
    revisados += [(validar_fecha, f) for f in RE_FECHA.findall(sin_ruc)]
    revisados += [(validar_monto, m) for m in RE_MONTO.findall(RE_FECHA.sub(" ", sin_ruc))]
    validos = sum(1 for validar, valor in revisados if validar(valor))
    tasa = validos / len(revisados) if revisados else 0.0
    return {"confianza": round(confianza, 3), "validos": validos, "invalidos": len(revisados) - validos,
            "score": round(0.5 * confianza + 0.5 * tasa, 3)}
