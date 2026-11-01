"""Pruebas de ocr.renderizar: PDF a imagen."""
import numpy as np
import pytest

from pipeline_sbs.ocr.renderizar import pdf_a_imagen
from pipeline_sbs.tests.conftest import crear_pdf_con_texto


def test_pdf_a_imagen_300_dpi(tmp_path):
    pdf = crear_pdf_con_texto(tmp_path / "hoja.pdf", "Oficio DEMO")
    imagen = pdf_a_imagen(pdf, dpi=300)
    assert imagen.shape == (3300, 2550, 3)  # carta: 8,5 x 11 pulgadas a 300 dpi
    assert imagen.dtype == np.uint8


def test_pdf_a_imagen_menos_dpi_menos_pixeles(tmp_path):
    pdf = crear_pdf_con_texto(tmp_path / "hoja.pdf", "Oficio DEMO")
    assert pdf_a_imagen(pdf, dpi=100).shape == (1100, 850, 3)


def test_pdf_a_imagen_hoja_con_texto_no_es_blanca(tmp_path):
    pdf = crear_pdf_con_texto(tmp_path / "hoja.pdf", "Oficio DEMO")
    assert pdf_a_imagen(pdf, dpi=100).min() < 100


def test_pdf_a_imagen_errores(tmp_path):
    with pytest.raises(FileNotFoundError):
        pdf_a_imagen(tmp_path / "no_existe.pdf")
    pdf = crear_pdf_con_texto(tmp_path / "hoja.pdf", "Oficio DEMO")
    with pytest.raises(IndexError):
        pdf_a_imagen(pdf, pagina=3)
