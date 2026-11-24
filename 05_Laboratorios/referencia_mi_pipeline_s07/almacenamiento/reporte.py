"""El reporte del lote en una página HTML: qué se procesó, cuánto tardó, qué quedó apartado y qué debe revisar una persona.

Se arma con ``DataFrame.to_html`` dentro de una plantilla de texto: sin otros paquetes ni conexión a internet. Lee de la base
de DuckDB o de la carpeta de Parquet, así que quien no hizo la corrida también puede generar el reporte.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .guardar import leer_tabla

FASES = ("ingesta", "ocr", "pln")
PLANTILLA = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}}h1{{font-size:22px}}h2{{font-size:17px;margin-top:26px}}
table{{border-collapse:collapse;margin:8px 0}}th,td{{border:1px solid #bbb;padding:4px 10px;text-align:left;font-size:14px}}th{{background:#eee}}
p.nota{{color:#555;font-size:13px}}</style></head><body>
<h1>{titulo}</h1><p class="nota">Generado el {fecha}. Documentos ficticios de práctica.</p>
{secciones}
</body></html>
"""


def tabla_exactitud(campos: pd.DataFrame, correctos: dict[str, dict[str, Any]],
                    es_correcto: Callable[[Any, Any], bool]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mide los campos después de cada etapa contra la respuesta correcta: en total (por fase) y por tipo.

    Args:
        campos: la tabla ``campos`` (de la base o del Parquet), con el valor de cada campo después de cada etapa.
        correctos: respuesta correcta de cada documento, por nombre de archivo sin extensión.
        es_correcto: función que dice si un valor extraído coincide con el correcto.

    Returns:
        ``por_fase`` (fase, correctos, esperados y exactitud) y ``por_tipo`` (una fila por tipo, con correctos/esperados por fase).
    """
    filas = []
    for fila in campos.to_dict("records"):
        correcto = correctos.get(Path(fila["archivo"]).stem)
        if correcto is None or fila["campo"] not in correcto:
            continue
        medida = {"tipo": fila["tipo"]}
        for fase in FASES:
            texto = fila[f"tras_{fase}"]
            medida[fase] = es_correcto(None if texto is None or pd.isna(texto) else json.loads(texto), correcto[fila["campo"]])
        filas.append(medida)
    medidas = pd.DataFrame(filas, columns=["tipo", *FASES])
    esperados = len(medidas)
    por_fase = pd.DataFrame([{"fase": fase, "correctos": int(medidas[fase].sum()), "esperados": esperados,
                              "exactitud": round(float(medidas[fase].sum()) / max(esperados, 1), 3)} for fase in FASES])
    por_tipo = pd.DataFrame([{"tipo": tipo, **{fase: f"{int(grupo[fase].sum())}/{len(grupo)}" for fase in FASES}}
                             for tipo, grupo in medidas.groupby("tipo", sort=True)], columns=["tipo", *FASES])
    return por_fase, por_tipo


def _seccion(titulo: str, tabla: pd.DataFrame, nota: str = "") -> str:
    """Una sección del reporte: título, nota y tabla (o «Ninguno» si la tabla está vacía)."""
    cuerpo = tabla.to_html(index=False, border=0, na_rep="—", escape=True) if len(tabla) else "<p>Ninguno.</p>"
    return f"<h2>{html.escape(titulo)}</h2>" + (f'<p class="nota">{html.escape(nota)}</p>' if nota else "") + cuerpo


def tablas_del_reporte(origen: str | Path) -> dict[str, pd.DataFrame]:
    """Las tablas que muestra el reporte, calculadas desde la base de DuckDB o desde la carpeta de Parquet."""
    registro, documentos = leer_tabla(origen, "registro"), leer_tabla(origen, "documentos")
    campos, corridas = leer_tabla(origen, "campos"), leer_tabla(origen, "corridas")
    totales = registro.groupby("estado").size().rename("archivos").reset_index() if len(registro) else pd.DataFrame()
    etapas = pd.DataFrame()
    if len(documentos):
        segundos = {etapa: float(documentos[f"seg_{etapa}"].sum()) for etapa in ("control", "ingesta", "ocr", "pln")}
        total = sum(segundos.values()) or 1.0
        etapas = pd.DataFrame([{"etapa": etapa, "segundos": round(valor, 1), "porcentaje": f"{valor / total * 100:.1f} %".replace(".", ",")} for etapa, valor in segundos.items()])
    apartados = registro[registro["estado"] != "ok"][["archivo", "estado", "motivo"]] if len(registro) else pd.DataFrame()
    revisar = pd.DataFrame()
    if len(campos):
        vacios = campos[campos["revisar"]]
        revisar = (vacios.groupby(["tipo", "campo"]).size().rename("documentos con el campo vacío").reset_index()
                   .sort_values(["tipo", "documentos con el campo vacío"], ascending=[True, False]))
    if len(corridas):
        corridas = corridas[["inicio", "modo", "trabajadores", "archivos", "saltados", "ok", "cuarentena", "duplicados", "errores", "segundos", "documentos_por_minuto"]]
    return {"totales": totales, "corridas": corridas, "etapas": etapas, "apartados": apartados, "revisar": revisar}


def escribir_reporte(origen: str | Path, ruta_html: str | Path, exactitud: tuple[pd.DataFrame, pd.DataFrame] | None = None,
                     titulo: str = "Reporte del lote") -> Path:
    """Escribe el reporte HTML del lote.

    Args:
        origen: la base de DuckDB o la carpeta con los Parquet (``documentos``, ``campos``, ``registro`` y ``corridas``).
        ruta_html: archivo de salida.
        exactitud: ``(por_fase, por_tipo)`` de ``tabla_exactitud``; solo existe cuando hay respuesta correcta (documentos de práctica).
        titulo: título de la página.

    Returns:
        La ruta del reporte.
    """
    tablas = tablas_del_reporte(origen)
    secciones = [
        _seccion("1. Archivos por estado", tablas["totales"], "Cada archivo recibido tiene un estado en el registro: ok, cuarentena, duplicado o error."),
        _seccion("2. Corridas", tablas["corridas"], "Una fila por corrida: «saltados» son los archivos que ya estaban procesados y no se repitieron."),
        _seccion("3. Tiempo por etapa", tablas["etapas"], "La etapa con más segundos es el cuello de botella."),
        _seccion("4. Apartados: cuarentena, duplicados y errores", tablas["apartados"], "Cada uno con su motivo; una persona decide qué hacer."),
        _seccion("5. Lista «revisar»: campos vacíos por tipo", tablas["revisar"], "Lo que el pipeline no pudo llenar queda para revisión humana."),
    ]
    if exactitud is not None:
        secciones.append(_seccion("6. Exactitud por fase", exactitud[0], "Campos correctos después de cada etapa, contra la respuesta correcta."))
        secciones.append(_seccion("7. Exactitud por tipo", exactitud[1]))
    ruta_html = Path(ruta_html)
    ruta_html.parent.mkdir(parents=True, exist_ok=True)
    ruta_html.write_text(PLANTILLA.format(titulo=html.escape(titulo), fecha=datetime.now().strftime("%d/%m/%Y %H:%M"), secciones="\n".join(secciones)),
                         encoding="utf-8")
    return ruta_html
