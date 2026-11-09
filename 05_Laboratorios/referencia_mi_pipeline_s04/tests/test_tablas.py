"""Pruebas de la lectura de tablas."""
import math

import pandas as pd

from mi_pipeline.ocr.tablas import a_numero, cuadratura


def test_a_numero_quita_la_coma_de_miles_y_devuelve_nan_si_no_es_numero():
    assert a_numero("35,569") == 35569.0 and math.isnan(a_numero("3S,569"))


def test_cuadratura_activo_igual_a_pasivo_mas_patrimonio():
    tabla = pd.DataFrame({"Concepto": ["Total activo", "Total pasivo", "Total patrimonio"], "2026": [100.0, 70.0, 30.0]})
    assert cuadratura(tabla, "2026")["cuadra"] is True
