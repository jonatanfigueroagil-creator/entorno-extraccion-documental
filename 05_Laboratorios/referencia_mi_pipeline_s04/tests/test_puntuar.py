"""Pruebas de los validadores y del puntaje."""
from mi_pipeline.calidad.puntuar import puntuar, validar_monto, validar_ruc


def test_validar_ruc_acepta_uno_correcto_y_rechaza_uno_con_un_digito_cambiado():
    assert validar_ruc("20992371634") and not validar_ruc("20992371635")


def test_validar_monto_acepta_la_coma_de_miles_y_rechaza_una_coma_mal_puesta():
    assert validar_monto("S/ 1,250.00") and not validar_monto("1,25.00")


def test_puntuar_baja_el_score_si_un_ruc_es_invalido():
    texto = "Lima, 24 de junio de 2026\nRUC 20992371635\nMONTO S/ 16,798.00"
    assert puntuar(texto, 0.9)["invalidos"] == 1 and puntuar(texto, 0.9)["score"] < 0.8
