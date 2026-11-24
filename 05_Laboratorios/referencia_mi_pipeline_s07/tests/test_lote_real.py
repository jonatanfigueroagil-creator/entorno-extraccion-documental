"""Pruebas de extraccion/lote_real.py (no necesitan el lote real)."""
from mi_pipeline.extraccion.lote_real import extraer_empresa, extraer_fecha_presentacion, normalizar_empresa


def test_normalizar_empresa_quita_parentesis_y_sociedad():
    assert normalizar_empresa("EMPRESA EJEMPLO S.A.A. (ANTES EMPRESA ANTERIOR)") == "EMPRESA EJEMPLO"


def test_extraer_empresa_de_un_titulo_de_politica():
    assert normalizar_empresa(extraer_empresa("Política de Dividendos de EMPRESA EJEMPLO para el año 2026")) == "EMPRESA EJEMPLO"


def test_extraer_fecha_presentacion_lee_el_sello():
    assert extraer_fecha_presentacion("Fecha: 16/03/2026 04:38:16 p.m.") == "2026-03-16"
