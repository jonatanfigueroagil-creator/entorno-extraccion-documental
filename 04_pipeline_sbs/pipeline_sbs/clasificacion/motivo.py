"""Clasificación del motivo de un reclamo: TF-IDF con regresión logística y zero-shot con un modelo de Transformers."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from ..extraccion.ner import resolver_dispositivo

MODELO_ZERO_SHOT = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
PLANTILLA = "Este reclamo trata de {}."


def crear_modelo(semilla: int = 2026) -> Pipeline:
    """Arma el clasificador sin entrenar: TF-IDF de palabras sueltas y pares de palabras, y regresión logística.

    Args:
        semilla: número que fija el azar y vuelve reproducible el resultado.
    """
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("logistica", LogisticRegression(max_iter=1000, random_state=semilla)),
    ])


def entrenar(textos: list[str], etiquetas: list[str], semilla: int = 2026) -> Pipeline:
    """Entrena el clasificador con los textos y sus motivos correctos.

    Args:
        textos: cuerpos de los correos (nunca el asunto: el asunto trae la clase).
        etiquetas: motivo correcto de cada texto.
        semilla: número que fija el azar.

    Returns:
        El modelo entrenado, que acepta ``predict`` y ``predict_proba``.
    """
    return crear_modelo(semilla).fit(textos, etiquetas)


def predecir(modelo: Pipeline, textos: list[str]) -> list[tuple[str, float]]:
    """Predice el motivo de cada texto y la probabilidad que el modelo le da.

    Returns:
        Una lista de pares ``(motivo, probabilidad)``.
    """
    probabilidades = modelo.predict_proba(textos)
    clases = modelo.classes_
    return [(str(clases[fila.argmax()]), round(float(fila.max()), 4)) for fila in probabilidades]


def f1_macro(correctas: list[str], predichas: list[str]) -> float:
    """F1 macro: calcula el F1 de cada motivo por separado y promedia, de modo que todos pesan igual.

    Args:
        correctas: motivo correcto de cada texto.
        predichas: motivo que predijo el modelo (mismo orden).
    """
    return round(float(f1_score(correctas, predichas, average="macro")), 3)


def validar_cruzado(textos: list[str], etiquetas: list[str], pliegues: int = 5, semilla: int = 2026) -> dict[str, Any]:
    """Mide el modelo con validación cruzada: cada texto se predice con un modelo que no lo vio en el entrenamiento.

    Args:
        textos: cuerpos de los correos.
        etiquetas: motivo correcto de cada texto.
        pliegues: en cuántas partes se divide el lote.
        semilla: número que fija el azar.

    Returns:
        ``{"f1_macro", "exactitud", "predicciones", "clases", "matriz"}``.
    """
    modelo = crear_modelo(semilla)
    division = StratifiedKFold(n_splits=pliegues, shuffle=True, random_state=semilla)
    predicciones = list(cross_val_predict(modelo, textos, etiquetas, cv=division))
    clases = sorted(set(etiquetas))
    return {
        "f1_macro": f1_macro(etiquetas, predicciones),
        "exactitud": round(sum(p == e for p, e in zip(predicciones, etiquetas)) / len(etiquetas), 3),
        "predicciones": predicciones,
        "clases": clases,
        "matriz": confusion_matrix(etiquetas, predicciones, labels=clases).tolist(),
    }


@lru_cache(maxsize=2)
def cargar_zero_shot(modelo: str, dispositivo: str):
    """Carga el clasificador zero-shot (no necesita ejemplos de entrenamiento) y lo guarda en memoria."""
    from transformers import pipeline

    return pipeline("zero-shot-classification", model=modelo, device=0 if dispositivo == "cuda" else -1)


def zero_shot(
    textos: list[str],
    etiquetas: list[str],
    modelo: str = MODELO_ZERO_SHOT,
    dispositivo: str = "auto",
    plantilla: str = PLANTILLA,
    precalculado: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Clasifica sin entrenar: el modelo decide cuál de las etiquetas completa mejor la frase de la plantilla.

    Si no hay GPU y se pasa la lista ``precalculado`` (un .json por texto, en el mismo orden) y todos existen,
    lee esas salidas en vez de correr el modelo: en CPU el lote de 60 correos tarda unos 7 minutos.

    Args:
        textos: cuerpos de los correos.
        etiquetas: motivos posibles.
        modelo: nombre del modelo en Hugging Face.
        dispositivo: ``auto``, ``cpu`` o ``cuda``.
        plantilla: frase con ``{}`` donde va cada etiqueta.
        precalculado: archivos .json con la salida guardada de una corrida anterior con GPU.

    Returns:
        Una lista de ``{"etiqueta", "score", "etiquetas", "scores"}``, una por texto.
    """
    donde = resolver_dispositivo(dispositivo)
    if precalculado is not None and donde == "cpu" and all(Path(a).is_file() for a in precalculado):
        salidas = [json.loads(Path(a).read_text(encoding="utf-8")) for a in precalculado]
        return [{"etiqueta": s["etiquetas"][0], "score": s["scores"][0], "etiquetas": s["etiquetas"],
                 "scores": s["scores"]} for s in salidas]
    clasificador = cargar_zero_shot(modelo, donde)
    resultado = clasificador(textos, candidate_labels=etiquetas, hypothesis_template=plantilla)
    if isinstance(resultado, dict):
        resultado = [resultado]
    return [{"etiqueta": r["labels"][0], "score": round(float(r["scores"][0]), 4), "etiquetas": r["labels"],
             "scores": [round(float(x), 4) for x in r["scores"]]} for r in resultado]
