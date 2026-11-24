"""Secretos y arranque seguro (S07).

1. Los secretos (claves de un servicio, tokens) se leen solo de variables de entorno: nunca del YAML ni del repositorio.
   El valor leído se anota en el registro como secreto: si alguien lo escribe por error en un evento, sale ``[OCULTO]``.
2. ``verificar_arranque`` revisa, antes de tocar un documento, lo que el lote necesita: Tesseract existe y responde, la
   carpeta de entrada se puede leer, la de salida se puede escribir y no está dentro de la de entrada, y el YAML no trae
   secretos. Si algo falta, el pipeline se detiene con un mensaje claro (fallo temprano), no a mitad del lote.
3. Mínimo privilegio: el pipeline no necesita la cuenta de administrador; si corre con ella, se avisa.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..monitoreo.registro import PALABRAS_SECRETAS, ocultar_valor


class ErrorSecreto(RuntimeError):
    """Falta un secreto obligatorio en las variables de entorno."""


def leer_secreto(nombre: str, obligatorio: bool = True) -> str | None:
    """Lee un secreto de una variable de entorno y lo anota para que el registro lo oculte.

    Args:
        nombre: variable de entorno (por ejemplo ``PIPELINE_CLAVE_DEMO``).
        obligatorio: si falta y es obligatorio, se lanza ``ErrorSecreto``; si no, se devuelve ``None``.
    """
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        if obligatorio:
            raise ErrorSecreto(f"Falta la variable de entorno {nombre}. Un secreto se define en la cuenta del usuario o en un archivo "
                               ".env fuera del repositorio, nunca en el YAML.")
        return None
    ocultar_valor(valor)
    return valor


def secretos_en_config(datos: Any, lugar: str = "") -> list[str]:
    """Claves del YAML que parecen secretos (``api_key``, ``token``, ``clave``…) y traen un valor escrito."""
    hallados = []
    if isinstance(datos, dict):
        for clave, valor in datos.items():
            ruta = f"{lugar}.{clave}" if lugar else str(clave)
            if isinstance(valor, str) and valor.strip() and any(p in str(clave).lower() for p in PALABRAS_SECRETAS):
                hallados.append(ruta)
            hallados += secretos_en_config(valor, ruta)
    return hallados


def comando_tesseract() -> str:
    """Dónde se busca Tesseract: variable ``TESSERACT_CMD``, PATH o la carpeta estándar de Windows (como ``trabajo.py``)."""
    return (os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
            or str(Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR" / "tesseract.exe"))


def es_administrador() -> bool:
    """True si el proceso corre con privilegios de administrador (Windows) o como root."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except AttributeError:
        return hasattr(os, "geteuid") and os.geteuid() == 0


def verificar_arranque(cfg: Any, entrada: str | Path, salida: str | Path) -> list[str]:
    """Revisa lo que el lote necesita antes de procesar el primer documento.

    Args:
        cfg: configuración validada.
        entrada: carpeta con los archivos recibidos (solo se lee).
        salida: carpeta donde quedan la base, el registro, el reporte y la cuarentena.

    Returns:
        Lista de problemas, una frase cada uno; vacía si se puede arrancar.
    """
    problemas = []
    if "ocr" in cfg.orquestacion.etapas:
        comando = comando_tesseract()
        if not Path(comando).is_file() and not shutil.which(comando):
            problemas.append(f"Tesseract no está en {comando} (se busca en la variable TESSERACT_CMD, en el PATH y en la carpeta estándar).")
        else:
            try:
                respuesta = subprocess.run([comando, "--version"], capture_output=True, text=True, timeout=30)
                if respuesta.returncode != 0:
                    problemas.append(f"Tesseract no responde ({comando} --version devolvió {respuesta.returncode}).")
            except (OSError, subprocess.SubprocessError) as error:
                problemas.append(f"Tesseract no responde: {error}")
    entrada, salida = Path(entrada), Path(salida)
    if not entrada.is_dir():
        problemas.append(f"La carpeta de entrada no existe: {entrada}")
    elif not os.access(entrada, os.R_OK):
        problemas.append(f"La carpeta de entrada no se puede leer con esta cuenta: {entrada}")
    elif entrada.resolve() in (salida.resolve(), *salida.resolve().parents):
        problemas.append("La carpeta de salida está dentro de la de entrada: los datos recibidos solo se leen, nunca se escriben.")
    try:
        salida.mkdir(parents=True, exist_ok=True)
        prueba = salida / ".prueba_escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
    except OSError as error:
        problemas.append(f"No se puede escribir en la carpeta de salida {salida}: {error.strerror or error}")
    datos = cfg.model_dump() if hasattr(cfg, "model_dump") else dict(cfg)
    if secretos := secretos_en_config(datos):
        problemas.append(f"El YAML trae secretos ({', '.join(secretos)}): un secreto va en una variable de entorno, nunca en el YAML.")
    return problemas
