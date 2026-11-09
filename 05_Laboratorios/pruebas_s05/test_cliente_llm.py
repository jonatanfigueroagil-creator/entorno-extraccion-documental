"""Pruebas de llm/cliente_llm.py (la que llama al modelo se omite con aviso si Ollama no responde)."""
import pytest

from mi_pipeline.llm.cliente_llm import configuracion_llm, conectar, ollama_disponible, preguntar


def test_la_configuracion_fija_contexto_tope_y_temperatura():
    cfg = configuracion_llm()
    assert (cfg["num_ctx"], cfg["num_predict"], cfg["temperatura"]) == (12288, 1000, 0)


def test_un_backend_en_la_nube_no_se_permite():
    with pytest.raises(ValueError):
        conectar({**configuracion_llm(), "backend": "api_nube"})


@pytest.mark.skipif(not ollama_disponible("qwen3.5:4b"), reason="Ollama no responde en localhost:11434 o falta qwen3.5:4b: se abre «Ollama» desde Inicio y se repite")
def test_preguntar_mide_tokens_segundos_y_motivo_de_fin():
    respuesta = preguntar("qwen3.5:4b", "Responde solo con la palabra: listo", num_predict=10)
    assert respuesta.fin in ("stop", "length") and respuesta.tokens_entrada > 0 and respuesta.segundos > 0
