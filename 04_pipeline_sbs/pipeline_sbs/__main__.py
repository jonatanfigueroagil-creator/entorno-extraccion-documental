"""Línea de comandos del pipeline: un comando con su configuración reemplaza al cuaderno.

Uso (desde la carpeta que contiene el paquete):
    python -m mi_pipeline --entrada carpeta_con_archivos [--config pipeline.yaml] [--modo procesos] [--trabajadores 4] [--salida carpeta]
    python -m mi_pipeline --version

Lee y valida el YAML, revisa el arranque (S07), procesa el lote con su constancia en el registro, guarda en DuckDB, exporta a
Parquet, escribe el reporte HTML y muestra el tablero con sus alertas.
Códigos de salida: 0 el lote terminó; 2 la configuración no es válida; 3 el arranque se detuvo (falta algo para trabajar).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .almacenamiento.guardar import exportar_parquet, guardar_resultados
from .almacenamiento.reporte import escribir_reporte
from .config.secretos import es_administrador, verificar_arranque
from .monitoreo.metricas import alertas, calcular_metricas, tablero, umbrales_de
from .monitoreo.registro import abrir_registro, cerrar_registro, ejecutar_registrado, version_git
from .orquestacion.config import ErrorConfiguracion, cargar_config


def anotar_y_detener(ruta: Path | None, evento: str, codigo: int, **datos: object) -> int:
    """Deja el evento de un arranque detenido en el registro (y en la consola) y devuelve el código de salida."""
    try:
        registro = abrir_registro(ruta, consola=True)
    except OSError:
        registro = abrir_registro(None)
    registro.error(evento, extra={"evento": evento, "version": version_git(), **datos})
    cerrar_registro(registro)
    return codigo


def main(argumentos: list[str] | None = None) -> int:
    """Punto de entrada: devuelve 0 si el lote terminó, 2 si la configuración no es válida y 3 si el arranque se detuvo."""
    analizador = argparse.ArgumentParser(prog=f"python -m {__package__}", description="Procesa una carpeta de documentos de punta a punta.")
    analizador.add_argument("--version", action="version", version=f"{__package__} {__version__} ({version_git()})")
    analizador.add_argument("--entrada", required=True, help="carpeta con los archivos recibidos (solo se lee)")
    analizador.add_argument("--config", default=None, help="archivo YAML de configuración (por defecto, el del paquete)")
    analizador.add_argument("--modo", choices=["secuencial", "procesos"], default=None, help="reemplaza a orquestacion.modo del YAML")
    analizador.add_argument("--trabajadores", type=int, default=None, help="reemplaza a orquestacion.trabajadores del YAML")
    analizador.add_argument("--salida", default=None, help="carpeta para la base, los Parquet, el reporte, el registro y la cuarentena")
    analizador.add_argument("--eventos-en-consola", action="store_true", help="además del archivo, cada evento del registro sale por la consola")
    opciones = analizador.parse_args(argumentos)

    try:
        cfg = cargar_config(opciones.config)
        cambios = {clave: valor for clave, valor in (("modo", opciones.modo), ("trabajadores", opciones.trabajadores)) if valor is not None}
        cfg = cfg.con(**cambios) if cambios else cfg
    except (ErrorConfiguracion, ValueError, OSError) as error:
        print(f"Configuración no válida: {error}", file=sys.stderr)
        return anotar_y_detener(None, "configuracion_invalida", 2, error=str(error).replace("\n", " | "))
    if opciones.salida:
        cfg = cfg.en_carpeta(opciones.salida)
    salida = Path(cfg.almacenamiento.duckdb).parent
    ruta_registro = salida / str((getattr(cfg, "monitoreo", None) or {}).get("registro", "registro.jsonl"))

    problemas = verificar_arranque(cfg, opciones.entrada, salida)
    if problemas:
        for problema in problemas:
            print(f"Arranque detenido: {problema}", file=sys.stderr)
        destino = ruta_registro if salida.is_dir() else None
        return anotar_y_detener(destino, "arranque_fallido", 3, problemas=problemas)
    if es_administrador():
        print("Aviso: el pipeline corre como administrador y no lo necesita; se recomienda la cuenta del participante.")

    resumen = ejecutar_registrado(opciones.entrada, cfg, ruta_registro, avisar=print, consola=opciones.eventos_en_consola)
    filas = guardar_resultados(cfg.almacenamiento.duckdb, resumen.resultados)
    exportar_parquet(cfg.almacenamiento.duckdb, cfg.almacenamiento.parquet)
    reporte = escribir_reporte(cfg.almacenamiento.duckdb, cfg.almacenamiento.reporte)
    print(f"Estados: {resumen.ok} ok | {resumen.cuarentena} en cuarentena | {resumen.duplicados} duplicados | {resumen.errores} con error | {resumen.saltados} saltados")
    print(f"Base: {filas['documentos']} documentos, {filas['campos']} campos y {filas['registro']} filas en el registro")
    print(f"Reporte: {reporte}")
    print(f"Registro: {ruta_registro}")
    metricas = calcular_metricas(ruta_registro, resumen.corrida_id)
    print(tablero(metricas, alertas(metricas, umbrales_de(cfg))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
