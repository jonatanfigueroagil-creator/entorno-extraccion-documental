"""Pruebas de humo: la estructura del paquete está completa y se puede importar."""
import importlib

import pytest

SUBPAQUETES = [
    "ingesta", "preprocesamiento", "ocr", "calidad", "extraccion", "clasificacion",
    "llm", "orquestacion", "almacenamiento", "monitoreo", "config",
]


@pytest.mark.parametrize("nombre", SUBPAQUETES)
def test_subpaquete_importable_y_documentado(nombre):
    modulo = importlib.import_module(f"pipeline_sbs.{nombre}")
    assert modulo.__doc__ and modulo.__doc__.strip(), f"{nombre} debe explicar su rol en el docstring"


def test_version_del_paquete():
    import pipeline_sbs

    assert pipeline_sbs.__version__
