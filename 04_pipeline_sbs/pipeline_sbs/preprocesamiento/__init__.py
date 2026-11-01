"""Preprocesamiento de documentos: normalización de texto (S02) y, desde S03, limpieza de imágenes antes del OCR."""
from pipeline_sbs.preprocesamiento.normalizacion import (
    normalizar_texto,
    parsear_fecha,
    parsear_monto,
    unir_guiones,
)

__all__ = ["normalizar_texto", "unir_guiones", "parsear_fecha", "parsear_monto"]
