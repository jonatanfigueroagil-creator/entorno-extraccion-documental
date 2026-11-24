"""Prueba de regresión con golden set (S07): la salida aprobada de documentos conocidos se congela y cada cambio se compara con ella.

El golden set no compara con la respuesta correcta (esa comparación falla desde el primer día en los campos que el pipeline
todavía no lee): compara con la salida que se revisó y se aprobó. Aparte, la exactitud contra la respuesta correcta no puede
bajar de la línea base medida al congelar. Así, cualquier cambio de código o de configuración que mueva un campo se ve en
rojo, con el documento y el campo.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from ..monitoreo.registro import version_git
from ..orquestacion.etapas import ejecutar_etapas

CARPETA_GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden"
LINEA_BASE = "00_linea_base.json"
NO_SE_MIDEN = {"ambiguedad", "cuadra", "paginas", "n_paginas", "monto_en_texto", "canal", "adjunto"}


def localizar_datos() -> Path | None:
    """Carpeta de los datos de práctica: variable ``SBS_DATOS_PRACTICA``, la copia del curso o la carpeta de datos de la VM."""
    if os.environ.get("SBS_DATOS_PRACTICA") and Path(os.environ["SBS_DATOS_PRACTICA"]).is_dir():
        return Path(os.environ["SBS_DATOS_PRACTICA"])
    for carpeta in [*Path(__file__).resolve().parents, *Path.cwd().resolve().parents, Path.cwd().resolve()]:
        for candidata in (carpeta / "02_Datos_Practica", carpeta / "05_Laboratorios" / "02_Datos_Practica"):
            if (candidata / "10_Ground_Truth").is_dir():
                return candidata
    curso = Path(os.environ.get("SystemDrive", "C:") + os.sep) / "curso" / "datos"
    return curso if (curso / "10_Ground_Truth").is_dir() else None


def ruta_de(datos: Path, archivo: str) -> Path:
    """Dónde está un documento de práctica (``POL-0001.pdf`` -> ``05_Polizas/POL-0001.pdf``)."""
    hallados = sorted(datos.glob(f"*/{archivo}"))
    if not hallados:
        raise FileNotFoundError(f"No se encuentra {archivo} en los datos de práctica.")
    return hallados[0]


def salida_actual(datos: Path, archivo: str, tipo: str, cfg: Any) -> dict[str, Any]:
    """La salida de hoy de un documento, con los mismos tipos que el JSON congelado (fechas y números como en el archivo)."""
    resultado = ejecutar_etapas(ruta_de(datos, archivo), tipo, cfg)
    return json.loads(json.dumps({"archivo": archivo, "tipo": tipo, "campos": resultado["campos"]}, ensure_ascii=False, default=str))


def diferencias(actual: dict[str, Any], aprobada: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Campos que cambiaron: ``{campo: (valor aprobado, valor de hoy)}``."""
    return {campo: (aprobada.get(campo), actual.get(campo)) for campo in sorted(set(actual) | set(aprobada)) if actual.get(campo) != aprobada.get(campo)}


def _llano(texto: Any) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", base.lower()).strip(" .,:;")


def correcto_de(datos: Path, documento: str) -> dict[str, Any]:
    """La respuesta correcta de un documento (``10_Ground_Truth``), sin los campos que no se miden."""
    gt = json.loads((datos / "10_Ground_Truth" / f"{documento}.json").read_text(encoding="utf-8"))
    return {campo: valor for campo, valor in gt["campos"].items() if campo not in NO_SE_MIDEN and not isinstance(valor, (bool, dict, list))}


def es_correcto(valor: Any, correcto: Any) -> bool:
    """Medida estricta: el número como número, la fecha AAAA-MM-DD y el texto sin importar tildes ni mayúsculas."""
    if correcto is None or valor is None:
        return valor is None and correcto is None
    if isinstance(correcto, (int, float)):
        return isinstance(valor, (int, float)) and not isinstance(valor, bool) and abs(valor - correcto) < 0.011
    return _llano(valor) == _llano(correcto)


def exactitud(salidas: dict[str, dict[str, Any]], datos: Path) -> float:
    """Campos correctos / campos esperados de un conjunto de documentos (``{documento: campos}``)."""
    aciertos = esperados = 0
    for documento, campos in salidas.items():
        correcto = correcto_de(datos, documento)
        aciertos += sum(es_correcto(campos.get(campo), valor) for campo, valor in correcto.items())
        esperados += len(correcto)
    return round(aciertos / esperados, 4) if esperados else 0.0


def congelar(archivos: list[str], tipo: str, cfg: Any, datos: Path, carpeta: Path = CARPETA_GOLDEN) -> dict[str, Any]:
    """Congela la salida aprobada de cada documento en ``carpeta/<ID>.json`` y la línea base de exactitud en ``00_linea_base.json``.

    Se ejecuta una vez, después de revisar la salida; se vuelve a ejecutar solo cuando un cambio se revisa y se aprueba.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    salidas = {}
    for archivo in archivos:
        salida = salida_actual(datos, archivo, tipo, cfg)
        (carpeta / f"{Path(archivo).stem}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        salidas[Path(archivo).stem] = salida["campos"]
    base = {"documentos": sorted(salidas), "tipo": tipo, "exactitud": exactitud(salidas, datos), "version": version_git(),
            "fecha": datetime.now().isoformat(timespec="seconds")}
    (carpeta / LINEA_BASE).write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return base
