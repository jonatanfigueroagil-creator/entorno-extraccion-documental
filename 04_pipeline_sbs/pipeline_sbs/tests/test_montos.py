"""Pruebas de extraccion.montos: montos en cifras, en palabras y en la tabla del adjunto."""
import pytest

from pipeline_sbs.extraccion.montos import (
    extraer_monto,
    extraer_monto_cifras,
    extraer_monto_palabras,
    extraer_monto_tabla,
    monto_a_numero,
)


@pytest.mark.parametrize("palabras,esperado", [
    ("dos mil seiscientos cuarenta y tres", 2643),
    ("cien", 100),
    ("ciento un", 101),
    ("mil", 1000),
    ("mil cuarenta y siete", 1047),
    ("veintiún mil", 21000),
    ("quinientos cincuenta y siete soles", 557),
    ("dieciséis", 16),
])
def test_monto_a_numero_convierte_palabras_en_espanol(palabras, esperado):
    assert monto_a_numero(palabras) == esperado


def test_monto_a_numero_devuelve_none_si_hay_una_palabra_ajena():
    assert monto_a_numero("dos mil pesos") is None
    assert monto_a_numero("") is None


def test_extraer_monto_cifras_lee_soles_con_coma_de_miles():
    assert extraer_monto_cifras("Me cargaron S/ 2,643.00 en mi cuenta") == 2643.0
    assert extraer_monto_cifras("Fueron S/ 450 en mi tarjeta") == 450.0
    assert extraer_monto_cifras("Fueron dos mil soles") is None


def test_extraer_monto_palabras_busca_el_numero_antes_de_soles():
    assert extraer_monto_palabras("Fueron dos mil seiscientos cuarenta y tres soles en mi prestamo") == 2643.0
    assert extraer_monto_palabras("El monto es quinientos cincuenta y siete soles, el dia 10/09") == 557.0
    assert extraer_monto_palabras("Pasé tres veces por la agencia") is None


def test_extraer_monto_tabla_lee_la_fila_del_cargo_reclamado():
    texto = "10/09/2026 Cargo reclamado (demora en entrega) 2,643.00\n03/09/2026 Interes 290.00"
    assert extraer_monto_tabla(texto) == 2643.0


def test_extraer_monto_sin_palabras_pierde_los_montos_escritos_en_palabras():
    texto = "Fueron dos mil seiscientos cuarenta y tres soles"
    assert extraer_monto(texto, palabras=False) is None
    assert extraer_monto(texto) == 2643.0
