"""La función de trabajo: lo que hace un proceso con un archivo. Vive en un módulo para que los procesos la encuentren.

En Windows cada proceso trabajador arranca un intérprete nuevo e importa los módulos: una función definida en el cuaderno no
existe para él. El trabajador no escribe en la base ni en el registro: procesa y devuelve su resultado.
S07 (caso): dos fallos que no lanzan error se vuelven visibles. Un PDF digital con pocos caracteres por página (truncado) va a
revisión con la causa ``texto_insuficiente``, y los rótulos de un formato nuevo se leen con los sinónimos del YAML.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract

from ..ingesta.leer_documento import campos_rotulados
from .config import Config
from .etapas import ejecutar_etapas
from .registro import reintentar


def _fijar_tesseract() -> None:
    """Cada proceso busca Tesseract por su cuenta: variable ``TESSERACT_CMD``, PATH o la carpeta estándar de Windows."""
    comando = (os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
               or str(Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR" / "tesseract.exe"))
    pytesseract.pytesseract.tesseract_cmd = comando


def contar_paginas(ruta: str | Path) -> int:
    """Páginas de un PDF; 1 para los demás formatos (o si el PDF no se puede abrir)."""
    if Path(ruta).suffix.lower() != ".pdf":
        return 1
    try:
        with pymupdf.open(str(ruta)) as pdf:
            return max(pdf.page_count, 1)
    except Exception:  # noqa: BLE001 - el conteo no debe detener el trabajo
        return 1


def completar_con_sinonimos(resultado: dict[str, Any], cfg: Config) -> list[str]:
    """Segunda lectura de rótulos con los sinónimos del YAML (``sinonimos_rotulos``): solo llena campos vacíos.

    Un emisor que cambia «Poliza:» por «Nro. de poliza -» no lanza error, pero deja campos vacíos. El sinónimo traduce el
    rótulo nuevo al de siempre y la lectura de rótulos de S05 hace el resto. Devuelve los campos que llenó.
    """
    sinonimos = ((getattr(cfg, "sinonimos_rotulos", None) or {}).get(resultado.get("tipo")) or {})
    vacios = [campo for campo, valor in resultado.get("campos", {}).items() if valor is None]
    if not sinonimos or not vacios or not resultado.get("texto"):
        return []
    texto = resultado["texto"]
    for nuevo, de_siempre in sinonimos.items():
        texto = re.sub(rf"(?im)^\s*{re.escape(nuevo)}\s*", f"{de_siempre} ", texto)
    leidos = campos_rotulados(resultado["tipo"], {"partes": [texto], "pendientes": [], "cabecera": None})
    llenados = [campo for campo in vacios if leidos.get(campo) is not None]
    for campo in llenados:
        resultado["campos"][campo] = leidos[campo]
    resultado["revisar"] = [campo for campo, valor in resultado["campos"].items() if valor is None]
    return llenados


def causas_de_revision(resultado: dict[str, Any], ruta: str | Path, cfg: Config) -> list[str]:
    """Causas que mandan un documento a revisión aunque no haya fallado: un PDF digital con menos caracteres por página que el mínimo."""
    minimo = float((getattr(cfg, "monitoreo", None) or {}).get("minimo_caracteres_pagina", 200))
    causas = []
    digital = Path(ruta).suffix.lower() == ".pdf" and resultado.get("paginas_ocr", 0) == 0
    if digital and resultado.get("caracteres", 0) / resultado["paginas"] < minimo:
        causas.append("texto_insuficiente")
    return causas


def procesar_archivo(ruta: str | Path, tipo: str, cfg: Config) -> dict[str, Any]:
    """Procesa un archivo con las etapas del YAML y devuelve su resultado; nunca lanza un error.

    Un error transitorio (archivo bloqueado) se reintenta con las esperas del YAML. Cualquier otro error deja el
    archivo en estado ``error`` con la etapa en que ocurrió: el lote sigue con los demás.

    Returns:
        El resultado de ``ejecutar_etapas`` más ``intentos``, ``segundos_total``, ``proceso`` (número del proceso que lo hizo)
        y, si el archivo se procesó, ``paginas``, ``causas_revision`` y ``por_sinonimo`` (S07).
    """
    _fijar_tesseract()
    inicio = time.perf_counter()
    try:
        resultado, intentos = reintentar(lambda: ejecutar_etapas(ruta, tipo, cfg), cfg.reintentos.intentos, cfg.reintentos.espera_s)
    except Exception as error:  # noqa: BLE001 - un archivo con error no detiene el lote
        resultado = {"archivo": Path(ruta).name, "tipo": tipo, "estado": "error", "motivo": f"error_en_etapa:{getattr(error, 'etapa', 'desconocida')}",
                     "detalle": f"{type(error).__name__}: {error}"[:300], "campos": {}, "fases": {}, "segundos": {}, "revisar": [], "ambiguos": [],
                     "paginas_ocr": 0, "caracteres": 0, "texto": ""}
        intentos = 1
    if resultado["estado"] == "ok":
        resultado["paginas"] = contar_paginas(ruta)
        resultado["por_sinonimo"] = completar_con_sinonimos(resultado, cfg)
        resultado["causas_revision"] = causas_de_revision(resultado, ruta, cfg)
    resultado.update(intentos=intentos, segundos_total=round(time.perf_counter() - inicio, 3), proceso=os.getpid())
    return resultado
