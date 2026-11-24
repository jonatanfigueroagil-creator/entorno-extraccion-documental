"""Pruebas de calidad/f1.py."""
from mi_pipeline.calidad.f1 import f1_por_campo


def test_f1_perfecto_cuando_todo_coincide():
    correctos = [{"dni": "99111111"}, {"dni": "99222222"}]
    assert f1_por_campo(correctos, correctos)["dni"]["f1"] == 1.0


def test_un_valor_distinto_baja_el_f1_a_la_mitad():
    predichos = [{"dni": "99111111"}, {"dni": "99222223"}]
    correctos = [{"dni": "99111111"}, {"dni": "99222222"}]
    assert f1_por_campo(predichos, correctos)["dni"]["f1"] == 0.5
