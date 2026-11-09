"""Pruebas de llm/esquemas.py (no necesitan GPU)."""
import pytest
from pydantic import ValidationError

from mi_pipeline.llm.esquemas import ESQUEMAS, Poliza, campos_de


def test_todos_los_campos_son_obligatorios_y_admiten_null():
    esquema = Poliza.model_json_schema()
    assert set(esquema["required"]) == set(campos_de("poliza"))
    assert Poliza(**{campo: None for campo in campos_de("poliza")}).moneda is None


def test_la_moneda_es_una_lista_cerrada():
    with pytest.raises(ValidationError):
        Poliza(**{**{campo: None for campo in campos_de("poliza")}, "moneda": "S/"})


def test_cada_campo_trae_la_descripcion_que_el_formato_escribe_en_el_prompt():
    for tipo, esquema in ESQUEMAS.items():
        assert all(datos.get("description") for datos in esquema.model_json_schema()["properties"].values()), tipo
