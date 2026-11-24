"""Pruebas del registro en formato JSON y de la configuración nueva de S02."""
import io
import json
import logging

import pytest

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.ingesta.cargador import CargadorDocumentos
from pipeline_sbs.monitoreo.registro import FormateadorJson, enmascarar_dni, obtener_logger


def _logger_con_salida(nombre: str) -> tuple[logging.Logger, io.StringIO]:
    salida = io.StringIO()
    logger = logging.getLogger(nombre)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    manejador = logging.StreamHandler(salida)
    manejador.setFormatter(FormateadorJson())
    logger.addHandler(manejador)
    return logger, salida


def test_cada_evento_es_una_linea_json_con_sus_campos():
    logger, salida = _logger_con_salida("prueba.json.campos")
    logger.warning("archivo_procesado", extra={"archivo": "LOT-0007.pdf", "estado": "fallo", "motivo": "pdf_cifrado",
                                               "formato": "pdf", "segundos": 0.0123})
    lineas = salida.getvalue().strip().splitlines()
    assert len(lineas) == 1
    evento = json.loads(lineas[0])
    assert evento["nivel"] == "WARNING" and evento["mensaje"] == "archivo_procesado"
    assert (evento["archivo"], evento["estado"], evento["motivo"], evento["formato"]) == (
        "LOT-0007.pdf", "fallo", "pdf_cifrado", "pdf")
    assert evento["segundos"] == 0.0123 and evento["ts"].endswith("+00:00")


def test_las_tildes_se_conservan_y_las_excepciones_se_incluyen():
    logger, salida = _logger_con_salida("prueba.json.excepcion")
    try:
        raise ValueError("ñandú")
    except ValueError:
        logger.exception("falló ñandú")
    evento = json.loads(salida.getvalue())
    assert evento["mensaje"] == "falló ñandú" and "ValueError" in evento["excepcion"]


def test_el_dni_se_enmascara_en_mensaje_y_campos():
    assert enmascarar_dni("DNI 99386133 y operación 123") == "DNI ******33 y operación 123"
    logger, salida = _logger_con_salida("prueba.json.dni")
    logger.info("cliente 99386133", extra={"detalle": "titular 99386133"})
    evento = json.loads(salida.getvalue())
    assert "99386133" not in salida.getvalue()
    assert evento["mensaje"] == "cliente ******33" and evento["detalle"] == "titular ******33"


def test_obtener_logger_json_y_formato_invalido():
    logger = obtener_logger("pipeline_sbs.prueba_json", formato="json")
    assert isinstance(logger.handlers[0].formatter, FormateadorJson)
    again = obtener_logger("pipeline_sbs.prueba_json", formato="simple")
    assert again is logger and len(logger.handlers) == 1 and not isinstance(logger.handlers[0].formatter, FormateadorJson)
    with pytest.raises(ValueError):
        obtener_logger("pipeline_sbs.prueba_x", formato="xml")


def test_el_cargador_emite_un_evento_json_por_archivo(lote_trampas, tmp_path, caplog):
    logger, salida = _logger_con_salida("pipeline_sbs.ingesta.cargador")
    try:
        CargadorDocumentos(lote_trampas, tmp_path / "q", esperas=(0,)).cargar_lote()
    finally:
        logger.handlers.clear()
        logger.propagate = True
    eventos = [json.loads(linea) for linea in salida.getvalue().splitlines()]
    procesados = [e for e in eventos if e["mensaje"] == "archivo_procesado"]
    assert len(procesados) == 12
    assert all({"archivo", "estado", "motivo", "formato", "segundos"} <= set(e) for e in procesados)


def test_configuracion_de_s02():
    cfg = cargar_configuracion()
    assert cfg["ingesta"]["umbral_ocr_caracteres_por_pagina"] == 20
    assert cfg["ingesta"]["hash"] == "sha256" and cfg["ingesta"]["carpeta_cuarentena"]
    assert cfg["logging"]["formato"] == "json"
    paddle = cfg["ocr"]["paddle"]
    assert paddle["enable_mkldnn"] is False and "mobile" in paddle["modelo_deteccion"]


def test_la_biblioteca_declara_solo_un_nullhandler():
    import pipeline_sbs  # noqa: F401

    manejadores = logging.getLogger("pipeline_sbs").handlers
    assert any(isinstance(h, logging.NullHandler) for h in manejadores)
