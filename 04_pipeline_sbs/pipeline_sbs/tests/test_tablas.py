"""Pruebas de ocr.tablas: líneas, filas, cuadratura y lectura de una tabla sintética."""
import numpy as np
import pandas as pd
import pytest
from PIL import Image, ImageDraw, ImageFont

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.ocr.tablas import a_numero, agrupar_filas, cuadratura, quitar_lineas, tabla_a_dataframe
from pipeline_sbs.orquestacion.pipeline_ocr import configurar_tesseract

FILAS = [("Concepto", "2026", "2025"), ("Disponible", "7,113", "5,874"), ("Inversiones", "355", "391"),
         ("Total activo", "35,569", "39,161"), ("Total pasivo", "30,120", "32,520"),
         ("Total patrimonio", "5,449", "6,641"), ("Total pasivo y patrimonio", "35,569", "39,161")]


def tabla_sintetica() -> np.ndarray:
    """Imagen con una tabla de bordes: concepto a la izquierda y dos columnas de cifras a la derecha."""
    imagen = Image.new("L", (1500, 1500), 255)
    dibujo = ImageDraw.Draw(imagen)
    letra = ImageFont.load_default(size=36)
    for i, (concepto, a, b) in enumerate(FILAS):
        y = 40 + i * 80
        dibujo.text((60, y + 15), concepto, fill=0, font=letra)
        dibujo.text((1150 - dibujo.textlength(a, font=letra), y + 15), a, fill=0, font=letra)
        dibujo.text((1440 - dibujo.textlength(b, font=letra), y + 15), b, fill=0, font=letra)
        dibujo.line([(40, y), (1460, y)], fill=0, width=3)
    dibujo.line([(40, 40 + len(FILAS) * 80), (1460, 40 + len(FILAS) * 80)], fill=0, width=3)
    for x in (40, 800, 1180, 1460):
        dibujo.line([(x, 40), (x, 40 + len(FILAS) * 80)], fill=0, width=3)
    return np.array(imagen)


def test_a_numero():
    assert a_numero("35,569") == 35569.0
    assert np.isnan(a_numero("3S,569"))


def test_quitar_lineas_cuenta_las_horizontales():
    limpia, horizontales = quitar_lineas(tabla_sintetica())
    assert horizontales == len(FILAS) + 1
    assert limpia.shape == (1500, 1500)


def test_agrupar_filas_une_las_palabras_de_una_misma_fila():
    palabras = [{"texto": "Total", "caja": (0, 10, 50, 40)}, {"texto": "activo", "caja": (60, 12, 120, 42)},
                {"texto": "35,569", "caja": (300, 11, 380, 41)}, {"texto": "Otros", "caja": (0, 100, 50, 130)}]
    filas = agrupar_filas(palabras)
    assert [len(f) for f in filas] == [3, 1]


def test_cuadratura_cuadra_y_no_cuadra():
    tabla = pd.DataFrame({"Concepto": ["Total activo", "Total pasivo", "Total patrimonio"], "2026": [100.0, 70.0, 30.0]})
    assert cuadratura(tabla, "2026")["cuadra"] is True
    tabla.loc[2, "2026"] = 31.0
    resultado = cuadratura(tabla, "2026")
    assert resultado["cuadra"] is False and resultado["diferencia"] == -1.0


def test_cuadratura_tolera_un_error_de_ocr_en_el_nombre():
    tabla = pd.DataFrame({"Concepto": ["Totai activo", "Total pasivo", "Total patrimonio"], "2026": [100.0, 70.0, 30.0]})
    assert cuadratura(tabla, "2026")["cuadra"] is True


def test_cuadratura_sin_filas_de_totales():
    tabla = pd.DataFrame({"Concepto": ["Disponible"], "2026": [5.0]})
    assert cuadratura(tabla, "2026")["cuadra"] is False


def test_tabla_a_dataframe_lee_una_tabla_sintetica():
    try:
        configurar_tesseract(cargar_configuracion())
    except RuntimeError:
        pytest.skip("Tesseract no está instalado en esta máquina")
    tabla = tabla_a_dataframe(tabla_sintetica())
    assert list(tabla.columns) == ["Concepto", "2026", "2025"]
    assert cuadratura(tabla, "2026")["cuadra"] is True
