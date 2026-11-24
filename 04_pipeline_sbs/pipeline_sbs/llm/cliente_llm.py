"""Cliente del LLM local (Ollama): una llamada con esquema, contexto fijo y medida de segundos y tokens."""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    import ollama
except ImportError:  # sin el paquete, las funciones que llaman al modelo avisan qué falta
    ollama = None

RUTA_CONFIG = Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml"
HOST_LOCAL = "http://127.0.0.1:11434"  # 127.0.0.1 y no «localhost»: en Windows «localhost» prueba antes la dirección IPv6 (el formato nuevo de direcciones de red) y cada conexión tarda 2 s más


class AvisoCorte(UserWarning):
    """La respuesta del modelo se cortó al llegar al límite de tokens."""


warnings.simplefilter("always", AvisoCorte)


@dataclass
class Respuesta:
    """Lo que devuelve una llamada al modelo: el texto y cómo se produjo."""

    texto: str
    segundos: float
    tokens_entrada: int
    tokens_salida: int
    fin: str
    modelo: str


def leer_yaml(ruta: str | Path = RUTA_CONFIG) -> dict[str, Any]:
    """Lee el archivo de configuración completo."""
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def configuracion_llm(ruta: str | Path = RUTA_CONFIG) -> dict[str, Any]:
    """La sección ``llm`` del YAML: dónde corre el modelo (``backend``), modelos, contexto, tope de salida, temperatura y semilla."""
    return leer_yaml(ruta)["llm"]


def conectar(cfg: dict[str, Any] | None = None) -> Any:
    """Devuelve el cliente de Ollama que indica ``llm.backend``.

    ``ollama_local`` usa el servidor de la propia VM; ``servidor_compartido`` usa el que indique la variable
    de entorno ``OLLAMA_HOST``. El cliente se crea una vez y se reutiliza en todas las llamadas.

    Raises:
        RuntimeError: si falta el paquete ``ollama``.
        ValueError: con ``api_nube`` u otro valor, porque en el laboratorio ningún documento sale a servicios externos.
    """
    cfg = cfg or configuracion_llm()
    if cfg["backend"] not in ("ollama_local", "servidor_compartido"):
        raise ValueError(f"Backend no permitido en el laboratorio: {cfg['backend']} (ningún documento sale a servicios externos).")
    if ollama is None:
        raise RuntimeError("Falta el paquete ollama: se instala con el archivo de requisitos del curso (pip install ollama).")
    return _cliente(cfg["backend"])


@lru_cache(maxsize=2)
def _cliente(backend: str) -> Any:
    """Un solo cliente por servidor (``backend``): abrir una conexión nueva en cada llamada cuesta tiempo."""
    return ollama.Client(host=HOST_LOCAL) if backend == "ollama_local" else ollama.Client()


def preguntar(
    modelo: str,
    mensaje: str | list[dict[str, Any]],
    esquema: Any = None,
    imagenes: list[bytes] | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> Respuesta:
    """Hace una llamada al modelo y mide cuánto tardó y cuántos tokens leyó y escribió.

    Args:
        modelo: nombre del modelo en Ollama (por ejemplo ``qwen3.5:4b`` o ``glm-ocr``).
        mensaje: el texto del pedido, o la conversación completa (lista de mensajes) para un segundo intento.
        esquema: clase de Pydantic que la respuesta debe cumplir, ``"json"`` para JSON libre, o None para texto libre.
        imagenes: imágenes PNG o JPG (en bytes) que acompañan al pedido.
        num_ctx: contexto en tokens (entrada más salida); por defecto ``llm.num_ctx`` del YAML.
        num_predict: tope de tokens de salida; por defecto ``llm.num_predict`` del YAML.
        cfg: sección ``llm`` de la configuración (por defecto la del YAML).

    Returns:
        Una ``Respuesta`` con el texto, los segundos, los tokens de entrada y de salida y el motivo de fin:
        ``stop`` si el modelo terminó y ``length`` si se cortó por el límite (en ese caso, además, avisa).
    """
    cfg = cfg or configuracion_llm()
    mensajes = [{"role": "user", "content": mensaje}] if isinstance(mensaje, str) else list(mensaje)
    if imagenes:
        mensajes[0] = {**mensajes[0], "images": list(imagenes)}
    formato = esquema if esquema is None or isinstance(esquema, str) else esquema.model_json_schema()
    opciones = {"temperature": cfg["temperatura"], "seed": cfg["semilla"],
                "num_ctx": num_ctx or cfg["num_ctx"], "num_predict": num_predict or cfg["num_predict"]}
    inicio = time.perf_counter()
    salida = conectar(cfg).chat(model=modelo, messages=mensajes, format=formato, think=False, options=opciones)
    respuesta = Respuesta(texto=salida.message.content or "", segundos=round(time.perf_counter() - inicio, 2),
                          tokens_entrada=salida.prompt_eval_count or 0, tokens_salida=salida.eval_count or 0,
                          fin=salida.done_reason or "", modelo=modelo)
    if respuesta.fin == "length":
        warnings.warn(f"{modelo}: la respuesta se cortó en {respuesta.tokens_salida} tokens de salida "
                      f"(fin = length, contexto {opciones['num_ctx']}); lo que falta no llegó.", AvisoCorte, stacklevel=2)
    return respuesta


def modelos_cargados(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Modelos que Ollama tiene en memoria y la VRAM que ocupa cada uno, en GB (lo mismo que ``ollama ps``)."""
    return [{"modelo": m.model, "vram_gb": round((m.size_vram or 0) / 1e9, 1), "contexto": m.context_length}
            for m in conectar(cfg).ps().models]


def ollama_disponible(modelo: str | None = None, cfg: dict[str, Any] | None = None) -> bool:
    """Dice si el servidor de Ollama responde y, si se indica, si el modelo ya está descargado."""
    if ollama is None:
        return False
    try:
        cfg = cfg or configuracion_llm()
        host = HOST_LOCAL if cfg["backend"] == "ollama_local" else None
        nombres = [m.model for m in ollama.Client(host=host, timeout=5).list().models]
    except Exception:  # sin servidor: conexión rechazada o tiempo agotado
        return False
    return modelo is None or modelo in nombres or f"{modelo}:latest" in nombres
