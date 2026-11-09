"""Pruebas de extraccion.reglas: regex y EntityRuler."""
import pytest

from pipeline_sbs.extraccion.reglas import (
    extraer_correo_electronico,
    extraer_dni,
    extraer_entidad,
    extraer_fecha,
    extraer_motivo,
    extraer_nombre,
    extraer_numero_oficio,
    extraer_producto,
    extraer_ruc,
    extraer_telefono,
    modelo_con_reglas,
)


def test_extraer_dni_exacto_y_con_letras_del_ocr():
    assert extraer_dni("soy Ana, DNI 99123456. Gracias") == "99123456"
    assert extraer_dni("Cliente: Ana Ruiz DNI 99O23l56") == "99023156"   # O por 0 y l por 1
    assert extraer_dni("DNI 123456") is None
    assert extraer_dni("telefono 999000123456789") is None


def test_extraer_fecha_prefiere_la_fila_del_cargo_reclamado():
    texto = "09/09/2026 Interes 226.00\n10/09/2026 Cargo reclamado (demora en entrega) 2,643.00\n11/09/2026 Pago"
    assert extraer_fecha(texto) == "2026-09-10"


def test_extraer_fecha_sin_fila_toma_la_mas_reciente_y_no_acepta_fechas_parciales():
    assert extraer_fecha("03/09/2026 Interes\n10/09/2026 Pago\n06/09/2026 Interes") == "2026-09-10"
    assert extraer_fecha("el dia 10/09 me cobraron") is None
    assert extraer_fecha("31/02/2026") is None


def test_extraer_ruc_acepta_el_valido_y_rechaza_un_digito_cambiado():
    assert extraer_ruc("Senores\nRUC 20992371634\nPresente") == "20992371634"
    ruc = "20992371634"
    invalido = ruc[:-1] + "5"
    assert extraer_ruc(f"RUC {invalido}") is None
    assert extraer_ruc(f"RUC {invalido} y RUC {ruc}") == ruc


def test_extraer_numero_oficio_corrige_id_leido_como_1d():
    assert extraer_numero_oficio("OFICIO N* 0230-2026-1D/DSF") == "0230-2026-ID/DSF"
    assert extraer_numero_oficio("OFICIO N° 0955-2026-ID/DCM") == "0955-2026-ID/DCM"
    assert extraer_numero_oficio("Oficio sin numero") is None


def test_extraer_telefono_y_correo():
    assert extraer_telefono("Mi cel es 999 000 680.") == "999 000 680"
    assert extraer_telefono("Mi cel es 987 654 321") is None
    assert extraer_correo_electronico("escribir a jorge.fuentes6@ejemplo.pe por favor") == "jorge.fuentes6@ejemplo.pe"
    assert extraer_correo_electronico("sin correo") is None


@pytest.mark.parametrize("texto,esperado", [
    ("En Banco Cordillera DEMO S.A. pedi mi tarjeta", "Banco Cordillera DEMO S.A."),
    ("Senores de Banco del Sur Austral DEMO S.A.: reclamo", "Banco del Sur Austral DEMO S.A."),
    ("Caja Rural Valle Verde DEMO S.A,\nEstado de cuenta", "Caja Rural Valle Verde DEMO S.A"),
    ("me cobraron en el banco", None),
])
def test_extraer_entidad(texto, esperado):
    assert extraer_entidad(texto) == esperado


@pytest.mark.parametrize("texto,esperado", [
    ("Buenas, soy Jorge Fuentes Bravo, DNI 99929470.", "Jorge Fuentes Bravo"),
    ("Solicito la devolucion. Atte. Ana Ruiz Soto (DNI 99111111).", "Ana Ruiz Soto"),
    ("Cliente: Pedro Salazar Montoya DNI 99703460", "Pedro Salazar Montoya"),
    ("Me atendieron mal. Carmen Paredes Ramos, DNI 99197515, correo x@ejemplo.pe", "Carmen Paredes Ramos"),
    ("sin datos personales", None),
])
def test_extraer_nombre(texto, esperado):
    assert extraer_nombre(texto) == esperado


def test_extraer_producto_y_motivo():
    assert extraer_producto("Fueron S/ 100 en mi Prestamo Personal y mi cuenta sueldo") == "prestamo personal"
    assert extraer_producto("sin producto") is None
    assert extraer_motivo("10/09/2026 Cargo reclamado (Demora en entrega) 2,643.00") == "demora en entrega"
    assert extraer_motivo("sin cargo") is None


def test_entity_ruler_marca_dni_telefono_y_producto():
    try:
        nlp = modelo_con_reglas()
    except OSError:
        pytest.skip("No está instalado ningún modelo de spaCy en español")
    doc = nlp("Mi DNI es 99929470, mi cel 999 000 680 y mi cuenta de ahorros.")
    etiquetas = {e.text: e.label_ for e in doc.ents}
    assert etiquetas["99929470"] == "DNI"
    assert etiquetas["999 000 680"] == "TELEFONO"
    assert etiquetas["cuenta de ahorros"] == "PRODUCTO"
