"""Pruebas de extraccion/reglas.py."""
from mi_pipeline.extraccion.reglas import extraer_dni, extraer_fecha, extraer_numero_oficio, extraer_ruc


def test_extraer_dni_exacto():
    assert extraer_dni("soy Ana, DNI 99123456. Gracias") == "99123456"


def test_extraer_dni_corrige_letras_del_ocr():
    assert extraer_dni("Cliente: Ana Ruiz DNI 99O23l56") == "99023156"


def test_extraer_fecha_toma_la_fila_del_cargo_reclamado():
    assert extraer_fecha("09/09/2026 Interes 226.00\n10/09/2026 Cargo reclamado (demora en entrega) 2,643.00") == "2026-09-10"


def test_extraer_ruc_rechaza_un_digito_cambiado():
    ruc = "20992371634"
    assert extraer_ruc(f"RUC {ruc[:-1] + '5'}") is None


def test_extraer_numero_oficio_corrige_1d_por_id():
    assert extraer_numero_oficio("OFICIO N* 0230-2026-1D/DSF") == "0230-2026-ID/DSF"
