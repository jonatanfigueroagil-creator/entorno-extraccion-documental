"""Reconocimiento de entidades (NER) con dos motores: spaCy y un modelo de Transformers."""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from .texto import analizar

MODELO_NER = "Davlan/xlm-roberta-base-ner-hrl"


def ner_spacy(texto: str, nombre: str = "es_core_news_md") -> list[dict[str, Any]]:
    """Reconoce entidades con spaCy (CPU).

    Returns:
        Una lista de ``{"texto", "etiqueta", "inicio", "fin", "score"}``; spaCy no entrega puntaje (``score`` es None).
    """
    return [{"texto": e.text, "etiqueta": e.label_, "inicio": e.start_char, "fin": e.end_char, "score": None}
            for e in analizar(texto, nombre).ents]


def resolver_dispositivo(dispositivo: str = "auto") -> str:
    """Decide dónde corre el modelo: ``cuda`` si hay GPU y se pidió ``auto`` o ``cuda``; en otro caso ``cpu``."""
    if dispositivo == "cpu":
        return "cpu"
    try:
        import torch
    except ImportError:          # sin torch no hay GPU: se usa la CPU y las salidas guardadas
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=2)
def cargar_ner(modelo: str, dispositivo: str):
    """Carga el modelo de Transformers para NER y lo guarda en memoria (la primera carga tarda unos segundos)."""
    from transformers import pipeline

    return pipeline("token-classification", model=modelo, aggregation_strategy="simple",
                    device=0 if dispositivo == "cuda" else -1)


def leer_precalculado(ruta: str | Path) -> list[dict[str, Any]]:
    """Lee las entidades de un archivo .json precalculado (respaldo cuando no hay GPU)."""
    entidades = json.loads(Path(ruta).read_text(encoding="utf-8"))["entidades"]
    return [{"inicio": None, "fin": None, **e} for e in entidades]


def unir_fragmentos(entidades: list[dict[str, Any]], texto: str) -> list[dict[str, Any]]:
    """Une los trozos de una misma palabra que el modelo partió (``Ca`` y ``ja Rural`` pasan a ser ``Caja Rural``).

    Dos entidades con la misma etiqueta se unen si la segunda empieza justo donde termina la primera.

    Args:
        entidades: entidades ordenadas por posición, con ``inicio`` y ``fin`` en caracteres.
        texto: texto original, del que se recorta el nuevo tramo.

    Returns:
        La lista con los fragmentos unidos; el puntaje de la unión es el promedio de los dos.
    """
    unidas: list[dict[str, Any]] = []
    for e in sorted(entidades, key=lambda x: x["inicio"]):
        previa = unidas[-1] if unidas else None
        if previa and previa["etiqueta"] == e["etiqueta"] and e["inicio"] == previa["fin"]:
            previa.update(fin=e["fin"], texto=texto[previa["inicio"]:e["fin"]].strip(),
                          score=round((previa["score"] + e["score"]) / 2, 4))
        else:
            unidas.append(dict(e))
    return unidas


def ner_transformers(
    texto: str,
    modelo: str = MODELO_NER,
    dispositivo: str = "auto",
    precalculado: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Reconoce entidades con un modelo de Transformers (agrupa las piezas de una misma entidad).

    Si no hay GPU y se indica un archivo ``precalculado`` que existe, devuelve su contenido en vez de correr el modelo.

    Args:
        texto: texto de un correo y su adjunto.
        modelo: nombre del modelo en Hugging Face.
        dispositivo: ``auto``, ``cpu`` o ``cuda``.
        precalculado: salida guardada de una corrida anterior con GPU.

    Returns:
        Una lista de ``{"texto", "etiqueta", "inicio", "fin", "score"}``.
    """
    donde = resolver_dispositivo(dispositivo)
    if precalculado is not None and donde == "cpu" and Path(precalculado).is_file():
        return leer_precalculado(precalculado)
    salida = cargar_ner(modelo, donde)(texto)
    entidades = [{"texto": e["word"].strip(), "etiqueta": e["entity_group"], "inicio": int(e["start"]),
                  "fin": int(e["end"]), "score": round(float(e["score"]), 4)} for e in salida]
    return unir_fragmentos(entidades, texto)


def entidades_a_campos(entidades: list[dict[str, Any]], etiquetas_entidad: tuple[str, ...] = ("ORG", "LOC")) -> dict[str, str | None]:
    """Resume las entidades de un documento en los campos ``nombre`` y ``entidad``.

    Elige la persona (PER) y la organización que más se repiten; si empatan, la más larga.

    Args:
        entidades: salida de ``ner_spacy`` o ``ner_transformers``.
        etiquetas_entidad: etiquetas que cuentan como organización, en orden de preferencia.

    Returns:
        ``{"nombre": ..., "entidad": ...}`` con None cuando no hay candidato.
    """
    def elegir(etiquetas: tuple[str, ...]) -> str | None:
        for etiqueta in etiquetas:
            candidatas = [e for e in entidades if e["etiqueta"] == etiqueta]
            if candidatas:
                veces = Counter(e["texto"] for e in candidatas)
                mejor_score = {e["texto"]: max(x["score"] or 0 for x in candidatas if x["texto"] == e["texto"]) for e in candidatas}
                return max(veces, key=lambda t: (veces[t], len(t), mejor_score[t]))
        return None

    return {"nombre": elegir(("PER",)), "entidad": elegir(etiquetas_entidad)}
