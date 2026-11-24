"""Pruebas de las métricas."""
import pytest

from mi_pipeline.calidad.metricas import cer


def test_cer_textos_iguales():
    assert cer("Banco Andino DEMO", "Banco Andino DEMO") == 0.0


def test_cer_una_sustitucion_en_diez_caracteres():
    assert cer("0123456789", "0123456780") == pytest.approx(0.1)


def test_cer_texto_borrado():
    assert cer("abcd", "") == 1.0
