"""Extracción con el LLM: el prompt de ``prompts.py`` -> JSON -> validación con el esquema -> valores normalizados en Python.

Desde el nivel 4 el prompt trae el Formato y el esquema va también en ``format``: la respuesta se valida con Pydantic y,
si no cumple, se pide una vez más con el error a la vista. En los niveles 1 a 3 el modelo responde JSON libre: todavía no
conoce el esquema, así que la respuesta no se corrige; solo se anota si lo cumple.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ..ingesta.leer_documento import normalizar
from .cliente_llm import configuracion_llm, preguntar
from .esquemas import ESQUEMAS
from .prompts import armar_mensajes


def _leer_json(texto: str, esquema: type[BaseModel], con_esquema: bool) -> dict[str, Any]:
    """El JSON de la respuesta: validado con el esquema si el prompt lo trae; si no, tal como llegó."""
    if con_esquema:
        return esquema.model_validate_json(texto).model_dump()
    crudo = json.loads(texto)
    if not isinstance(crudo, dict):
        raise ValueError("la respuesta no es un objeto JSON")
    return crudo


def _cumple(esquema: type[BaseModel], crudo: dict[str, Any]) -> bool:
    """Dice si un JSON libre cumple el esquema (claves, tipos y listas cerradas)."""
    try:
        esquema.model_validate({campo: crudo.get(campo) for campo in esquema.model_fields})
    except ValidationError:
        return False
    return True


def extraer_con_llm(texto: str, tipo: str, modelo: str | None = None, esquema: type[BaseModel] | None = None,
                    num_ctx: int | None = None, nivel: int | None = None, cfg: dict[str, Any] | None = None,
                    contexto: str | None = None) -> dict[str, Any]:
    """Extrae los campos de un texto con el prompt de su tipo y valida la respuesta.

    Args:
        texto: texto del documento (de ``texto_de``).
        tipo: ``poliza``, ``contrato``, ``oficio``, ``estado_financiero``, ``voucher``, ``reclamo``, ``tarifario``,
            ``expediente`` u otro con su propio ``esquema``.
        modelo: por defecto ``llm.modelo`` del YAML.
        esquema: otro esquema en lugar del esquema del tipo.
        num_ctx: contexto de la llamada; por defecto ``llm.num_ctx``.
        nivel: nivel del prompt (1 a 5); por defecto ``llm.prompt_nivel`` (5: Rol, Contexto, Tarea, Formato y un ejemplo).
        cfg: sección ``llm`` de la configuración.
        contexto: otro texto en lugar del Contexto del tipo (para probar un Contexto propio).

    Returns:
        ``campos`` (normalizados), ``crudo`` (lo que dijo el modelo), ``valido`` (cumple el esquema), ``intentos``,
        ``omitidos`` (claves que el modelo no escribió), ``nivel``, ``segundos``, ``tokens_entrada`` y ``fin``.
    """
    cfg = cfg or configuracion_llm()
    nivel = nivel or cfg["prompt_nivel"]
    esquema = esquema or ESQUEMAS[tipo]
    con_esquema = nivel >= 4
    mensajes = armar_mensajes(texto, tipo, nivel, esquema, cfg, contexto)
    modelo = modelo or cfg["modelo"]
    segundos = 0.0
    for intento in (1, 2):
        respuesta = preguntar(modelo, mensajes, esquema if con_esquema else "json", num_ctx=num_ctx, cfg=cfg)
        segundos += respuesta.segundos
        try:
            crudo = _leer_json(respuesta.texto, esquema, con_esquema)
        except (ValidationError, ValueError) as error:
            causa = "no cumple el esquema" if con_esquema else "no es un JSON válido"
            mensajes = mensajes + [{"role": "assistant", "content": respuesta.texto},
                                   {"role": "user", "content": f"La respuesta {causa}: {str(error)[:300]}. Corregirla y entregar solo el JSON."}]
            continue
        return {"campos": {campo: normalizar(campo, crudo.get(campo)) for campo in esquema.model_fields}, "crudo": crudo,
                "valido": con_esquema or _cumple(esquema, crudo), "intentos": intento,
                "omitidos": sum(campo not in crudo for campo in esquema.model_fields), "nivel": nivel,
                "segundos": round(segundos, 2), "tokens_entrada": respuesta.tokens_entrada, "fin": respuesta.fin}
    return {"campos": {campo: None for campo in esquema.model_fields}, "crudo": None, "valido": False, "intentos": 2,
            "omitidos": len(esquema.model_fields), "nivel": nivel, "segundos": round(segundos, 2),
            "tokens_entrada": respuesta.tokens_entrada, "fin": respuesta.fin}
