"""Documentos largos, con la técnica «dividir y combinar» (map-reduce): estimar si caben en el contexto, partir en trozos
(por página o en ventanas) y combinar por votación. Cada trozo recibe el mismo prompt (``prompts.py``) que un documento entero."""
from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel

from .esquemas import ESQUEMAS
from .extraer import extraer_con_llm

CARACTERES_POR_TOKEN = 3.5  # medido en los contratos del corpus; en documentos cortos con muchos números es cerca de 2,2
RESERVA = 1500  # tokens para el prompt (Rol, Contexto, Tarea y Formato) y la respuesta


def estimar_tokens(texto: str) -> int:
    """Tokens aproximados de un texto, sin contarlos con el modelo: caracteres / 3,5."""
    return round(len(texto) / CARACTERES_POR_TOKEN)


def cabe(texto: str, num_ctx: int) -> bool:
    """Dice si el texto, más la reserva para el prompt y la respuesta, cabe en el contexto."""
    return estimar_tokens(texto) + RESERVA <= num_ctx


def por_pagina(doc: dict[str, Any]) -> list[str]:
    """Un trozo por página (o por pieza del documento), con su número al inicio."""
    return [f"--- Página {numero} ---\n{parte}" for numero, parte in enumerate(doc["partes"], 1) if parte.strip()]


def ventana(texto: str, tamano: int = 7000, solape: int = 700) -> list[str]:
    """Trozos de ``tamano`` caracteres que se solapan ``solape`` caracteres, para no cortar una cláusula por la mitad."""
    paso = tamano - solape
    return [texto[inicio:inicio + tamano] for inicio in range(0, max(len(texto) - solape, 1), paso)]


def votar(valores: list[Any]) -> Any:
    """El valor no nulo que más trozos devolvieron; si empatan, el que apareció primero."""
    presentes = [v for v in valores if v is not None]
    if not presentes:
        return None
    veces = Counter(presentes)
    return max(presentes, key=lambda v: (veces[v], -presentes.index(v)))


def map_reduce(trozos: list[str], tipo: str, modelo: str | None = None, num_ctx: int | None = None,
               esquema: type[BaseModel] | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dividir y combinar: extrae de cada trozo por separado, con el mismo prompt (map), y combina por votación en Python (reduce).

    Args:
        esquema: otro esquema en lugar del esquema del tipo (por ejemplo, uno propio para documentos reales).

    Returns:
        ``campos`` (combinados), ``por_trozo`` (lo que dio cada trozo), ``llamadas`` y ``segundos``.
    """
    esquema = esquema or ESQUEMAS[tipo]
    parciales = [extraer_con_llm(trozo, tipo, modelo, esquema=esquema, num_ctx=num_ctx, cfg=cfg) for trozo in trozos]
    campos = {campo: votar([p["campos"][campo] for p in parciales]) for campo in esquema.model_fields}
    return {"campos": campos, "por_trozo": [p["campos"] for p in parciales], "llamadas": len(parciales),
            "segundos": round(sum(p["segundos"] for p in parciales), 2)}
