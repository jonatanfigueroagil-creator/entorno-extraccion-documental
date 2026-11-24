"""Pipeline de OCR (S03): PDF o imagen -> imagen enderezada -> receta -> lectura -> puntaje -> decisión."""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytesseract
from PIL import Image

from ..calidad.puntuar import puntuar
from ..config.configuracion import cargar_configuracion
from ..ocr.leer import leer_con_confianza
from ..ocr.preprocesar import aplicar_receta, corregir_inclinacion
from ..ocr.renderizar import pdf_a_imagen

registro = logging.getLogger(__name__)


def configurar_tesseract(cfg: dict[str, Any]) -> str:
    """Indica a pytesseract dónde está el programa tesseract.

    Orden de búsqueda: variable de entorno ``TESSERACT_CMD``, clave ``ocr.tesseract_cmd`` del YAML,
    el PATH y la carpeta estándar de instalación en Windows.

    Returns:
        Ruta o nombre del programa que se usará.

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


def enrutar(puntaje: dict[str, Any], umbral: float = 0.85) -> str:
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


def ejecutar_ocr(
    ruta: str | Path,
    cfg: dict[str, Any] | None = None,
    pagina: int = 0,
    enderezar: bool = True,
    receta: str | None = None,
) -> dict[str, Any]:
    """Procesa un PDF escaneado o una imagen de punta a punta.

    Args:
        ruta: archivo PDF, PNG o JPG.
        cfg: configuración (por defecto la del YAML del paquete).
        pagina: página del PDF, desde 0.
        enderezar: si es False no corrige la inclinación (útil con fotos con perspectiva).
        receta: reemplaza a ``ocr.receta`` del YAML (crudo, gris, otsu, adaptativa o mediana).

    Returns:
        Diccionario con ``archivo``, ``receta``, ``inclinacion``, ``imagen``, ``texto``, ``confianza``,
        ``puntaje`` y ``decision``.
    """
    inicio = time.perf_counter()  # solo referencia
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
    registro.info("etapa_preprocesar", extra={"componente": "ocr", "archivo": ruta.name, "receta": receta, "inclinacion": inclinacion})  # solo referencia
    lectura = leer_con_confianza(imagen, ocr["lang"], ocr["oem"], ocr["psm"])
    puntaje = puntuar(lectura["texto"], lectura["confianza"])
    decision = enrutar(puntaje, cfg["calidad"]["umbral_score"])
    registro.info("etapa_leer", extra={"componente": "ocr", "archivo": ruta.name, "score": puntaje["score"], "decision": decision, "segundos": round(time.perf_counter() - inicio, 2)})  # solo referencia
    return {"archivo": ruta.name, "receta": receta, "inclinacion": inclinacion, "imagen": imagen,
            "texto": lectura["texto"], "confianza": lectura["confianza"], "puntaje": puntaje, "decision": decision}
