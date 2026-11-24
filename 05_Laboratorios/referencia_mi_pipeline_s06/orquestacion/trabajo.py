"""La función de trabajo: lo que hace un proceso con un archivo. Vive en un módulo para que los procesos la encuentren.

En Windows cada proceso trabajador arranca un intérprete nuevo e importa los módulos: una función definida en el cuaderno no
existe para él. El trabajador no escribe en la base ni en el registro: procesa y devuelve su resultado.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytesseract

from .config import Config
from .etapas import ejecutar_etapas
from .registro import reintentar


def _fijar_tesseract() -> None:
    """Cada proceso busca Tesseract por su cuenta: variable ``TESSERACT_CMD``, PATH o la carpeta estándar de Windows."""
    comando = (os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
               or str(Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR" / "tesseract.exe"))
    pytesseract.pytesseract.tesseract_cmd = comando


def procesar_archivo(ruta: str | Path, tipo: str, cfg: Config) -> dict[str, Any]:
    """Procesa un archivo con las etapas del YAML y devuelve su resultado; nunca lanza un error.

    Un error transitorio (archivo bloqueado) se reintenta con las esperas del YAML. Cualquier otro error deja el
    archivo en estado ``error`` con la etapa en que ocurrió: el lote sigue con los demás.

    Returns:
        El resultado de ``ejecutar_etapas`` más ``intentos``, ``segundos_total`` y ``proceso`` (número del proceso que lo hizo).
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
    resultado.update(intentos=intentos, segundos_total=round(time.perf_counter() - inicio, 3), proceso=os.getpid())
    return resultado
