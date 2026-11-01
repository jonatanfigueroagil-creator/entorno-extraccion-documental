"""Pruebas de la normalización: Unicode, espacios, guiones de corte, fechas y montos en soles."""
import unicodedata
from datetime import date
from decimal import Decimal

import pytest

from pipeline_sbs.preprocesamiento.normalizacion import (
    normalizar_texto,
    parsear_fecha,
    parsear_monto,
    unir_guiones,
)


def test_nfc_hace_iguales_dos_cadenas_que_se_ven_iguales():
    compuesta = "café"
    descompuesta = "café"
    assert compuesta != descompuesta
    assert normalizar_texto(descompuesta) == normalizar_texto(compuesta) == compuesta


def test_nfkc_cambia_el_contenido_y_normalizar_texto_no_lo_hace():
    assert unicodedata.normalize("NFKC", "Oficio Nº 123") == "Oficio No 123"
    assert normalizar_texto("Oficio Nº 123") == "Oficio Nº 123"


def test_espacios_especiales_invisibles_y_ligaduras():
    sucio = "S/ 1 250,00  \t total​­  ﬁnanciero\r\nlinea  dos "
    assert normalizar_texto(sucio) == "S/ 1 250,00 total financiero\nlinea dos"


def test_normalizar_texto_rechaza_no_cadenas():
    with pytest.raises(TypeError):
        normalizar_texto(123)  # type: ignore[arg-type]


def test_unir_guiones_une_palabras_cortadas():
    assert unir_guiones("la pala-\nbra cortada") == "la palabra cortada"
    assert unir_guiones("informa-  \n  cion") == "informacion"


def test_unir_guiones_limitaciones_documentadas():
    assert unir_guiones("socio-\neconomico") == "socioeconomico"       # falso positivo conocido
    assert unir_guiones("Ley 28-\nA") == "Ley 28-\nA"                  # no une si no es letra + minúscula
    assert unir_guiones("plazo - \nSiguiente") == "plazo - \nSiguiente"


@pytest.mark.parametrize("texto, esperado", [
    ("11/08/2026", date(2026, 8, 11)),
    ("11-08-2026", date(2026, 8, 11)),
    ("2026-08-11", date(2026, 8, 11)),
    ("Lima, 11 de agosto de 2026", date(2026, 8, 11)),
    ("Al 31 de Diciembre del 2026", date(2026, 12, 31)),
    ("5 de setiembre de 2026", date(2026, 9, 5)),
    ("vence el 1/2/2026.", date(2026, 2, 1)),
])
def test_parsear_fecha_formatos(texto, esperado):
    assert parsear_fecha(texto) == esperado


@pytest.mark.parametrize("texto", ["31/02/2026", "sin fecha", "13/13/2026", "11 de brumario de 2026", ""])
def test_parsear_fecha_devuelve_none(texto):
    assert parsear_fecha(texto) is None


@pytest.mark.parametrize("texto, esperado", [
    ("S/ 1 250,00", Decimal("1250.00")),
    ("S/ 1 250,00", Decimal("1250.00")),
    ("S/ 8,861.00", Decimal("8861.00")),
    ("MONTO S/ 8,861.00", Decimal("8861.00")),
    ("1.250,50", Decimal("1250.50")),
    ("S/. 1250", Decimal("1250")),
    ("4,143", Decimal("4143")),
    ("1,25", Decimal("1.25")),
    ("(1,250)", Decimal("-1250")),
    ("S/ -50.00", Decimal("-50.00")),
])
def test_parsear_monto_formatos(texto, esperado):
    assert parsear_monto(texto) == esperado


@pytest.mark.parametrize("texto", ["sin numero", "S/", ""])
def test_parsear_monto_devuelve_none(texto):
    assert parsear_monto(texto) is None


def test_normalizar_texto_del_corpus(datos_practica):
    import json

    verdad = json.loads((datos_practica / "10_Ground_Truth" / "EFI-0001.json").read_text(encoding="utf-8"))
    texto = verdad["texto_completo"]
    assert normalizar_texto(texto) == texto            # el texto del corpus ya viene normalizado
    assert parsear_monto("S/ " + verdad["tablas"][0]["filas"][1][1]) == Decimal(
        verdad["tablas"][0]["filas"][1][1].replace(",", "")
    )
