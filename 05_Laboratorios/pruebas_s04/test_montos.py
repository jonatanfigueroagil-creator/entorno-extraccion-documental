"""Pruebas de extraccion/montos.py."""
from mi_pipeline.extraccion.montos import extraer_monto, monto_a_numero


def test_monto_a_numero_convierte_palabras_en_espanol():
    assert monto_a_numero("dos mil seiscientos cuarenta y tres") == 2643


def test_extraer_monto_sin_palabras_pierde_el_monto_escrito_en_palabras():
    assert extraer_monto("Fueron dos mil soles", palabras=False) is None


def test_extraer_monto_lee_cifras_con_coma_de_miles():
    assert extraer_monto("Me cargaron S/ 2,643.00 en mi cuenta") == 2643.0
