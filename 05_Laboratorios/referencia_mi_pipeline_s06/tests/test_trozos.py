"""Pruebas de llm/trozos.py (no necesitan GPU)."""
from mi_pipeline.llm.trozos import cabe, por_pagina, ventana, votar


def test_un_contrato_de_27000_caracteres_no_cabe_en_4096_y_si_en_12288():
    assert not cabe("x" * 27000, 4096) and cabe("x" * 27000, 12288)


def test_las_ventanas_se_solapan_y_por_pagina_salta_las_vacias():
    trozos = ventana("abcdefghij" * 100, tamano=300, solape=30)
    assert trozos[0][-30:] == trozos[1][:30]
    assert por_pagina({"partes": ["uno", "", "tres"]}) == ["--- Página 1 ---\nuno", "--- Página 3 ---\ntres"]


def test_votar_elige_el_valor_mas_repetido_y_salta_los_nulos():
    assert votar([None, "A", "B", "A"]) == "A" and votar([None, None]) is None
