"""El registro del lote: qué se procesó, qué falló y por qué. Con él, repetir una corrida no repite el trabajo.

Idempotencia: la huella SHA-256 identifica el contenido de un archivo; si el registro ya la tiene con un estado final, no se
procesa de nuevo. Reintentos: solo ante errores transitorios (un archivo bloqueado), con esperas crecientes. Cuarentena:
lo dañado no se reintenta; se aparta con su motivo y el lote sigue.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import duckdb

ESTADOS = ("ok", "cuarentena", "duplicado", "error")
TERMINADOS = ("ok", "cuarentena", "duplicado")  # estados finales: repetir no cambia el resultado; «error» sí se intenta de nuevo
TABLA_REGISTRO = """CREATE TABLE IF NOT EXISTS registro (
    sha256 VARCHAR, archivo VARCHAR, estado VARCHAR, motivo VARCHAR, intentos INTEGER, segundos DOUBLE, fecha VARCHAR,
    PRIMARY KEY (sha256, archivo))"""
TABLA_CORRIDAS = """CREATE TABLE IF NOT EXISTS corridas (
    inicio VARCHAR PRIMARY KEY, modo VARCHAR, trabajadores INTEGER, archivos INTEGER, saltados INTEGER, ok INTEGER, cuarentena INTEGER,
    duplicados INTEGER, errores INTEGER, segundos DOUBLE, documentos_por_minuto DOUBLE)"""


def huella(ruta: str | Path) -> str:
    """Huella SHA-256 del contenido: dos archivos con el mismo contenido tienen la misma huella, aunque cambie el nombre."""
    with open(ruta, "rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def abrir_registro(ruta_db: str | Path) -> duckdb.DuckDBPyConnection:
    """Abre la base (la crea si no existe) con las tablas ``registro`` y ``corridas``. Solo un proceso puede escribir en ella."""
    Path(ruta_db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta_db))
    con.execute(TABLA_REGISTRO)
    con.execute(TABLA_CORRIDAS)
    return con


def ya_procesado(con: duckdb.DuckDBPyConnection, sha256: str) -> bool:
    """Dice si un contenido con esa huella ya tiene un estado final en el registro."""
    fila = con.execute("SELECT count(*) FROM registro WHERE sha256 = ? AND estado IN ('ok', 'cuarentena', 'duplicado')", [sha256]).fetchone()
    return fila[0] > 0


def marcar(con: duckdb.DuckDBPyConnection, sha256: str, archivo: str, estado: str, motivo: str = "", intentos: int = 1, segundos: float = 0.0) -> None:
    """Anota el estado de un archivo. ``INSERT OR REPLACE`` sobre la clave: repetir la anotación no duplica la fila."""
    if estado not in ESTADOS:
        raise ValueError(f"estado desconocido: {estado}")
    con.execute("INSERT OR REPLACE INTO registro VALUES (?, ?, ?, ?, ?, ?, ?)",
                [sha256, archivo, estado, motivo, intentos, round(segundos, 3), datetime.now().isoformat(timespec="seconds")])


def anotar_corrida(con: duckdb.DuckDBPyConnection, fila: dict[str, Any]) -> None:
    """Anota una corrida del lote (modo, trabajadores, cuántos archivos, segundos y documentos por minuto)."""
    con.execute("INSERT OR REPLACE INTO corridas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [fila[c] for c in ("inicio", "modo", "trabajadores", "archivos", "saltados", "ok", "cuarentena", "duplicados", "errores", "segundos", "documentos_por_minuto")])


def es_transitorio(error: BaseException) -> bool:
    """Un error transitorio se arregla solo al esperar: el archivo está bloqueado por otro programa (antivirus, sincronizador)."""
    if isinstance(error, PermissionError):
        return True
    return isinstance(error, OSError) and (getattr(error, "winerror", None) in (32, 33) or error.errno in (errno.EBUSY, errno.EAGAIN))


def reintentar(funcion: Callable[[], Any], intentos: int = 3, esperas: Sequence[float] = (1, 2, 4),
               dormir: Callable[[float], None] = time.sleep) -> tuple[Any, int]:
    """Llama a ``funcion`` y, si falla con un error transitorio, espera y repite: hasta ``intentos`` repeticiones.

    Args:
        funcion: operación sin argumentos (se arma con ``lambda``); debe poder repetirse sin efectos dobles.
        intentos: repeticiones máximas después de la primera llamada.
        esperas: segundos antes de cada repetición (1, 2 y 4: cada espera duplica la anterior).
        dormir: función que espera; en las pruebas se cambia para no esperar de verdad.

    Returns:
        El resultado de ``funcion`` y cuántas llamadas hizo falta (1 si salió a la primera).

    Raises:
        El error original si no es transitorio (no se reintenta) o si se agotaron las repeticiones.
    """
    for llamada in range(1, intentos + 2):
        try:
            return funcion(), llamada
        except Exception as error:
            if not es_transitorio(error) or llamada > intentos:
                raise
            dormir(esperas[min(llamada - 1, len(esperas) - 1)])
    raise RuntimeError("no se llega aquí")


def a_cuarentena(ruta: str | Path, carpeta: str | Path, motivo: str, detalle: str = "") -> Path:
    """Copia (no mueve) el archivo a la carpeta de cuarentena y agrega una línea con su motivo a ``registro_errores.jsonl``."""
    ruta, carpeta = Path(ruta), Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / ruta.name
    temporal = destino.with_name(destino.name + ".tmp")
    shutil.copy2(ruta, temporal)
    os.replace(temporal, destino)  # reemplaza si ya existía: repetir no falla ni deja dos copias
    with open(carpeta / "registro_errores.jsonl", "a", encoding="utf-8") as bitacora:
        bitacora.write(json.dumps({"archivo": ruta.name, "motivo": motivo, "detalle": detalle[:300],
                                   "fecha": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    return destino
