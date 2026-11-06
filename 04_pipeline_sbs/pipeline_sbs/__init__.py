"""pipeline_sbs: pipeline de extracción documental construido sesión a sesión.

Subpaquetes (uno por componente de la arquitectura de referencia):
    ingesta, preprocesamiento, ocr, calidad, extraccion, clasificacion,
    llm, orquestacion, almacenamiento, monitoreo y config.
"""
import logging

__version__ = "0.3.0"

# Una biblioteca no configura el logging de quien la usa: solo declara un NullHandler.
logging.getLogger("pipeline_sbs").addHandler(logging.NullHandler())
