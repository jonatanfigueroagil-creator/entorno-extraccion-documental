"""Pruebas de orquestacion.pipeline_ocr: configuración de Tesseract, enrutamiento y ejecución."""
import pytest

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.orquestacion.pipeline_ocr import configurar_tesseract, ejecutar_ocr, enrutar
from pipeline_sbs.tests.conftest import crear_pdf_con_texto


def test_configuracion_trae_las_claves_de_s03():
    cfg = cargar_configuracion()
    assert cfg["ocr"]["tesseract_cmd"] == ""
    assert (cfg["ocr"]["lang"], cfg["ocr"]["oem"], cfg["ocr"]["psm"], cfg["ocr"]["psm_pagina"], cfg["ocr"]["dpi"]) == ("spa", 1, 6, 3, 300)
    assert cfg["ocr"]["receta"] in ("crudo", "gris", "otsu", "adaptativa", "mediana")
    assert 0 < cfg["calidad"]["umbral_score"] <= 1


def test_enrutar_acepta_revisa_y_rechaza():
    assert enrutar({"score": 0.95, "invalidos": 0}, 0.8) == "aceptar"
    assert enrutar({"score": 0.95, "invalidos": 1}, 0.8) == "revisar"   # confianza alta pero un campo inválido
    assert enrutar({"score": 0.55, "invalidos": 0}, 0.8) == "revisar"
    assert enrutar({"score": 0.2, "invalidos": 0}, 0.8) == "rechazar"


def test_configurar_tesseract_usa_la_clave_del_yaml(monkeypatch):
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    assert configurar_tesseract({"ocr": {"tesseract_cmd": "mi_tesseract"}}) == "mi_tesseract"


def test_configurar_tesseract_la_variable_de_entorno_manda(monkeypatch):
    monkeypatch.setenv("TESSERACT_CMD", "otro_tesseract")
    assert configurar_tesseract({"ocr": {"tesseract_cmd": "mi_tesseract"}}) == "otro_tesseract"


def test_ejecutar_ocr_lee_un_pdf(tmp_path, caplog):
    try:
        configurar_tesseract(cargar_configuracion())
    except RuntimeError:
        pytest.skip("Tesseract no está instalado en esta máquina")
    pdf = crear_pdf_con_texto(tmp_path / "oficio.pdf", "Oficio DEMO 24 de junio de 2026 RUC 20992371634")
    with caplog.at_level("INFO", logger="pipeline_sbs"):
        resultado = ejecutar_ocr(pdf, enderezar=False)
    eventos = [r.getMessage() for r in caplog.records]
    assert eventos == ["etapa_preprocesar", "etapa_leer"]   # un evento por etapa
    assert "20992371634" in resultado["texto"]
    assert resultado["decision"] in ("aceptar", "revisar", "rechazar")
    assert resultado["puntaje"]["validos"] >= 1
