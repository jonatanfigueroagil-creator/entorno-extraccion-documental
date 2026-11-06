"""Pruebas de ocr.zonas: encabezado, cuerpo y pie por coordenadas."""
import numpy as np
import pytest

from pipeline_sbs.ocr.zonas import ZONAS, recortar_zona, zonas_de_pagina


def test_recortar_zona_por_fracciones_de_la_altura():
    pagina = np.zeros((1000, 800), np.uint8)
    assert recortar_zona(pagina, 0.0, 0.22).shape == (220, 800)
    assert recortar_zona(pagina, 0.88, 1.0).shape == (120, 800)
    with pytest.raises(ValueError):
        recortar_zona(pagina, 0.5, 0.2)


def test_zonas_de_pagina_cubren_toda_la_hoja_sin_huecos():
    pagina = np.zeros((1000, 800, 3), np.uint8)
    zonas = zonas_de_pagina(pagina)
    assert list(zonas) == list(ZONAS) == ["encabezado", "cuerpo", "pie"]
    assert sum(z.shape[0] for z in zonas.values()) == 1000
