"""Exactitud del equipo (sesión 9): compara la corrida del lote con las respuestas correctas de ``insumos/respuestas``.

Se ejecuta desde la raíz del repositorio del equipo, en dos momentos (paso 4 de la sesión):
    líder (rama s09-resultados), después de la corrida del lote, escribe las 20 salidas JSON:
        python -m mi_pipeline --entrada insumos/documentos --salida resultados
        python -m mi_pipeline.calidad.exactitud_equipo --salida resultados --solo-json
    calidad (rama s09-exactitud), con resultados/ ya unido a main, mide contra las respuestas correctas:
        python -m mi_pipeline.calidad.exactitud_equipo --salida resultados --respuestas insumos/respuestas

Lee la corrida de ``resultados/resultados.duckdb`` (o ``resultados/parquet``) si está en la máquina; si no (la base no se sube a
GitHub), de las salidas ``resultados/json/<ID>.json`` que subió el líder. Escribe en la misma carpeta:
    json/<ID>.json            un archivo por documento: tipo, estado, campos y si va a revisión humana
    exactitud_por_campo.csv   por tipo y campo: esperados, correctos, vacíos y exactitud (no con --solo-json)
    revision_humana.csv       documentos que ve una persona: con campos vacíos o que no terminaron bien (no con --solo-json)

La medida es la estricta del golden set (``calidad/regresion.py``): el número como número, la fecha AAAA-MM-DD y el texto sin
importar tildes ni mayúsculas; un campo vacío es correcto solo si la respuesta correcta también es vacía.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from ..almacenamiento.guardar import leer_tabla
from .regresion import NO_SE_MIDEN, es_correcto

ETAPAS = ("tras_pln", "tras_ocr", "tras_ingesta")   # el valor después de la última etapa que lo dejó


def valor_final(fila: dict[str, Any]) -> Any:
    """El valor de un campo con su tipo (número, fecha o texto): el de la última etapa que lo dejó; None si quedó vacío."""
    for etapa in ETAPAS:
        texto = fila.get(etapa)
        if isinstance(texto, str) and texto:
            return json.loads(texto)
    valor = fila.get("valor")
    return None if valor is None or valor != valor else valor   # valor != valor: un NaN de pandas es vacío


def origen_de(salida: Path) -> Path | None:
    """Dónde leer la corrida: la base de DuckDB si está; si no, la carpeta de Parquet; si no, las salidas JSON (None)."""
    base, parquet = salida / "resultados.duckdb", salida / "parquet"
    if base.is_file():
        return base
    if parquet.is_dir():
        return parquet
    if any((salida / "json").glob("*.json")):
        return None
    raise FileNotFoundError(f"No hay corrida en {salida}: se ejecuta antes python -m mi_pipeline --entrada insumos/documentos --salida {salida}")


def leer_corrida(salida: Path) -> dict[str, dict[str, Any]]:
    """Los documentos de la corrida: ``{ID: {"archivo", "tipo", "estado", "campos": {campo: valor}}}``."""
    origen = origen_de(salida)
    documentos = {}
    if origen is None:   # sin la base en esta máquina: las salidas JSON que subió el líder
        for ruta in sorted((salida / "json").glob("*.json")):
            d = json.loads(ruta.read_text(encoding="utf-8"))
            documentos[ruta.stem] = {"archivo": d.get("archivo", ruta.stem), "tipo": d.get("tipo", ""), "estado": d.get("estado", ""), "campos": d.get("campos", {})}
        return documentos
    for fila in leer_tabla(origen, "documentos").to_dict("records"):
        documentos[Path(fila["archivo"]).stem] = {"archivo": fila["archivo"], "tipo": fila.get("tipo") or "", "estado": fila.get("estado") or "", "campos": {}}
    for fila in leer_tabla(origen, "campos").to_dict("records"):
        doc = documentos.setdefault(Path(fila["archivo"]).stem, {"archivo": fila["archivo"], "tipo": fila.get("tipo") or "", "estado": "", "campos": {}})
        doc["campos"][fila["campo"]] = valor_final(fila)
    return documentos


def respuesta_de(carpeta: Path, documento: str) -> dict[str, Any] | None:
    """La respuesta correcta de un documento (``<ID>.json``), sin los campos que no se miden; None si no está."""
    ruta = carpeta / f"{documento}.json"
    if not ruta.is_file():
        return None
    campos = json.loads(ruta.read_text(encoding="utf-8"))["campos"]
    return {campo: valor for campo, valor in campos.items() if campo not in NO_SE_MIDEN and not isinstance(valor, (bool, dict, list))}


def comparar(documentos: dict[str, dict[str, Any]], respuestas: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Filas de exactitud por tipo y campo, y los documentos sin respuesta correcta (no se miden)."""
    conteo: dict[tuple[str, str], dict[str, int]] = {}
    sin_respuesta = []
    for documento, datos in sorted(documentos.items()):
        correcto = respuesta_de(respuestas, documento)
        if correcto is None:
            sin_respuesta.append(documento)
            continue
        for campo, esperado in correcto.items():
            fila = conteo.setdefault((datos["tipo"], campo), {"esperados": 0, "correctos": 0, "vacios": 0})
            valor = datos["campos"].get(campo)
            fila["esperados"] += 1
            fila["correctos"] += int(es_correcto(valor, esperado))
            fila["vacios"] += int(valor is None)
    filas = [{"tipo": tipo, "campo": campo, **n, "exactitud": round(n["correctos"] / n["esperados"], 3) if n["esperados"] else 0.0}
             for (tipo, campo), n in sorted(conteo.items())]
    return filas, sin_respuesta


def revision_humana(documentos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Documentos que ve una persona: los que no terminaron bien o dejaron algún campo vacío (el pipeline no inventa valores)."""
    filas = []
    for documento, datos in sorted(documentos.items()):
        vacios = sorted(campo for campo, valor in datos["campos"].items() if valor is None)
        if datos["estado"] != "ok" or vacios or not datos["campos"]:
            motivo = f"estado {datos['estado']}" if datos["estado"] != "ok" else ("sin campos" if not datos["campos"] else "campos vacíos")
            filas.append({"documento": documento, "tipo": datos["tipo"], "motivo": motivo, "campos_vacios": " ".join(vacios)})
    return filas


def escribir_csv(ruta: Path, filas: list[dict[str, Any]], columnas: list[str]) -> Path:
    """Escribe una tabla CSV (UTF-8 con BOM: Excel la abre con tildes)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(filas)
    return ruta


def escribir_json(carpeta: Path, documentos: dict[str, dict[str, Any]], revisar: set[str]) -> int:
    """Un JSON por documento en ``carpeta``; devuelve cuántos escribió."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for documento, datos in sorted(documentos.items()):
        salida = {"doc_id": documento, **datos, "revision_humana": documento in revisar}
        (carpeta / f"{documento}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return len(documentos)


def exportar(salida: str | Path) -> int:
    """Solo las salidas JSON (un archivo por documento), sin medir: lo que sube el líder después de la corrida."""
    salida = Path(salida)
    documentos = leer_corrida(salida)
    if not documentos:
        raise ValueError(f"La corrida de {salida} no tiene documentos.")
    return escribir_json(salida / "json", documentos, {f["documento"] for f in revision_humana(documentos)})


def medir(salida: str | Path, respuestas: str | Path) -> dict[str, Any]:
    """Escribe los JSON, la exactitud por campo y la lista de revisión humana; devuelve el resumen."""
    salida, respuestas = Path(salida), Path(respuestas)
    if not respuestas.is_dir():
        raise FileNotFoundError(f"No está la carpeta de respuestas {respuestas}: el líder la sube con los insumos del flujo.")
    documentos = leer_corrida(salida)
    if not documentos:
        raise ValueError(f"La corrida de {salida} no tiene documentos.")
    filas, sin_respuesta = comparar(documentos, respuestas)
    revisar = revision_humana(documentos)
    escritos = escribir_json(salida / "json", documentos, {f["documento"] for f in revisar})
    escribir_csv(salida / "exactitud_por_campo.csv", filas, ["tipo", "campo", "esperados", "correctos", "vacios", "exactitud"])
    escribir_csv(salida / "revision_humana.csv", revisar, ["documento", "tipo", "motivo", "campos_vacios"])
    esperados = sum(f["esperados"] for f in filas)
    correctos = sum(f["correctos"] for f in filas)
    return {"documentos": escritos, "esperados": esperados, "correctos": correctos,
            "exactitud": round(correctos / esperados, 3) if esperados else 0.0, "revision_humana": len(revisar), "sin_respuesta": sin_respuesta}


def main(argumentos: list[str] | None = None) -> int:
    """Línea de comandos: 0 si midió, 1 si falta la corrida o las respuestas."""
    analizador = argparse.ArgumentParser(prog="python -m mi_pipeline.calidad.exactitud_equipo", description="Exactitud por campo del lote del equipo.")
    analizador.add_argument("--salida", default="resultados", help="carpeta de la corrida (la del --salida de mi_pipeline)")
    analizador.add_argument("--respuestas", default="insumos/respuestas", help="carpeta con un <ID>.json correcto por documento")
    analizador.add_argument("--solo-json", action="store_true", help="solo escribe las salidas JSON, sin medir (paso del líder)")
    opciones = analizador.parse_args(argumentos)
    if opciones.solo_json:
        try:
            escritos = exportar(opciones.salida)
        except (FileNotFoundError, ValueError) as error:
            print(f"[ERROR] {error}", file=sys.stderr)
            return 1
        print(f"Salidas JSON: {escritos} documentos en {Path(opciones.salida) / 'json'}")
        return 0
    try:
        resumen = medir(opciones.salida, opciones.respuestas)
    except (FileNotFoundError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    salida = Path(opciones.salida)
    print(f"Documentos: {resumen['documentos']} | JSON en {salida / 'json'}")
    print(f"Exactitud: {str(resumen['exactitud']).replace('.', ',')} ({resumen['correctos']} de {resumen['esperados']} campos correctos)")
    print(f"Revisión humana: {resumen['revision_humana']} documentos (lista en {salida / 'revision_humana.csv'})")
    print(f"Exactitud por campo: {salida / 'exactitud_por_campo.csv'}")
    if resumen["sin_respuesta"]:
        print(f"[AVISO] Sin respuesta correcta (no se miden): {', '.join(resumen['sin_respuesta'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
