"""Pruebas de clasificacion.motivo: TF-IDF con regresión logística y zero-shot."""
import json

import pytest

from pipeline_sbs.clasificacion import motivo
from pipeline_sbs.clasificacion.motivo import crear_modelo, entrenar, f1_macro, predecir, validar_cruzado, zero_shot

FRASES = {
    "cobro indebido": "me cobraron una comision que nunca autorice",
    "cargo duplicado": "me descontaron dos veces la misma cuota",
    "demora en entrega": "pedi mi tarjeta hace semanas y nadie me la entrega",
    "cuenta cerrada": "cerraron mi cuenta sin avisarme y no me devuelven mi saldo",
}


@pytest.fixture
def datos():
    textos, etiquetas = [], []
    for i in range(5):
        for etiqueta, frase in FRASES.items():
            textos.append(f"{frase} en la agencia numero {i}")
            etiquetas.append(etiqueta)
    return textos, etiquetas


def test_crear_modelo_usa_tfidf_de_uno_y_dos_terminos():
    modelo = crear_modelo()
    tfidf = modelo.named_steps["tfidf"]
    assert tfidf.ngram_range == (1, 2) and tfidf.sublinear_tf is True
    assert modelo.named_steps["logistica"].random_state == 2026


def test_f1_macro_promedia_el_f1_de_cada_motivo():
    assert f1_macro(["a", "a", "b", "b"], ["a", "a", "b", "b"]) == 1.0
    assert f1_macro(["a", "a", "b", "b"], ["a", "b", "b", "b"]) == 0.733


def test_entrenar_y_predecir_devuelven_motivo_y_probabilidad(datos):
    textos, etiquetas = datos
    modelo = entrenar(textos, etiquetas)
    (etiqueta, probabilidad), = predecir(modelo, ["cerraron mi cuenta sin avisarme"])
    assert etiqueta == "cuenta cerrada" and 0.0 < probabilidad <= 1.0


def test_validar_cruzado_es_repetible_y_trae_matriz(datos):
    textos, etiquetas = datos
    a = validar_cruzado(textos, etiquetas, pliegues=5, semilla=2026)
    b = validar_cruzado(textos, etiquetas, pliegues=5, semilla=2026)
    assert a["f1_macro"] == b["f1_macro"] and a["predicciones"] == b["predicciones"]
    assert 0.9 <= a["f1_macro"] <= 1.0
    assert len(a["matriz"]) == len(a["clases"]) == 4


def test_zero_shot_ordena_las_etiquetas_por_puntaje(monkeypatch):
    def falso(textos, candidate_labels, hypothesis_template):
        assert hypothesis_template == "Este reclamo trata de {}."
        return [{"labels": ["cargo duplicado", "cobro indebido"], "scores": [0.91, 0.09]} for _ in textos]
    monkeypatch.setattr(motivo, "cargar_zero_shot", lambda modelo, dispositivo: falso)
    salida = zero_shot(["me descontaron dos veces"], ["cobro indebido", "cargo duplicado"], dispositivo="cpu")
    assert salida[0]["etiqueta"] == "cargo duplicado" and salida[0]["score"] == 0.91


def test_zero_shot_lee_los_archivos_precalculados_si_no_hay_gpu(tmp_path, monkeypatch):
    archivo = tmp_path / "REC-0001.json"
    archivo.write_text(json.dumps({"etiquetas": ["cuenta cerrada", "tasa distinta"], "scores": [0.8, 0.2]}), encoding="utf-8")

    def no_cargar(*argumentos):
        raise AssertionError("no debe cargar el modelo")
    monkeypatch.setattr(motivo, "resolver_dispositivo", lambda d="auto": "cpu")
    monkeypatch.setattr(motivo, "cargar_zero_shot", no_cargar)
    salida = zero_shot(["texto"], ["cuenta cerrada", "tasa distinta"], precalculado=[archivo])
    assert salida[0]["etiqueta"] == "cuenta cerrada" and salida[0]["scores"] == [0.8, 0.2]
