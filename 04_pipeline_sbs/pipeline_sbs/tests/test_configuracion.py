"""Pruebas de la configuración y del logger."""
import logging

import pytest

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.monitoreo.registro import obtener_logger


def test_configuracion_por_defecto():
    cfg = cargar_configuracion()
    assert cfg["ocr"]["idioma"] == "spa"
    assert cfg["llm"]["backend"] == "ollama_local"
    assert ".pdf" in cfg["ingesta"]["extensiones"]


def test_configuracion_propia(tmp_path):
    archivo = tmp_path / "otra.yaml"
    archivo.write_text(
        "ocr: {idioma: eng}\ningesta: {extensiones: ['.pdf']}\nllm: {backend: api_nube}\nlogging: {nivel: DEBUG}\n",
        encoding="utf-8",
    )
    assert cargar_configuracion(archivo)["ocr"]["idioma"] == "eng"


def test_configuracion_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_configuracion(tmp_path / "no_existe.yaml")


def test_configuracion_sin_clave_obligatoria(tmp_path):
    archivo = tmp_path / "incompleta.yaml"
    archivo.write_text("ocr: {idioma: spa}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ingesta"):
        cargar_configuracion(archivo)


def test_logger_sin_manejadores_duplicados():
    a = obtener_logger("pipeline_sbs.prueba")
    b = obtener_logger("pipeline_sbs.prueba")
    assert a is b and len(a.handlers) == 1
    assert a.level == logging.INFO


def test_logger_nivel_invalido():
    with pytest.raises(ValueError):
        obtener_logger("pipeline_sbs.prueba2", nivel="RUIDOSO")
