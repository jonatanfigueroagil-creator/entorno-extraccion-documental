"""Pruebas de las zonas de la página."""
import numpy as np

from mi_pipeline.ocr.zonas import recortar_zona, zonas_de_pagina


def test_recortar_zona_por_fracciones_de_la_altura():
    pagina = np.zeros((1000, 800), np.uint8)
    assert recortar_zona(pagina, 0.0, 0.22).shape == (220, 800)


def test_zonas_de_pagina_cubren_toda_la_hoja():
    assert sum(zona.shape[0] for zona in zonas_de_pagina(np.zeros((1000, 800), np.uint8)).values()) == 1000
