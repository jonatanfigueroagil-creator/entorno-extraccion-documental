"""Almacenamiento de los resultados: DuckDB para consultar y Parquet para entregar.

Tres tablas: ``documentos`` (una fila por contenido recibido), ``campos`` (una fila por campo de cada documento, con su valor
después de cada etapa) y ``registro`` (una fila por archivo, la escribe el lote). ``INSERT OR REPLACE`` sobre la clave primaria:
guardar dos veces lo mismo deja las mismas filas.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

TABLA_DOCUMENTOS = """CREATE TABLE IF NOT EXISTS documentos (
    archivo VARCHAR PRIMARY KEY, tipo VARCHAR, formato VARCHAR, sha256 VARCHAR, estado VARCHAR, motivo VARCHAR, paginas_ocr INTEGER,
    caracteres INTEGER, campos_llenos INTEGER, campos_vacios INTEGER, seg_control DOUBLE, seg_ingesta DOUBLE, seg_ocr DOUBLE, seg_pln DOUBLE)"""
TABLA_CAMPOS = """CREATE TABLE IF NOT EXISTS campos (
    archivo VARCHAR, tipo VARCHAR, campo VARCHAR, valor VARCHAR, etapa VARCHAR, revisar BOOLEAN,
    tras_ingesta VARCHAR, tras_ocr VARCHAR, tras_pln VARCHAR, PRIMARY KEY (archivo, campo))"""
TABLAS = ("documentos", "campos", "registro", "corridas")
ORDEN = {"documentos": "archivo", "campos": "archivo, campo", "registro": "archivo", "corridas": "inicio"}


def _json(valor: Any) -> str | None:
    """El valor como texto JSON (conserva si era número o texto); None si está vacío."""
    return None if valor is None else json.dumps(valor, ensure_ascii=False)


def _filas(resultados: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convierte los resultados del lote en las filas de ``documentos`` y de ``campos``. El duplicado no entra: su contenido ya está."""
    documentos, campos = [], []
    for r in resultados:
        if r["estado"] == "duplicado":
            continue
        valores, segundos, fases = r.get("campos", {}), r.get("segundos", {}), r.get("fases", {})
        documentos.append({
            "archivo": r["archivo"], "tipo": r.get("tipo", ""), "formato": r.get("formato", ""), "sha256": r.get("sha256", ""), "estado": r["estado"],
            "motivo": r.get("motivo", ""), "paginas_ocr": r.get("paginas_ocr", 0), "caracteres": r.get("caracteres", 0),
            "campos_llenos": sum(valor is not None for valor in valores.values()), "campos_vacios": sum(valor is None for valor in valores.values()),
            "seg_control": segundos.get("control", 0.0), "seg_ingesta": segundos.get("ingesta", 0.0), "seg_ocr": segundos.get("ocr", 0.0), "seg_pln": segundos.get("pln", 0.0)})
        for campo, valor in valores.items():
            etapa = next((nombre for nombre in ("ingesta", "ocr", "pln") if fases.get(nombre, {}).get(campo) is not None), None)
            campos.append({"archivo": r["archivo"], "tipo": r.get("tipo", ""), "campo": campo, "valor": None if valor is None else str(valor),
                           "etapa": etapa, "revisar": valor is None, "tras_ingesta": _json(fases.get("ingesta", {}).get(campo)),
                           "tras_ocr": _json(fases.get("ocr", {}).get(campo)), "tras_pln": _json(fases.get("pln", {}).get(campo))})
    return pd.DataFrame(documentos), pd.DataFrame(campos)


def contar_filas(ruta_db: str | Path) -> dict[str, int]:
    """Cuántas filas tiene cada tabla de la base (0 si la tabla todavía no existe)."""
    con = duckdb.connect(str(ruta_db), read_only=True)
    try:
        existentes = {fila[0] for fila in con.execute("SHOW TABLES").fetchall()}
        return {tabla: con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0] if tabla in existentes else 0 for tabla in TABLAS}
    finally:
        con.close()


def guardar_resultados(ruta_db: str | Path, resultados: list[dict[str, Any]]) -> dict[str, int]:
    """Guarda los resultados de un lote en las tablas ``documentos`` y ``campos`` de la base.

    Args:
        ruta_db: archivo de DuckDB (el mismo que usa el registro del lote).
        resultados: ``Resumen.resultados`` de ``ejecutar_lote``; una lista vacía no cambia nada.

    Returns:
        Las filas de cada tabla después de guardar (``documentos``, ``campos``, ``registro`` y ``corridas``).
    """
    Path(ruta_db).parent.mkdir(parents=True, exist_ok=True)
    documentos, campos = _filas(resultados)
    con = duckdb.connect(str(ruta_db))
    try:
        con.execute(TABLA_DOCUMENTOS)
        con.execute(TABLA_CAMPOS)
        if len(documentos):
            con.register("documentos_df", documentos)
            con.execute("INSERT OR REPLACE INTO documentos SELECT * FROM documentos_df")
            con.unregister("documentos_df")
        if len(campos):
            con.register("campos_df", campos)
            con.execute("INSERT OR REPLACE INTO campos SELECT * FROM campos_df")
            con.unregister("campos_df")
    finally:
        con.close()
    return contar_filas(ruta_db)


def exportar_parquet(ruta_db: str | Path, carpeta: str | Path) -> dict[str, int]:
    """Exporta cada tabla de la base a un archivo Parquet con ``COPY … TO`` (DuckDB lo escribe sin otro paquete).

    Returns:
        Las filas que quedaron en cada Parquet, contadas al leerlo de nuevo.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta_db), read_only=True)
    filas = {}
    try:
        existentes = {fila[0] for fila in con.execute("SHOW TABLES").fetchall()}
        for tabla in TABLAS:
            if tabla not in existentes:
                continue
            destino = (carpeta / f"{tabla}.parquet").as_posix()
            con.execute(f"COPY (SELECT * FROM {tabla} ORDER BY {ORDEN[tabla]}) TO '{destino}' (FORMAT parquet)")
            filas[tabla] = con.execute(f"SELECT count(*) FROM read_parquet('{destino}')").fetchone()[0]
    finally:
        con.close()
    return filas


def leer_tabla(origen: str | Path, tabla: str) -> pd.DataFrame:
    """Lee una tabla desde la base de DuckDB o desde una carpeta de Parquet; devuelve una tabla vacía si no existe."""
    origen = Path(origen)
    if origen.is_dir():
        archivo = origen / f"{tabla}.parquet"
        return duckdb.sql(f"SELECT * FROM read_parquet('{archivo.as_posix()}')").df() if archivo.is_file() else pd.DataFrame()
    con = duckdb.connect(str(origen), read_only=True)
    try:
        existentes = {fila[0] for fila in con.execute("SHOW TABLES").fetchall()}
        return con.execute(f"SELECT * FROM {tabla} ORDER BY {ORDEN[tabla]}").df() if tabla in existentes else pd.DataFrame()
    finally:
        con.close()
