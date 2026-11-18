"""Pruebas de llm/extraer.py (la que llama al modelo se omite con aviso si Ollama no responde)."""
import json

import pytest

from mi_pipeline.llm import extraer
from mi_pipeline.llm.cliente_llm import Respuesta, ollama_disponible
from mi_pipeline.llm.esquemas import Poliza, campos_de


def respuestas(*textos):
    """Reemplaza al modelo: cada llamada devuelve el texto siguiente y anota el formato que recibió."""
    pendientes, formatos = iter(textos), []

    def falso(modelo, mensajes, esquema=None, **opciones):
        formatos.append(esquema)
        return Respuesta(next(pendientes), 0.1, 10, 5, "stop", "prueba")
    return falso, formatos


def test_pide_una_vez_mas_si_el_json_no_cumple_el_esquema(monkeypatch):
    falso, _ = respuestas('{"entidad": 5}', json.dumps({campo: None for campo in campos_de("tarifario")}))
    monkeypatch.setattr(extraer, "preguntar", falso)
    resultado = extraer.extraer_con_llm("texto", "tarifario")
    assert resultado["valido"] and resultado["intentos"] == 2 and resultado["nivel"] == 5


def test_el_esquema_va_en_format_solo_desde_el_nivel_4(monkeypatch):
    falso, formatos = respuestas('{"moneda": "S/"}', json.dumps({campo: None for campo in campos_de("poliza")}))
    monkeypatch.setattr(extraer, "preguntar", falso)
    solo_tarea = extraer.extraer_con_llm("texto", "poliza", nivel=1)
    extraer.extraer_con_llm("texto", "poliza", nivel=4)
    assert formatos == ["json", Poliza]
    assert solo_tarea["intentos"] == 1 and not solo_tarea["valido"] and solo_tarea["campos"]["moneda"] == "S/"


@pytest.mark.skipif(not ollama_disponible("qwen3.5:4b"), reason="Ollama no responde en localhost:11434 o falta qwen3.5:4b: se abre «Ollama» desde Inicio y se repite")
def test_el_llm_extrae_y_python_normaliza():
    texto = ("Poliza: PZ-2026-000001\nAseguradora: Seguros Tierra Firme DEMO S.A.\n"
             "Suma asegurada: S/ 174,000.00\nVigencia desde: 6 de julio de 2026")
    resultado = extraer.extraer_con_llm(texto, "poliza")
    assert resultado["valido"] and resultado["campos"]["suma_asegurada"] == 174000.0
    assert resultado["campos"]["vigencia_desde"] == "2026-07-06"
