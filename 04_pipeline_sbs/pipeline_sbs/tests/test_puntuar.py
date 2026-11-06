"""Pruebas de calidad.puntuar: validadores de RUC, fecha y monto, y puntaje."""
import pytest

from pipeline_sbs.calidad.puntuar import puntuar, validar_fecha, validar_monto, validar_ruc


@pytest.mark.parametrize("ruc, esperado", [
    ("20992371634", True),     # RUC del corpus (módulo 11 correcto)
    ("20992371635", False),    # un dígito final distinto
    ("2099237163", False),     # le falta un dígito
    ("30992371634", False),    # prefijo que no existe
    ("2O992371634", False),    # letra O en lugar de cero (error típico del OCR)
])
def test_validar_ruc(ruc, esperado):
    assert validar_ruc(ruc) is esperado


@pytest.mark.parametrize("fecha, esperado", [
    ("24/06/2026", True), ("2026-06-24", True), ("24 de junio de 2026", True),
    ("31 de junio de 2026", False), ("32/01/2026", False), ("24 de junlo de 2026", False),
])
def test_validar_fecha(fecha, esperado):
    assert validar_fecha(fecha) is esperado


@pytest.mark.parametrize("monto, esperado", [
    ("S/ 1,250.00", True), ("35,569", True), ("16798", True), ("1,25.00", False), ("1.250,00", False), ("S/ abc", False),
])
def test_validar_monto(monto, esperado):
    assert validar_monto(monto) is esperado


TEXTO_BUENO = "OFICIO N° 0230-2026\nLima, 24 de junio de 2026\nRUC 20992371634\nMONTO S/ 16,798.00"


def test_puntuar_lectura_buena():
    puntaje = puntuar(TEXTO_BUENO, 0.9)
    assert puntaje["validos"] == 3 and puntaje["invalidos"] == 0
    assert puntaje["score"] == pytest.approx(0.95)


def test_puntuar_ruc_invalido_baja_el_score_aunque_la_confianza_sea_alta():
    puntaje = puntuar(TEXTO_BUENO.replace("20992371634", "20992371635"), 0.9)
    assert puntaje["invalidos"] == 1
    assert puntaje["score"] < 0.8


def test_puntuar_texto_sin_campos():
    assert puntuar("xx ,, ;; ##", 0.3)["score"] == pytest.approx(0.15)
