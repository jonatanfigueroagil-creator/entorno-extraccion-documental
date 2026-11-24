"""Métricas de una corrida (S07): el tablero de alertas tempranas del pipeline, calculado desde el libro de actas.

DuckDB lee ``registro.jsonl`` tal como está (una línea JSON por evento, con claves distintas según el evento) y calcula,
para la última corrida: documentos por minuto, % de errores por tipo, confianza media, % de revisión, caracteres por página
de los PDF digitales y % de campos nulos por tipo. Las alertas comparan esas cifras con los umbrales del YAML.
Lo que no lanza error lo delatan las métricas: un PDF cortado o un formato nuevo no se caen, pero mueven estas cifras.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

UMBRALES_POR_DEFECTO = {"umbral_errores": 0.05, "revision_linea_base": 0.20, "factor_revision": 2.0,
                        "umbral_confianza": 0.85, "minimo_caracteres_pagina": 200}
COLUMNAS = {"evento": "VARCHAR", "corrida_id": "VARCHAR", "ts": "VARCHAR", "tipo": "VARCHAR", "error": "VARCHAR", "ruta": "VARCHAR",
            "archivo": "VARCHAR", "confianza": "DOUBLE", "caracteres": "BIGINT", "paginas": "BIGINT", "paginas_ocr": "BIGINT",
            "campos": "BIGINT", "campos_nulos": "BIGINT", "segundos": "DOUBLE"}


def _por_ciento(valor: float) -> str:
    return f"{valor * 100:.1f} %".replace(".", ",")


def _dos(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def calcular_metricas(ruta_registro: str | Path, corrida_id: str | None = None) -> dict[str, Any]:
    """Lee el registro con DuckDB y devuelve las cifras de una corrida (por omisión, la última).

    Args:
        ruta_registro: archivo ``registro.jsonl``.
        corrida_id: corrida que se mide; ``None`` toma la del último evento ``corrida_inicio``.

    Returns:
        ``corrida_id``, ``version``, ``documentos``, ``procesados``, ``fallidos``, ``duplicados``, ``pct_errores``,
        ``errores_por_tipo``, ``documentos_por_minuto``, ``confianza_media``, ``confianza_p10``, ``pct_revision``,
        ``causas_revision``, ``caracteres_por_pagina`` (mediana y mínimo de los PDF digitales), ``pct_campos_nulos``
        y ``nulos_por_tipo``.
    """
    ruta = str(Path(ruta_registro)).replace("'", "''")
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE crudo AS SELECT * FROM read_json_auto('{ruta}', format='newline_delimited', union_by_name=true)")
        presentes = {fila[0] for fila in con.execute("DESCRIBE crudo").fetchall()}
        columnas = ", ".join(f"TRY_CAST({c} AS {t}) AS {c}" if c in presentes else f"CAST(NULL AS {t}) AS {c}" for c, t in COLUMNAS.items())
        con.execute(f"CREATE TABLE ev AS SELECT {columnas} FROM crudo")
        if corrida_id is None:
            fila = con.execute("SELECT corrida_id FROM ev WHERE evento = 'corrida_inicio' ORDER BY ts DESC LIMIT 1").fetchone()
            if fila is None:
                raise ValueError(f"El registro {Path(ruta_registro).name} no tiene ningún evento corrida_inicio.")
            corrida_id = fila[0]
        con.execute("CREATE TABLE d AS SELECT * FROM ev WHERE corrida_id = ? AND evento LIKE 'documento_%'", [corrida_id])
        total, procesados, fallidos, duplicados = con.execute(
            "SELECT count(*), count(*) FILTER (evento = 'documento_procesado'), count(*) FILTER (evento = 'documento_fallido'), "
            "count(*) FILTER (evento = 'documento_duplicado') FROM d").fetchone()
        segundos = con.execute("SELECT epoch(max(CAST(ts AS TIMESTAMPTZ))) - epoch(min(CAST(ts AS TIMESTAMPTZ))) FROM ev "
                               "WHERE corrida_id = ? AND evento IN ('corrida_inicio', 'corrida_fin')", [corrida_id]).fetchone()[0] or 0.0
        errores = dict(con.execute("SELECT error, count(*) FROM d WHERE evento = 'documento_fallido' GROUP BY error ORDER BY 2 DESC, 1").fetchall())
        confianza_media, confianza_p10, revisar = con.execute(
            "SELECT avg(confianza), quantile_cont(confianza, 0.1), count(*) FILTER (ruta = 'revisar') FROM d WHERE evento = 'documento_procesado'").fetchone()
        mediana, minimo = con.execute(
            "SELECT median(caracteres / greatest(coalesce(paginas, 1), 1)), min(caracteres / greatest(coalesce(paginas, 1), 1)) FROM d "
            "WHERE evento = 'documento_procesado' AND lower(archivo) LIKE '%.pdf' AND coalesce(paginas_ocr, 0) = 0").fetchone()
        campos, nulos = con.execute("SELECT sum(campos), sum(campos_nulos) FROM d WHERE evento = 'documento_procesado'").fetchone()
        por_tipo = {t: round(n / c, 3) for t, c, n in con.execute(
            "SELECT tipo, sum(campos), sum(campos_nulos) FROM d WHERE evento = 'documento_procesado' AND campos > 0 GROUP BY tipo ORDER BY tipo").fetchall()}
        version = con.execute("SELECT max(version) FROM crudo WHERE corrida_id = ? AND evento = 'corrida_inicio'",
                              [corrida_id]).fetchone()[0] if "version" in presentes else None
        causas: dict[str, int] = {}
        if "causas_revision" in presentes:
            for (lista,) in con.execute("SELECT causas_revision FROM crudo WHERE corrida_id = ? AND evento = 'documento_procesado'", [corrida_id]).fetchall():
                for causa in lista or []:
                    causas[causa] = causas.get(causa, 0) + 1
    finally:
        con.close()
    return {
        "corrida_id": corrida_id, "version": version,
        "documentos": total, "procesados": procesados, "fallidos": fallidos, "duplicados": duplicados,
        "pct_errores": round(fallidos / total, 3) if total else 0.0, "errores_por_tipo": errores,
        "documentos_por_minuto": round(total / segundos * 60, 1) if segundos else None,
        "confianza_media": round(confianza_media, 3) if confianza_media is not None else None,
        "confianza_p10": round(confianza_p10, 3) if confianza_p10 is not None else None,
        "pct_revision": round(revisar / procesados, 3) if procesados else 0.0, "causas_revision": causas,
        "caracteres_por_pagina": {"mediana": round(mediana) if mediana is not None else None, "minimo": round(minimo) if minimo is not None else None},
        "pct_campos_nulos": round(nulos / campos, 3) if campos else 0.0, "nulos_por_tipo": por_tipo,
    }


def umbrales_de(cfg: Any) -> dict[str, float]:
    """Umbrales de la sección ``monitoreo`` del YAML. La confianza mínima es ``calidad.umbral_score``, salvo que el flujo fije la suya
    en ``monitoreo.umbral_confianza`` (calibrada con su línea base)."""
    monitoreo = dict(getattr(cfg, "monitoreo", None) or {})
    calidad = getattr(cfg, "calidad", None) or {}
    umbrales = {"umbral_confianza": float(calidad["umbral_score"])} if "umbral_score" in calidad else {}
    umbrales.update({clave: float(monitoreo[clave]) for clave in UMBRALES_POR_DEFECTO if clave in monitoreo})
    return {**UMBRALES_POR_DEFECTO, **umbrales}


def alertas(metricas: dict[str, Any], umbrales: dict[str, float]) -> list[str]:
    """Las cifras que cruzaron su umbral, una frase por alerta. Lista vacía: el tablero está en verde."""
    u = {**UMBRALES_POR_DEFECTO, **umbrales}
    salida = []
    if metricas["pct_errores"] > u["umbral_errores"]:
        salida.append(f"Errores: {_por_ciento(metricas['pct_errores'])} de los documentos falló (umbral {_por_ciento(u['umbral_errores'])}).")
    tope = u["factor_revision"] * u["revision_linea_base"]
    if metricas["pct_revision"] > tope:
        salida.append(f"Revisión: {_por_ciento(metricas['pct_revision'])} va a revisión humana (más de {u['factor_revision']:g} veces la línea base de "
                      f"{_por_ciento(u['revision_linea_base'])}).")
    if metricas["confianza_media"] is not None and metricas["confianza_media"] < u["umbral_confianza"]:
        salida.append(f"Confianza: la media es {_dos(metricas['confianza_media'])} (umbral {_dos(u['umbral_confianza'])}).")
    minimo = metricas["caracteres_por_pagina"]["minimo"]
    if minimo is not None and minimo < u["minimo_caracteres_pagina"]:
        salida.append(f"Texto: un PDF digital tiene {minimo} caracteres por página (mínimo {u['minimo_caracteres_pagina']:g}): puede estar truncado.")
    return salida


def tablero(metricas: dict[str, Any], avisos: list[str]) -> str:
    """El tablero en texto: las cuatro cifras principales y, debajo, las alertas (o «sin alertas»)."""
    caracteres = metricas["caracteres_por_pagina"]
    confianza = "sin dato" if metricas["confianza_media"] is None else _dos(metricas["confianza_media"])
    lineas = [
        f"Tablero de la corrida {metricas['corrida_id']} (versión {metricas['version']})",
        f"  Documentos: {metricas['documentos']} | procesados {metricas['procesados']} | fallidos {metricas['fallidos']} | "
        f"duplicados {metricas['duplicados']} | {str(metricas['documentos_por_minuto']).replace('.', ',')} por minuto",
        f"  % de errores: {_por_ciento(metricas['pct_errores'])} {metricas['errores_por_tipo'] or ''}".rstrip(),
        f"  Confianza media: {confianza} | % de revisión: {_por_ciento(metricas['pct_revision'])} {metricas['causas_revision'] or ''}".rstrip(),
        f"  Caracteres por página (PDF digitales): mediana {caracteres['mediana']}, mínimo {caracteres['minimo']} | "
        f"% de campos nulos: {_por_ciento(metricas['pct_campos_nulos'])}",
    ]
    lineas += [f"  ALERTA {aviso}" for aviso in avisos] or ["  Sin alertas: todas las cifras dentro de sus umbrales."]
    return "\n".join(lineas)
