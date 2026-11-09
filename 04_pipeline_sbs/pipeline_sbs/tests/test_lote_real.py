"""Pruebas de extraccion.lote_real: reglas de empresa y fecha, normalización y comparación con la ficha (el lote real es opcional)."""
import pytest

from pipeline_sbs.extraccion.lote_real import (
    campos_desde_ner,
    extraer_empresa,
    extraer_fecha_presentacion,
    localizar_lote,
    medir_lote_real,
    normalizar_empresa,
    texto_a_fecha,
)


@pytest.mark.parametrize("texto,esperado", [
    ("EMPRESA EJEMPLO S.A.A. (ANTES EMPRESA ANTERIOR)", "EMPRESA EJEMPLO"),
    ("Administradora Jockey Plaza Shopping Center S.A.", "ADMINISTRADORA JOCKEY PLAZA SHOPPING CENTER"),
    ("Empresa Modelo S.A.", "EMPRESA MODELO"),
    ("Empresa Ñandú S.A.A.", "EMPRESA NANDU"),
    ("", None),
])
def test_normalizar_empresa_quita_tildes_parentesis_y_sociedad(texto, esperado):
    assert normalizar_empresa(texto) == esperado


def test_texto_a_fecha_acepta_numerica_y_larga():
    assert texto_a_fecha("16/03/2026") == "2026-03-16"
    assert texto_a_fecha("el 23 de Julio de 2020 se aprobó") == "2020-07-23"
    assert texto_a_fecha("31/02/2026") is None


def test_extraer_empresa_en_tres_formatos_de_politica():
    assert normalizar_empresa(extraer_empresa("EMPRESA\nEJEMPLO\nUNO S.A.A.\nPOLÍTICA DE DIVIDENDOS")) == "EMPRESA EJEMPLO UNO"
    assert normalizar_empresa(extraer_empresa("Política de Dividendos de EMPRESA EJEMPLO para el año 2026")) == "EMPRESA EJEMPLO"
    assert normalizar_empresa(extraer_empresa("Esta política rige para Banco Andino DEMO S.A. desde hoy")) == "BANCO ANDINO DEMO"
    assert extraer_empresa("Nueva Política de Dividendos aprobada en Junta") is None


def test_extraer_fecha_prefiere_el_sello_y_si_no_la_fecha_escrita():
    assert extraer_fecha_presentacion("Aprobado el 31 de marzo de 2025.\nFecha: 16/03/2026 04:38:16 p.m.") == "2026-03-16"
    assert extraer_fecha_presentacion("Junta del 31 de marzo de 2010 acordó") == "2010-03-31"
    assert extraer_fecha_presentacion("sin fecha") is None


def test_campos_desde_ner_descarta_personas():
    ents = [{"texto": "Ana Ruiz", "etiqueta": "PER", "score": 1.0},
            {"texto": "Banco Andino DEMO S.A.", "etiqueta": "ORG", "score": 0.9},
            {"texto": "31 de marzo de 2010", "etiqueta": "DATE", "score": 0.9}]
    assert campos_desde_ner(ents) == {"empresa": "Banco Andino DEMO S.A.", "fecha": "2010-03-31"}


def test_sin_lote_real_no_falla(monkeypatch, tmp_path):
    monkeypatch.setenv("SBS_LOTE_REAL", str(tmp_path / "no_existe"))
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    assert localizar_lote("carpeta/que/no/existe") is None
    assert medir_lote_real(None) is None


def test_medir_lote_real_sobre_el_lote_si_existe():
    lote = localizar_lote()
    if lote is None:
        pytest.skip("No hay lote público real en esta máquina (variable SBS_LOTE_REAL o carpeta curso/datos/14_Publico_Real)")
    pytest.importorskip("transformers")
    medidas = medir_lote_real(lote, dispositivo="cpu")
    assert len(medidas["documentos"]) == 7
    assert set(medidas["f1"]) == {"reglas", "spaCy", "Transformers"}
    assert medidas["f1"]["reglas"]["fecha"] >= 0.8
