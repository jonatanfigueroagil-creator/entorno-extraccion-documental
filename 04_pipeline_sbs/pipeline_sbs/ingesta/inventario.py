"""Inventario de documentos: qué llegó, de qué tipo es y si necesita OCR."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pypdf

from pipeline_sbs.documento import Documento

registro = logging.getLogger(__name__)

# Aquí se exportan las funciones del LAB (tiene_capa_texto e inventariar).
