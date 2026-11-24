"""Pipeline de OCR de mi_pipeline: PDF o imagen -> imagen enderezada -> receta -> lectura -> puntaje -> decisión."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytesseract
import yaml
from PIL import Image

from .calidad.puntuar import puntuar
from .ocr.leer import leer_con_confianza
from .ocr.preprocesar import aplicar_receta, corregir_inclinacion
from .ocr.renderizar import pdf_a_imagen

RUTA_CONFIG = Path(__file__).parent / "config" / "pipeline.yaml"


def cargar_configuracion(ruta: str | Path = RUTA_CONFIG) -> dict[str, Any]:
    """Lee el archivo YAML de configuración y lo entrega como diccionario."""
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def configurar_tesseract(cfg: dict[str, Any]) -> str:
    """Indica a pytesseract dónde está el programa tesseract.

    Orden de búsqueda: variable de entorno ``TESSERACT_CMD``, clave ``ocr.tesseract_cmd`` del YAML,
    el PATH y la carpeta estándar de instalación en Windows.

    Raises:
        RuntimeError: si no se encuentra Tesseract.
    """
    comando = os.environ.get("TESSERACT_CMD") or cfg["ocr"].get("tesseract_cmd") or shutil.which("tesseract")
    if not comando:
        estandar = Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR" / "tesseract.exe"
        comando = str(estandar) if estandar.is_file() else None
    if not comando:
        raise RuntimeError("No se encontró Tesseract: indicar ocr.tesseract_cmd en el YAML o la variable TESSERACT_CMD")
    pytesseract.pytesseract.tesseract_cmd = comando
    return comando


def ejecutar(
    ruta: str | Path,
    cfg: dict[str, Any] | None = None,
    pagina: int = 0,
    enderezar: bool = True,
    receta: str | None = None,
) -> dict[str, Any]:
    """Procesa un PDF escaneado o una imagen de punta a punta.

    Args:
        ruta: archivo PDF, PNG o JPG.
        cfg: configuración (por defecto la del YAML).
        pagina: página del PDF, desde 0.
        enderezar: si es False no corrige la inclinación (útil con fotos con perspectiva).
        receta: reemplaza a ``ocr.receta`` del YAML (crudo, gris, otsu, adaptativa o mediana).

    Returns:
        Diccionario con ``archivo``, ``receta``, ``inclinacion`` e ``imagen`` (y, desde el paso 7,
        ``texto``, ``confianza``, ``puntaje`` y ``decision``).
    """
    cfg = cfg or cargar_configuracion()
    ocr = cfg["ocr"]
    configurar_tesseract(cfg)
    ruta = Path(ruta)
    receta = receta or ocr["receta"]
    if ruta.suffix.lower() == ".pdf":
        imagen = pdf_a_imagen(ruta, pagina, ocr["dpi"])
    else:
        imagen = np.array(Image.open(ruta).convert("RGB"))
    inclinacion = 0.0
    if enderezar:
        imagen, inclinacion = corregir_inclinacion(imagen)
    imagen = aplicar_receta(imagen, receta)
    resultado = {"archivo": ruta.name, "receta": receta, "inclinacion": inclinacion, "imagen": imagen}
    lectura = leer_con_confianza(imagen, ocr["lang"], ocr["oem"], ocr["psm"])
    puntaje = puntuar(lectura["texto"], lectura["confianza"])
    resultado.update(
        texto=lectura["texto"],
        confianza=lectura["confianza"],
        puntaje=puntaje,
        decision=enrutar(puntaje, cfg["calidad"]["umbral_score"]),
    )
    return resultado


def enrutar(puntaje: dict[str, Any], umbral: float = 0.8) -> str:
    """Decide qué pasa con una lectura: ``aceptar``, ``revisar`` o ``rechazar``.

    Args:
        puntaje: resultado de ``puntuar`` (con ``score`` e ``invalidos``).
        umbral: puntaje mínimo para aceptar sin revisión.

    Returns:
        ``aceptar`` si el puntaje llega al umbral y ningún validador falló; ``revisar`` si el puntaje llega
        a la mitad del umbral; ``rechazar`` en los demás casos.
    """
    if puntaje["score"] >= umbral and puntaje["invalidos"] == 0:
        return "aceptar"
    if puntaje["score"] >= umbral / 2:
        return "revisar"
    return "rechazar"


# S04: extracción de campos y motivo a partir del correo y del texto de su adjunto
import copy
import json
import tempfile
import time

from .clasificacion.motivo import predecir
from .extraccion.montos import extraer_monto
from .extraccion.ner import entidades_a_campos, ner_spacy
from .extraccion.reglas import (
    extraer_correo_electronico,
    extraer_dni,
    extraer_entidad,
    extraer_fecha,
    extraer_nombre,
    extraer_producto,
    extraer_telefono,
)
from .extraccion.texto import leer_correo

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
        lectura = ejecutar(archivo, cfg_ocr, enderezar=extraccion["enderezar_adjunto"], receta=extraccion["receta_adjunto"])
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
    ocr = leer_adjunto(id_correo, correo["adjuntos"], cfg, carpeta_ocr)
    texto = f"De: {correo['remitente']}\n{correo['cuerpo']}\n{ocr['texto']}"
    campos = extraer_campos(texto, cfg)
    motivo, confianza = (predecir(modelo_motivo, [correo["cuerpo"]])[0] if modelo_motivo is not None else (None, 0.0))
    campos["motivo"] = motivo
    campos["numero_reclamo"] = None     # no consta en el documento: un dato que no consta no se inventa
    faltantes = [c for c in CAMPOS_OBLIGATORIOS if campos[c] is None]
    causas = ["ruta del OCR"] if ocr["decision"] != "aceptar" else []
    causas += [f"campo faltante: {c}" for c in faltantes]
    causas += ["confianza del motivo"] if confianza < cfg["clasificacion"]["umbral_confianza"] else []
    resultado = {"id": id_correo, "archivo": ruta.name, "campos": campos, "confianza_motivo": confianza,
                 "ocr": {"score": ocr["score"], "confianza": ocr["confianza"], "decision": ocr["decision"], "motor": ocr["motor"]},
                 "notas": {"numero_reclamo": "no consta en el documento"}, "faltantes": faltantes, "causas_revision": causas, "ruta": "revisar" if causas else "aceptar",
                 "segundos": round(time.perf_counter() - inicio, 3)}
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
            resultados.append({"id": eml.stem, "archivo": eml.name, "error": f"{type(error).__name__}: {error}", "ruta": "revisar"})
    return resultados
