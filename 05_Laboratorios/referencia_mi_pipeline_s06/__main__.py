"""Línea de comandos del pipeline: un comando con su configuración reemplaza al cuaderno.

Uso (desde la carpeta que contiene el paquete):
    python -m mi_pipeline --entrada carpeta_con_archivos [--config pipeline.yaml] [--modo procesos] [--trabajadores 4] [--salida carpeta]

Lee y valida el YAML, procesa el lote, guarda en DuckDB, exporta a Parquet y escribe el reporte HTML.
"""
from __future__ import annotations

import argparse
import sys

from .almacenamiento.guardar import exportar_parquet, guardar_resultados
from .almacenamiento.reporte import escribir_reporte
from .orquestacion.config import ErrorConfiguracion, cargar_config
from .orquestacion.lote import ejecutar_lote


def main(argumentos: list[str] | None = None) -> int:
    """Punto de entrada: devuelve 0 si el lote terminó, 2 si la configuración o la carpeta de entrada no son válidas."""
    analizador = argparse.ArgumentParser(prog=f"python -m {__package__}", description="Procesa una carpeta de documentos de punta a punta.")
    analizador.add_argument("--entrada", required=True, help="carpeta con los archivos recibidos")
    analizador.add_argument("--config", default=None, help="archivo YAML de configuración (por defecto, el del paquete)")
    analizador.add_argument("--modo", choices=["secuencial", "procesos"], default=None, help="reemplaza a orquestacion.modo del YAML")
    analizador.add_argument("--trabajadores", type=int, default=None, help="reemplaza a orquestacion.trabajadores del YAML")
    analizador.add_argument("--salida", default=None, help="carpeta para la base, los Parquet, el reporte y la cuarentena")
    opciones = analizador.parse_args(argumentos)

    try:
        cfg = cargar_config(opciones.config)
        cambios = {clave: valor for clave, valor in (("modo", opciones.modo), ("trabajadores", opciones.trabajadores)) if valor is not None}
        cfg = cfg.con(**cambios) if cambios else cfg
    except (ErrorConfiguracion, ValueError, OSError) as error:
        print(f"Configuración no válida: {error}", file=sys.stderr)
        return 2
    if opciones.salida:
        cfg = cfg.en_carpeta(opciones.salida)

    try:
        resumen = ejecutar_lote(opciones.entrada, cfg, avisar=print)
    except (FileNotFoundError, NotADirectoryError) as error:
        print(f"No se pudo leer la carpeta de entrada: {error}", file=sys.stderr)
        return 2
    filas = guardar_resultados(cfg.almacenamiento.duckdb, resumen.resultados)
    exportar_parquet(cfg.almacenamiento.duckdb, cfg.almacenamiento.parquet)
    reporte = escribir_reporte(cfg.almacenamiento.duckdb, cfg.almacenamiento.reporte)
    print(f"Estados: {resumen.ok} ok | {resumen.cuarentena} en cuarentena | {resumen.duplicados} duplicados | {resumen.errores} con error | {resumen.saltados} saltados")
    print(f"Base: {filas['documentos']} documentos, {filas['campos']} campos y {filas['registro']} filas en el registro")
    print(f"Reporte: {reporte}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
