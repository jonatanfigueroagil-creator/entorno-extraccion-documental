"""Prueba de regresión con golden set (S07): cada póliza congelada debe dar hoy la misma salida aprobada.

Se ejecuta sola con ``python -m pytest pipeline_sbs\\tests -m regresion``. La configuración es la del paquete o la que indique
la variable ``MI_PIPELINE_CONFIG`` (así se prueba un YAML cambiado sin tocar el del paquete). Sin golden set o sin los datos
de práctica, las pruebas se omiten con aviso.
"""
import json
import os

import pytest

from pipeline_sbs.calidad.regresion import CARPETA_GOLDEN, LINEA_BASE, diferencias, exactitud, localizar_datos, salida_actual
from pipeline_sbs.orquestacion.config import cargar_config

pytestmark = pytest.mark.regresion
APROBADAS = sorted(CARPETA_GOLDEN.glob("*.json")) if CARPETA_GOLDEN.is_dir() else []
APROBADAS = [ruta for ruta in APROBADAS if ruta.name != LINEA_BASE]


@pytest.fixture(scope="module")
def salidas_de_hoy():
    """La salida de hoy de cada documento del golden set (se calcula una sola vez para todas las pruebas)."""
    datos = localizar_datos()
    if datos is None:
        pytest.skip("No se encuentran los datos de práctica (02_Datos_Practica).")
    if not APROBADAS:
        pytest.skip("Todavía no hay golden set: se congela en el cuaderno (E3).")
    cfg = cargar_config(os.environ.get("MI_PIPELINE_CONFIG"))
    hoy = {}
    for ruta in APROBADAS:
        aprobada = json.loads(ruta.read_text(encoding="utf-8"))
        hoy[ruta.stem] = salida_actual(datos, aprobada["archivo"], aprobada["tipo"], cfg)["campos"]
    return datos, hoy


@pytest.mark.parametrize("aprobada", APROBADAS, ids=[ruta.stem for ruta in APROBADAS])
def test_la_salida_de_hoy_es_la_aprobada(aprobada, salidas_de_hoy):
    _, hoy = salidas_de_hoy
    cambios = diferencias(hoy[aprobada.stem], json.loads(aprobada.read_text(encoding="utf-8"))["campos"])
    assert not cambios, f"{aprobada.stem} cambió (campo: (aprobado, hoy)): {cambios}"


def test_la_exactitud_no_baja_de_la_linea_base(salidas_de_hoy):
    datos, hoy = salidas_de_hoy
    base = json.loads((CARPETA_GOLDEN / LINEA_BASE).read_text(encoding="utf-8"))
    medida = exactitud(hoy, datos)
    assert medida >= base["exactitud"], f"La exactitud bajó: {medida} frente a la línea base {base['exactitud']} ({base['version']})."
