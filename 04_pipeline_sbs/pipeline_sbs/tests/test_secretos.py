"""Pruebas de config/secretos.py (S07): los secretos salen de variables de entorno y nunca llegan al registro."""
import io
import json
import logging

import pytest

from pipeline_sbs.config.secretos import ErrorSecreto, leer_secreto, secretos_en_config
from pipeline_sbs.monitoreo.registro import FormateadorJson


def test_el_secreto_se_lee_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("PIPELINE_CLAVE_DEMO", "valor-de-practica-123")
    assert leer_secreto("PIPELINE_CLAVE_DEMO") == "valor-de-practica-123"


def test_sin_la_variable_se_detiene_con_un_mensaje_claro(monkeypatch):
    monkeypatch.delenv("PIPELINE_CLAVE_DEMO", raising=False)
    with pytest.raises(ErrorSecreto, match="PIPELINE_CLAVE_DEMO"):
        leer_secreto("PIPELINE_CLAVE_DEMO")
    assert leer_secreto("PIPELINE_CLAVE_DEMO", obligatorio=False) is None


def test_un_secreto_leido_sale_oculto_si_alguien_lo_escribe_en_el_registro(monkeypatch):
    monkeypatch.setenv("PIPELINE_CLAVE_DEMO", "otra-clave-de-practica-456")
    secreto = leer_secreto("PIPELINE_CLAVE_DEMO")
    salida = io.StringIO()
    logger = logging.getLogger("prueba.s07.secretos")
    logger.handlers.clear()
    logger.propagate = False
    manejador = logging.StreamHandler(salida)
    manejador.setFormatter(FormateadorJson())
    logger.addHandler(manejador)
    logger.warning(f"conexión con la clave {secreto}", extra={"api_key": secreto, "detalle": f"usa {secreto}"})
    linea = salida.getvalue()
    assert secreto not in linea
    evento = json.loads(linea)
    assert evento["api_key"] == "[OCULTO]" and "[OCULTO]" in evento["mensaje"] and "[OCULTO]" in evento["detalle"]


def test_el_yaml_con_un_secreto_escrito_se_detecta():
    datos = {"llm": {"backend": "servidor_compartido", "api_key": "abc123"}, "ocr": {"idioma": "spa"}}
    assert secretos_en_config(datos) == ["llm.api_key"]
    assert secretos_en_config({"llm": {"api_key": ""}}) == []
