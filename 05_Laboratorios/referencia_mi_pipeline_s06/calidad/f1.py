"""F1 por campo: compara lo que extrajo el pipeline con el valor correcto de cada documento."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

CAMPOS_SOLO_CIFRAS = ("dni", "telefono")


def normalizar_valor(campo: str, valor: Any) -> str | None:
    """Lleva un valor a una forma comparable: sin tildes, en minúscula y sin signos sobrantes.

    Args:
        campo: nombre del campo (``dni``, ``monto_reclamado``, ``fecha``, ``nombre``…).
        valor: valor extraído o correcto; None o texto vacío significan «sin valor».

    Returns:
        Texto normalizado, o None si no hay valor. El monto queda con dos decimales (``2643.00``),
        el DNI y el teléfono solo con cifras, y la fecha en formato ISO.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if campo == "monto_reclamado":
        return f"{float(valor):.2f}"
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor)
    if campo in CAMPOS_SOLO_CIFRAS:
        return re.sub(r"\D", "", texto)
    base = unicodedata.normalize("NFD", texto.lower())
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", base).strip(" .,;:()")


def f1_por_campo(
    predichos: list[dict[str, Any]], correctos: list[dict[str, Any]], campos: list[str] | None = None
) -> dict[str, dict[str, float]]:
    """Calcula precisión, recall y F1 de cada campo y compara por valor normalizado.

    Un valor predicho distinto del correcto cuenta como falso positivo y como falso negativo; un campo
    sin valor cuenta solo como falso negativo.

    Args:
        predichos: un diccionario por documento con los valores extraídos.
        correctos: un diccionario por documento (mismo orden) con los valores correctos.
        campos: campos a medir; por defecto, los del primer diccionario correcto.

    Returns:
        ``{campo: {"precision", "recall", "f1", "n", "aciertos"}}``.

    Raises:
        ValueError: si las listas no tienen la misma longitud.
    """
    if len(predichos) != len(correctos):
        raise ValueError(f"Hay {len(predichos)} predicciones y {len(correctos)} documentos correctos")
    resultado: dict[str, dict[str, float]] = {}
    for campo in campos or list(correctos[0]):
        tp = fp = fn = 0
        for pred, ok in zip(predichos, correctos):
            p, c = normalizar_valor(campo, pred.get(campo)), normalizar_valor(campo, ok.get(campo))
            if p is not None and p == c:
                tp += 1
            else:
                fp += p is not None
                fn += c is not None
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        resultado[campo] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
                            "n": len(correctos), "aciertos": tp}
    return resultado


def campos_bajo_umbral(tabla: dict[str, dict[str, float]], umbral: float = 0.80) -> list[str]:
    """Lista los campos cuyo F1 no llega al umbral."""
    return [campo for campo, medidas in tabla.items() if medidas["f1"] < umbral]
