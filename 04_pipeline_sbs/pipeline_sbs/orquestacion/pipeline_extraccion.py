"""Pipeline de extracción (S04): correo -> OCR del adjunto (S03) -> campos -> motivo -> confianza y ruta.

Por cada correo devuelve un diccionario que la sesión siguiente (S05) recibe: los campos extraídos, el motivo, la
confianza y la ruta (``aceptar`` o ``revisar``). Un correo defectuoso nunca detiene el lote.
"""
from __future__ import annotations

import copy
import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config.configuracion import cargar_configuracion
from ..extraccion.montos import extraer_monto
from ..extraccion.ner import entidades_a_campos, ner_spacy
from ..extraccion.reglas import (
    extraer_correo_electronico,
    extraer_dni,
    extraer_entidad,
    extraer_fecha,
    extraer_nombre,
    extraer_producto,
    extraer_telefono,
)
from ..extraccion.texto import leer_correo
from ..clasificacion.motivo import predecir
from .pipeline_ocr import ejecutar_ocr

registro = logging.getLogger(__name__)

CAMPOS_OBLIGATORIOS = ("dni", "nombre", "monto_reclamado", "entidad", "fecha")


def leer_adjunto(id_correo: str, adjuntos: list, cfg: dict[str, Any], carpeta_ocr: str | Path | None = None) -> dict[str, Any]:
    """Obtiene el texto del adjunto: lee la salida guardada del OCR de S03 o corre el OCR sobre el archivo adjunto.

    Args:
        id_correo: identificador del correo (``REC-0001``).
        adjuntos: lista de pares (nombre, bytes) del correo.
        cfg: configuración del pipeline.
        carpeta_ocr: carpeta con un .json de OCR por correo (respaldo y modo rápido).

    Returns:
        ``{"texto", "confianza", "score", "decision", "motor"}``; sin adjunto el texto queda vacío y la decisión es ``rechazar``.
    """
    guardado = Path(carpeta_ocr) / f"{id_correo}.json" if carpeta_ocr else None
    if guardado is not None and guardado.is_file():
        datos = json.loads(guardado.read_text(encoding="utf-8"))
        return {"texto": datos["texto"], "confianza": datos["confianza"], "score": datos["score"],
                "decision": datos["decision"], "motor": "ocr_guardado"}
    if not adjuntos:
        return {"texto": "", "confianza": 0.0, "score": 0.0, "decision": "rechazar", "motor": "sin_adjunto"}
    nombre, contenido = adjuntos[0]
    extraccion = cfg["extraccion"]
    cfg_ocr = copy.deepcopy(cfg)
    cfg_ocr["ocr"]["psm"] = extraccion["psm_adjunto"]
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / nombre
        archivo.write_bytes(contenido)
        lectura = ejecutar_ocr(archivo, cfg_ocr, enderezar=extraccion["enderezar_adjunto"], receta=extraccion["receta_adjunto"])
    return {"texto": lectura["texto"], "confianza": lectura["confianza"], "score": lectura["puntaje"]["score"],
            "decision": lectura["decision"], "motor": "tesseract"}


def extraer_campos(texto: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Aplica las reglas a un texto y completa nombre y entidad con spaCy cuando las reglas no los hallan.

    Args:
        texto: remitente, cuerpo del correo y texto del OCR del adjunto (el remitente aporta el correo electrónico).
        cfg: configuración del pipeline.
    """
    campos = {
        "dni": extraer_dni(texto),
        "nombre": extraer_nombre(texto),
        "monto_reclamado": extraer_monto(texto),
        "entidad": extraer_entidad(texto),
        "telefono": extraer_telefono(texto),
        "correo": extraer_correo_electronico(texto),
        "producto": extraer_producto(texto),
        "fecha": extraer_fecha(texto),
    }
    if campos["nombre"] is None or campos["entidad"] is None:
        respaldo = entidades_a_campos(ner_spacy(texto, cfg["extraccion"]["modelo_spacy"]))
        campos["nombre"] = campos["nombre"] or respaldo["nombre"]
        campos["entidad"] = campos["entidad"] or respaldo["entidad"]
    return campos


def extraer(
    ruta: str | Path,
    cfg: dict[str, Any] | None = None,
    modelo_motivo: Any = None,
    carpeta_ocr: str | Path | None = None,
) -> dict[str, Any]:
    """Extrae los datos de un correo de reclamo de punta a punta.

    Args:
        ruta: archivo .eml con un adjunto (imagen o PDF).
        cfg: configuración (por defecto la del YAML del paquete).
        modelo_motivo: clasificador entrenado con ``entrenar``; sin él, el motivo queda vacío.
        carpeta_ocr: carpeta con el OCR guardado de los adjuntos (si no, se corre el OCR).

    Returns:
        ``{"id", "archivo", "campos", "confianza_motivo", "ocr", "notas", "faltantes", "causas_revision", "ruta", "segundos"}``.
        ``numero_reclamo`` queda en None con la nota «no consta en el documento».
        ``ruta`` es ``aceptar`` solo si el OCR de S03 dijo «aceptar», no faltan campos obligatorios y la confianza del
        motivo llega al umbral; en otro caso es ``revisar`` y ``causas_revision`` dice por qué.
    """
    inicio = time.perf_counter()
    cfg = cfg or cargar_configuracion()
    ruta = Path(ruta)
    id_correo = ruta.stem
    correo = leer_correo(ruta)
    registro.info("etapa_texto", extra={"componente": "extraccion", "correo": id_correo, "caracteres": len(correo["cuerpo"])})  # solo referencia
    ocr = leer_adjunto(id_correo, correo["adjuntos"], cfg, carpeta_ocr)
    registro.info("etapa_ocr", extra={"componente": "extraccion", "correo": id_correo, "score": ocr["score"], "decision": ocr["decision"]})  # solo referencia
    texto = f"De: {correo['remitente']}\n{correo['cuerpo']}\n{ocr['texto']}"
    campos = extraer_campos(texto, cfg)
    registro.info("etapa_campos", extra={"componente": "extraccion", "correo": id_correo, "hallados": sum(v is not None for v in campos.values())})  # solo referencia
    motivo, confianza = (predecir(modelo_motivo, [correo["cuerpo"]])[0] if modelo_motivo is not None else (None, 0.0))
    campos["motivo"] = motivo
    campos["numero_reclamo"] = None     # no consta en el documento: un dato que no consta no se inventa
    registro.info("etapa_motivo", extra={"componente": "extraccion", "correo": id_correo, "motivo": motivo, "confianza": confianza})  # solo referencia
    faltantes = [c for c in CAMPOS_OBLIGATORIOS if campos[c] is None]
    causas = ["ruta del OCR"] if ocr["decision"] != "aceptar" else []
    causas += [f"campo faltante: {c}" for c in faltantes]
    causas += ["confianza del motivo"] if confianza < cfg["clasificacion"]["umbral_confianza"] else []
    resultado = {"id": id_correo, "archivo": ruta.name, "campos": campos, "confianza_motivo": confianza,
                 "ocr": {"score": ocr["score"], "confianza": ocr["confianza"], "decision": ocr["decision"], "motor": ocr["motor"]},
                 "notas": {"numero_reclamo": "no consta en el documento"}, "faltantes": faltantes, "causas_revision": causas, "ruta": "revisar" if causas else "aceptar",
                 "segundos": round(time.perf_counter() - inicio, 3)}
    registro.info("etapa_ruta", extra={"componente": "extraccion", "correo": id_correo, "ruta": resultado["ruta"], "segundos": resultado["segundos"]})  # solo referencia
    return resultado


def extraer_lote(
    carpeta: str | Path,
    cfg: dict[str, Any] | None = None,
    modelo_motivo: Any = None,
    carpeta_ocr: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Corre ``extraer`` sobre todos los .eml de una carpeta; un correo con error queda marcado y el lote sigue.

    Returns:
        Una lista con un resultado por correo; si falla, ``{"id", "archivo", "error", "ruta": "revisar"}``.
    """
    cfg = cfg or cargar_configuracion()
    resultados = []
    for eml in sorted(Path(carpeta).glob("*.eml")):
        try:
            resultados.append(extraer(eml, cfg, modelo_motivo, carpeta_ocr))
        except Exception as error:  # un correo dañado no detiene el lote
            registro.warning("correo_con_error", extra={"correo": eml.stem, "motivo": type(error).__name__})  # solo referencia
            resultados.append({"id": eml.stem, "archivo": eml.name, "error": f"{type(error).__name__}: {error}", "ruta": "revisar"})
    return resultados
