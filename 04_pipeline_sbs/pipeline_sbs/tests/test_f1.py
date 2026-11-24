"""Pruebas de calidad.f1: normalización de valores y F1 por campo."""
import pytest

from pipeline_sbs.calidad.f1 import campos_bajo_umbral, f1_por_campo, normalizar_valor


def test_normalizar_valor_unifica_formas_equivalentes():
    assert normalizar_valor("monto_reclamado", 2643) == "2643.00"
    assert normalizar_valor("telefono", "999 000 680") == "999000680"
    assert normalizar_valor("entidad", "Banco Andino DEMO S.A.") == normalizar_valor("entidad", "banco andino demo s.a")
    assert normalizar_valor("nombre", "José  Núñez") == "jose nunez"
    assert normalizar_valor("dni", None) is None
    assert normalizar_valor("dni", "  ") is None


def test_f1_perfecto_cuando_todo_coincide():
    ok = [{"dni": "99111111"}, {"dni": "99222222"}]
    assert f1_por_campo(ok, ok)["dni"]["f1"] == 1.0


def test_un_valor_distinto_cuenta_como_falso_positivo_y_falso_negativo():
    pred = [{"dni": "99111111"}, {"dni": "99222223"}]
    ok = [{"dni": "99111111"}, {"dni": "99222222"}]
    medidas = f1_por_campo(pred, ok)["dni"]
    assert (medidas["precision"], medidas["recall"], medidas["f1"], medidas["aciertos"]) == (0.5, 0.5, 0.5, 1)


def test_un_campo_sin_valor_baja_el_recall_pero_no_la_precision():
    pred = [{"dni": "99111111"}, {"dni": None}]
    ok = [{"dni": "99111111"}, {"dni": "99222222"}]
    medidas = f1_por_campo(pred, ok)["dni"]
    assert medidas["precision"] == 1.0 and medidas["recall"] == 0.5 and medidas["f1"] == pytest.approx(0.667, abs=0.001)


def test_f1_por_campo_exige_listas_del_mismo_largo():
    with pytest.raises(ValueError):
        f1_por_campo([{"dni": "1"}], [{"dni": "1"}, {"dni": "2"}])


def test_campos_bajo_umbral_lista_los_campos_debiles():
    tabla = {"dni": {"f1": 1.0}, "nombre": {"f1": 0.63}, "entidad": {"f1": 0.8}}
    assert campos_bajo_umbral(tabla, 0.8) == ["nombre"]
