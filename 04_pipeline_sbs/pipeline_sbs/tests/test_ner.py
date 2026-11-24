"""Pruebas de extraccion.ner: dos motores, respaldo precalculado y resumen en campos."""
import json

import pytest

from pipeline_sbs.extraccion import ner
from pipeline_sbs.extraccion.ner import entidades_a_campos, ner_spacy, ner_transformers, resolver_dispositivo, unir_fragmentos
from pipeline_sbs.extraccion.texto import cargar_modelo


def test_ner_spacy_reconoce_una_persona():
    try:
        cargar_modelo()
    except OSError:
        pytest.skip("No está instalado ningún modelo de spaCy en español")
    entidades = ner_spacy("Buenas, soy Jorge Fuentes Bravo, DNI 99929470.")
    assert ("Jorge Fuentes Bravo", "PER") in [(e["texto"], e["etiqueta"]) for e in entidades]
    assert all(e["score"] is None for e in entidades)


def test_resolver_dispositivo_cpu_es_cpu():
    assert resolver_dispositivo("cpu") == "cpu"


def test_resolver_dispositivo_auto_elige_cuda_o_cpu():
    pytest.importorskip("torch")
    assert resolver_dispositivo("auto") in ("cpu", "cuda")


def test_unir_fragmentos_junta_las_piezas_de_una_misma_palabra():
    texto = "Senores de Caja Rural Valle Verde DEMO S.A."
    partes = [{"texto": "Ca", "etiqueta": "ORG", "inicio": 11, "fin": 13, "score": 0.9},
              {"texto": "ja Rural Valle Verde DEMO S.A.", "etiqueta": "ORG", "inicio": 13, "fin": 43, "score": 0.7}]
    unidas = unir_fragmentos(partes, texto)
    assert len(unidas) == 1 and unidas[0]["texto"] == "Caja Rural Valle Verde DEMO S.A." and unidas[0]["score"] == 0.8


def test_unir_fragmentos_no_junta_etiquetas_distintas_ni_palabras_separadas():
    texto = "Ana Banco"
    partes = [{"texto": "Ana", "etiqueta": "PER", "inicio": 0, "fin": 3, "score": 1.0},
              {"texto": "Banco", "etiqueta": "ORG", "inicio": 4, "fin": 9, "score": 1.0}]
    assert len(unir_fragmentos(partes, texto)) == 2


def test_entidades_a_campos_elige_la_que_mas_se_repite():
    ents = [
        {"texto": "Jorge Fuentes Bravo", "etiqueta": "PER", "score": 1.0},
        {"texto": "Banco Andino DEMO S.A.", "etiqueta": "ORG", "score": 0.99},
        {"texto": "Jorge Fuentes Bravo", "etiqueta": "PER", "score": 0.99},
        {"texto": "Jorge", "etiqueta": "PER", "score": 1.0},
    ]
    assert entidades_a_campos(ents) == {"nombre": "Jorge Fuentes Bravo", "entidad": "Banco Andino DEMO S.A."}
    assert entidades_a_campos([]) == {"nombre": None, "entidad": None}


def test_entidades_a_campos_usa_loc_si_no_hay_org():
    ents = [{"texto": "Banco Cordillera DEMO S.A.", "etiqueta": "LOC", "score": None}]
    assert entidades_a_campos(ents)["entidad"] == "Banco Cordillera DEMO S.A."
    assert entidades_a_campos(ents, ("ORG",))["entidad"] is None


def test_ner_transformers_agrupa_y_devuelve_posiciones(monkeypatch):
    def falso(texto):
        return [{"word": "Ana Ruiz", "entity_group": "PER", "start": 5, "end": 13, "score": 0.9991}]
    monkeypatch.setattr(ner, "cargar_ner", lambda modelo, dispositivo: falso)
    salida = ner_transformers("Soy Ana Ruiz", dispositivo="cpu")
    assert salida == [{"texto": "Ana Ruiz", "etiqueta": "PER", "inicio": 5, "fin": 13, "score": 0.9991}]


def test_ner_transformers_lee_el_precalculado_si_no_hay_gpu(tmp_path, monkeypatch):
    archivo = tmp_path / "REC-0001.json"
    archivo.write_text(json.dumps({"id": "REC-0001", "entidades": [{"texto": "Ana Ruiz", "etiqueta": "PER", "score": 0.99}]}), encoding="utf-8")

    def no_cargar(*argumentos):
        raise AssertionError("no debe cargar el modelo")
    monkeypatch.setattr(ner, "resolver_dispositivo", lambda d="auto": "cpu")
    monkeypatch.setattr(ner, "cargar_ner", no_cargar)
    assert ner_transformers("cualquier texto", precalculado=archivo)[0]["texto"] == "Ana Ruiz"
