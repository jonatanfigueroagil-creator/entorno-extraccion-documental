"""Las etapas del pipeline y su contrato: qué recibe y qué entrega cada una. Se recorren en el orden del YAML.

control -> ingesta -> ocr -> pln. Cada etapa es una función que recibe el estado del documento, agrega lo suyo y lo devuelve.
Ninguna etapa llama a un modelo de lenguaje: lo que queda vacío va a la lista «revisar» para que lo vea una persona.
Quitar una etapa de ``orquestacion.etapas`` en el YAML la salta: eso es un pipeline configurable.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import pipeline_sbs  # noqa: F401 - el paquete del curso que trae el control de ingesta de S02
except ImportError:  # si no está instalado en el entorno, se toma de la carpeta 04_pipeline_sbs del repositorio
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_pipeline_sbs"))
from pipeline_sbs.ingesta.cargador import calcular_sha256, detectar_formato, validar_formato_y_extension, verificar_apertura
from pipeline_sbs.ingesta.errores import traducir_excepcion

from ..extraccion.hibrido import campos_ambiguos
from ..extraccion.hibrido import pln as completar_con_pln
from ..ingesta.leer_documento import aplicar_ocr, campos_rotulados, leer_documento, texto_de
from ..llm.esquemas import ESQUEMAS, campos_de
from .config import Config


def control(d: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """Control de ingesta (S02): huella, formato por la firma, extensión y apertura. Lo dañado sale con su motivo."""
    ruta = Path(d["ruta"])
    d.update(sha256="", formato="desconocido", estado="ok", motivo="", detalle="")
    try:
        d["sha256"] = calcular_sha256(ruta)
        d["formato"] = detectar_formato(ruta)
        validar_formato_y_extension(ruta, d["formato"])
        verificar_apertura(ruta, d["formato"])
    except PermissionError:
        raise  # un archivo bloqueado no está dañado: el error sube para que se reintente
    except Exception as error:  # noqa: BLE001 - un archivo dañado no detiene el lote
        tipificado = traducir_excepcion(error)
        d.update(estado="cuarentena", motivo=tipificado.motivo, detalle=(tipificado.detalle or str(tipificado)).replace(str(ruta), ruta.name))
    return d


def ingesta(d: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """Ingesta (S05): el lector del formato y los campos que el documento trae con su rótulo."""
    d["doc"] = leer_documento(d["ruta"])
    rotulados = campos_rotulados(d["tipo"], d["doc"])
    d["campos"] = {campo: rotulados.get(campo) for campo in d["campos"]}
    return d


def ocr(d: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """OCR (S03): Tesseract lee lo que no trae capa de texto. Un campo que ya venía de la ingesta no se reemplaza."""
    d["paginas_ocr"] = len(d["doc"]["pendientes"])
    if d["doc"]["pendientes"]:
        d["doc"] = aplicar_ocr(d["doc"], motor=cfg.orquestacion.motor_ocr)
        rotulados = campos_rotulados(d["tipo"], d["doc"])
        d["campos"] = {campo: valor if valor is not None else rotulados.get(campo) for campo, valor in d["campos"].items()}
    return d


def pln(d: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """PLN (S04): las reglas y el NER completan lo vacío; lo que llenan sin rótulo queda anotado como ambiguo."""
    antes = dict(d["campos"])
    d["campos"] = completar_con_pln(d["tipo"], d["doc"], antes)
    d["ambiguos"] = campos_ambiguos(antes, d["campos"])
    return d


@dataclass(frozen=True)
class Etapa:
    """Una etapa con su contrato de datos."""

    nombre: str
    recibe: str
    entrega: str
    funcion: Callable[[dict[str, Any], Config], dict[str, Any]]


ETAPAS: dict[str, Etapa] = {
    "control": Etapa("control", "la ruta del archivo", "sha256, formato, estado (ok o cuarentena) y motivo", control),
    "ingesta": Etapa("ingesta", "la ruta de un archivo que pasó el control", "el documento leído (partes y pendientes de OCR) y los campos rotulados", ingesta),
    "ocr": Etapa("ocr", "el documento con partes pendientes", "el documento con todo su texto y los campos rotulados que faltaban", ocr),
    "pln": Etapa("pln", "el documento con su texto y los campos", "los campos completados por reglas y NER, y la lista de ambiguos", pln),
}


def ejecutar_etapas(ruta: str | Path, tipo: str, cfg: Config) -> dict[str, Any]:
    """Pasa un archivo por las etapas del YAML, en orden, y guarda lo que entrega cada una.

    Args:
        ruta: archivo a procesar.
        tipo: tipo de documento (``poliza``, ``contrato``, ``oficio``…); con un tipo sin esquema solo se lee el texto.
        cfg: configuración validada (``cargar_config``).

    Returns:
        ``archivo``, ``tipo``, ``estado`` (``ok`` o ``cuarentena``) y ``motivo``; ``campos`` (los finales), ``fases`` (los campos
        después de cada etapa), ``revisar`` (campos vacíos, para revisión humana), ``ambiguos``, ``segundos`` por etapa,
        ``paginas_ocr``, ``caracteres`` y ``texto``. Si el control aparta el archivo, las demás etapas no corren.
    """
    campos = campos_de(tipo) if tipo in ESQUEMAS else []
    d: dict[str, Any] = {"ruta": str(ruta), "archivo": Path(ruta).name, "tipo": tipo, "estado": "ok", "motivo": "", "campos": {campo: None for campo in campos},
                         "fases": {}, "segundos": {}, "ambiguos": [], "paginas_ocr": 0, "doc": None}
    for nombre in cfg.orquestacion.etapas:
        inicio = time.perf_counter()
        try:
            d = ETAPAS[nombre].funcion(d, cfg)
        except Exception as error:
            error.etapa = nombre  # quien atrapa el error sabe en qué etapa ocurrió
            raise
        d["segundos"][nombre] = round(time.perf_counter() - inicio, 4)
        if d["estado"] != "ok":
            break
        if nombre != "control":
            d["fases"][nombre] = dict(d["campos"])
    doc = d.pop("doc")
    d.pop("ruta")
    d["texto"] = texto_de(doc) if doc else ""
    d["caracteres"] = len(d["texto"])
    d["revisar"] = [campo for campo, valor in d["campos"].items() if valor is None] if d["estado"] == "ok" else []
    return d
