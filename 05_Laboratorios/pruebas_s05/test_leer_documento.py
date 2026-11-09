"""Pruebas de ingesta/leer_documento.py (no necesitan GPU)."""
import pymupdf
import pytest

from mi_pipeline.ingesta.leer_documento import FormatoNoSoportado, a_iso, a_numero, leer_documento, normalizar


def test_a_iso_lleva_tres_formas_de_fecha_a_aaaa_mm_dd():
    assert a_iso("24 de junio de 2026") == a_iso("24/06/2026") == a_iso("Lima, 2026-06-24") == "2026-06-24"


def test_a_numero_quita_el_simbolo_y_las_comas():
    assert a_numero("S/ 2,643.00") == 2643.0


def test_normalizar_rechaza_un_ruc_con_un_digito_cambiado():
    assert normalizar("ruc", "RUC 20992371634") == "20992371634" and normalizar("ruc", "20992371635") is None


def test_una_pagina_sin_texto_queda_pendiente_de_ocr(tmp_path):
    ruta = tmp_path / "escaneado.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(str(ruta))
    pdf.close()
    doc = leer_documento(ruta)
    assert doc["partes"] == [""] and doc["pendientes"][0]["origen"] == "PDF página 1"


def test_un_doc_antiguo_responde_formato_no_soportado(tmp_path):
    ruta = tmp_path / "politica.doc"
    ruta.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(FormatoNoSoportado):
        leer_documento(ruta)
