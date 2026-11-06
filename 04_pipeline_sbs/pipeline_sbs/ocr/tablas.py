"""Tabla escaneada a DataFrame: se borran las líneas con OpenCV y se lee el texto con Tesseract."""
from __future__ import annotations

import re

import cv2
import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from .leer import leer_con_confianza
from .preprocesar import a_gris, adaptativa, mediana

RE_NUMERO = re.compile(r"[\d.,]*\d[\d.,]*")


def quitar_lineas(gris: np.ndarray) -> tuple[np.ndarray, int]:
    """Detecta las líneas de la tabla (morfología) y las cubre con el color de alrededor.

    Args:
        gris: imagen en escala de grises.

    Returns:
        La imagen sin líneas y la cantidad de líneas horizontales halladas.
    """
    alto, ancho = gris.shape
    tinta = cv2.adaptiveThreshold(cv2.bitwise_not(gris), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
    nucleo_h = cv2.getStructuringElement(cv2.MORPH_RECT, (ancho // 30, 1))
    nucleo_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, alto // 30))
    horizontales = cv2.dilate(cv2.erode(tinta, nucleo_h), nucleo_h)
    verticales = cv2.dilate(cv2.erode(tinta, nucleo_v), nucleo_v)
    lineas = cv2.dilate(cv2.bitwise_or(horizontales, verticales), np.ones((5, 5), np.uint8))
    limpia = cv2.inpaint(gris, lineas, 3, cv2.INPAINT_TELEA)
    return limpia, cv2.connectedComponents(horizontales)[0] - 1


def a_numero(texto: str) -> float:
    """Convierte "35,569" en 35569.0; devuelve NaN si no es un número."""
    try:
        return float(texto.replace(",", ""))
    except ValueError:
        return float("nan")


def agrupar_filas(palabras: list[dict]) -> list[list[dict]]:
    """Agrupa las palabras en filas: las que tienen casi la misma altura van juntas, de izquierda a derecha."""
    if not palabras:
        return []
    alto_tipico = float(np.median([p["caja"][3] - p["caja"][1] for p in palabras]))
    ordenadas = sorted(palabras, key=lambda p: (p["caja"][1] + p["caja"][3]) / 2)
    filas, centro_fila = [[ordenadas[0]]], (ordenadas[0]["caja"][1] + ordenadas[0]["caja"][3]) / 2
    for palabra in ordenadas[1:]:
        centro = (palabra["caja"][1] + palabra["caja"][3]) / 2
        if centro - centro_fila > alto_tipico * 0.6:
            filas.append([])
        filas[-1].append(palabra)
        centro_fila = centro
    return [sorted(fila, key=lambda p: p["caja"][0]) for fila in filas]


def columnas_numericas(filas: list[list[dict]], separacion: int = 120) -> list[float]:
    """Halla el borde derecho de cada columna de cifras (las cifras van alineadas a la derecha)."""
    bordes = sorted(p["caja"][2] for fila in filas for p in fila if RE_NUMERO.fullmatch(p["texto"]))
    grupos: list[list[int]] = []
    for borde in bordes:
        if grupos and borde - grupos[-1][-1] <= separacion:
            grupos[-1].append(borde)
        else:
            grupos.append([borde])
    return [float(np.mean(g)) for g in grupos if len(g) >= 3]


def tabla_a_dataframe(imagen: np.ndarray, lang: str = "spa", oem: int = 1, psm: int = 6) -> pd.DataFrame:
    """Lee una tabla de conceptos y cifras (como un balance) y la entrega como DataFrame.

    Lee la página dos veces (en gris y en blanco y negro) y se queda con la lectura de mayor confianza.

    Args:
        imagen: página enderezada (gris o RGB) que contiene la tabla.
        lang: idioma de Tesseract.
        oem: motor de Tesseract.
        psm: modo de segmentación de Tesseract.

    Returns:
        Tabla con la columna ``Concepto`` y una columna numérica por cada encabezado
        (por ejemplo "2026" y "2025"). Las filas sin cifras (ACTIVO, PASIVO) quedan con NaN. Si la tabla no
        tiene una fila de encabezado que empiece con "Concepto", las columnas se llaman "Valor 1", "Valor 2"...
    """
    limpia, _ = quitar_lineas(mediana(a_gris(imagen), 3))
    lecturas = [leer_con_confianza(candidata, lang, oem, psm) for candidata in (limpia, adaptativa(limpia))]
    filas = agrupar_filas(max(lecturas, key=lambda lectura: lectura["confianza"])["palabras"])
    anclas = columnas_numericas(filas)
    hay_encabezado = any(" ".join(p["texto"] for p in fila).lower().startswith("concepto") for fila in filas)
    registros, encabezados = [], (None if hay_encabezado else [])
    for fila in filas:
        textos = [p for p in fila if not RE_NUMERO.fullmatch(p["texto"])]
        cifras = [p for p in fila if RE_NUMERO.fullmatch(p["texto"])]
        concepto = " ".join(p["texto"] for p in textos)
        valores = [float("nan")] * len(anclas)
        for p in cifras:
            if anclas:
                posicion = int(np.argmin([abs(p["caja"][2] - ancla) for ancla in anclas]))
                valores[posicion] = a_numero(p["texto"])
        if encabezados is None:
            if concepto.lower().startswith("concepto"):
                encabezados = [p["texto"] for p in cifras] if len(cifras) == len(anclas) else []
            continue
        if cifras or concepto.isupper():
            registros.append([concepto] + valores)
    if not encabezados or len(set(encabezados)) < len(encabezados):
        encabezados = [f"Valor {i + 1}" for i in range(len(anclas))]
    return pd.DataFrame(registros, columns=["Concepto"] + encabezados)


def cuadratura(tabla: pd.DataFrame, columna: str) -> dict:
    """Comprueba que Activo = Pasivo + Patrimonio en una columna del balance.

    Busca las filas "Total activo", "Total pasivo" y "Total patrimonio" aunque el OCR las lea con algún error.

    Returns:
        Diccionario con ``activo``, ``pasivo``, ``patrimonio`` (None si falta la fila), ``diferencia`` y ``cuadra``.
    """
    totales = {}
    for clave in ("activo", "pasivo", "patrimonio"):
        puntajes = tabla["Concepto"].map(lambda c: fuzz.ratio(c.lower(), f"total {clave}"))
        mejor = puntajes.idxmax() if len(puntajes) else None
        valor = tabla.loc[mejor, columna] if mejor is not None and puntajes[mejor] >= 80 else None
        totales[clave] = None if valor is None or pd.isna(valor) else float(valor)
    if None in totales.values():
        return {**totales, "diferencia": None, "cuadra": False}
    diferencia = totales["activo"] - totales["pasivo"] - totales["patrimonio"]
    return {**totales, "diferencia": diferencia, "cuadra": diferencia == 0}
