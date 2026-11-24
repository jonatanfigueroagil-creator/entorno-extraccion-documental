"""Pruebas de calidad.metricas: CER e IoU (3 casos de cada uno, más los bordes)."""
import unicodedata

import pytest

from pipeline_sbs.calidad.metricas import cer, iou


def test_cer_textos_iguales():
    assert cer("Banco Andino DEMO", "Banco Andino DEMO") == 0.0


def test_cer_una_sustitucion_en_diez_caracteres():
    assert cer("0123456789", "0123456780") == pytest.approx(0.1)


def test_cer_borra_todo_el_texto():
    assert cer("abcd", "") == 1.0


def test_cer_ignora_espacios_repetidos_y_normaliza_nfc():
    assert cer("acción  total", unicodedata.normalize("NFD", "acción total")) == 0.0


def test_cer_referencia_vacia():
    assert cer("", "") == 0.0
    assert cer("", "ruido") == 1.0


def test_iou_cajas_identicas():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_iou_cajas_mitad():
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_iou_cajas_sin_cruce():
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_iou_caja_sin_area():
    assert iou((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0
