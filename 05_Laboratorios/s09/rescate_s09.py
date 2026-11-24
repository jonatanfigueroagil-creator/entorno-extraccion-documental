"""Rescate de la sesión 9: trae a la carpeta del repositorio del equipo las carpetas de una función desde la referencia del curso.

Se ejecuta desde la raíz del repositorio del equipo (la carpeta que tiene insumos/ y mi_pipeline/):
    python C:\\curso\\trabajo\\entorno-extraccion-documental\\05_Laboratorios\\s09\\rescate_s09.py --funcion extraccion
    python ...\\rescate_s09.py --funcion extraccion --solo-probar     (no copia nada: solo corre las pruebas de la función)

Qué hace:
  1. Por cada archivo de las carpetas de la función: si falta, lo trae ([REPUESTO] faltaba); si es distinto del de la referencia,
     guarda el propio en respaldo_rescate/<fecha>/ y trae el de la referencia ([REPUESTO] distinto); si es igual, lo deja ([OK]).
     Los archivos propios que la referencia no tiene se conservan.
  2. Corre las pruebas de la función sobre una copia temporal: la referencia completa con las carpetas de la función tal como
     quedaron en el repositorio del equipo. Así cada integrante prueba su parte antes de que el líder una las demás.
La referencia es el mi_pipeline de la sesión 7 publicado en 05_Laboratorios\\referencia_mi_pipeline_s07 (y el pyproject.toml en
referencia_mi_pipeline_s07_raiz). Nunca borra trabajo propio. Códigos de salida: 0 todo en verde; 1 fallan pruebas; 2 falta la referencia.
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LABORATORIOS = AQUI.parent
IGNORAR = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints"}

# función -> (entradas dentro de mi_pipeline/, archivos junto a mi_pipeline/, archivos de esta carpeta s09 que se agregan)
FUNCIONES = {
    "integracion": (["__init__.py", "__main__.py", "pipeline.py", "orquestacion", "config"], ["pyproject.toml"], []),
    "extraccion": (["ingesta", "ocr", "extraccion", "clasificacion", "llm"], [], []),
    "calidad": (["calidad", "tests"], [], [("exactitud_equipo.py", "calidad"), ("test_exactitud_equipo.py", "tests")]),
    "documentacion": (["almacenamiento", "monitoreo"], [], []),
}
# las pruebas de cada función (las corre --solo-probar y después de reponer)
PRUEBAS = {
    "integracion": ["test_cli.py", "test_config.py", "test_etapas.py", "test_lote.py", "test_registro.py", "test_trabajo.py",
                    "test_arranque.py", "test_secretos.py", "test_rueda.py"],
    "extraccion": ["test_leer_documento.py", "test_preprocesar.py", "test_renderizar.py", "test_tablas.py", "test_zonas.py",
                   "test_texto.py", "test_reglas.py", "test_montos.py", "test_lote_real.py", "test_hibrido.py", "test_motivo.py",
                   "test_esquemas.py", "test_prompts.py", "test_trozos.py", "test_cliente_llm.py", "test_extraer.py"],
    "calidad": ["test_f1.py", "test_metricas.py", "test_iou.py", "test_puntuar.py", "test_alucinaciones.py", "test_regresion.py", "test_exactitud_equipo.py"],
    "documentacion": ["test_guardar.py", "test_reporte.py", "test_registro_enmascarado.py", "test_tablero.py", "test_silenciosos.py"],
}
NOMBRES = {"integracion": "integración", "extraccion": "extracción", "calidad": "calidad", "documentacion": "documentación"}


def consola() -> None:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - consola sin reconfigure
            pass


def archivos(base: Path) -> list[str]:
    """Archivos de una carpeta (rutas relativas con /), sin cachés ni respaldos."""
    if base.is_file():
        return [""]
    if not base.is_dir():
        return []
    salida = []
    for f in base.rglob("*"):
        partes = f.relative_to(base).parts
        if f.is_file() and f.suffix != ".pyc" and not any(p in IGNORAR or p.startswith("_respaldo_") for p in partes):
            salida.append(f.relative_to(base).as_posix())
    return sorted(salida)


def normalizar(ruta: Path) -> bytes:
    """Contenido comparable: los textos sin diferencias de fin de línea ni espacios al final."""
    datos = ruta.read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos
    return "\n".join(x.rstrip() for x in texto.replace("\r\n", "\n").split("\n")).strip("\n").encode("utf-8")


def pares(funcion: str, referencia: Path, destino: Path) -> list[tuple[Path, Path, str]]:
    """(origen, destino, nombre a mostrar) de todo lo que la función trae."""
    dentro, junto, extras = FUNCIONES[funcion]
    lista = []
    for entrada in dentro:
        origen = referencia / entrada
        for rel in archivos(origen):
            o = origen / rel if rel else origen
            d = destino / "mi_pipeline" / entrada / rel if rel else destino / "mi_pipeline" / entrada
            lista.append((o, d, f"mi_pipeline/{entrada}" + (f"/{rel}" if rel else "")))
    raiz = referencia.parent / (referencia.name + "_raiz")
    for nombre in junto:
        lista.append((raiz / nombre, destino / nombre, nombre))
    for nombre, carpeta in extras:
        lista.append((AQUI / nombre, destino / "mi_pipeline" / carpeta / nombre, f"mi_pipeline/{carpeta}/{nombre}"))
    return lista


def reponer(funcion: str, referencia: Path, destino: Path) -> tuple[list[str], int]:
    """Trae lo que falta o es distinto, con respaldo de lo propio. Devuelve (repuestos, iguales)."""
    respaldo = destino / "respaldo_rescate" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    repuestos, iguales = [], 0
    for origen, final, nombre in pares(funcion, referencia, destino):
        if not origen.is_file():
            print(f"[AVISO] La referencia no trae {nombre}: se avisa al docente.")
            continue
        if final.is_file() and normalizar(final) == normalizar(origen):
            iguales += 1
            continue
        motivo = "distinto" if final.is_file() else "faltaba"
        if final.is_file():
            copia = respaldo / final.relative_to(destino)
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final, copia)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, final)
        repuestos.append(nombre)
        print(f"[REPUESTO] {nombre} ({motivo})")
    if respaldo.is_dir():
        print(f"Respaldo de lo propio: {respaldo.relative_to(destino)}")
    return repuestos, iguales


def probar(funcion: str, referencia: Path, destino: Path, python: str) -> tuple[bool, str]:
    """Corre las pruebas de la función: referencia completa + las carpetas de la función como están en el repositorio del equipo."""
    dentro, junto, _ = FUNCIONES[funcion]
    with tempfile.TemporaryDirectory(prefix="rescate_s09_") as tmp:
        base = Path(tmp)
        paquete = base / "mi_pipeline"
        shutil.copytree(referencia, paquete, ignore=shutil.ignore_patterns(*IGNORAR, "_respaldo_*"))
        raiz = referencia.parent / (referencia.name + "_raiz")
        if (raiz / "pyproject.toml").is_file():
            shutil.copy2(raiz / "pyproject.toml", base / "pyproject.toml")
        for extra, carpeta in FUNCIONES["calidad"][2]:
            shutil.copy2(AQUI / extra, paquete / carpeta / extra)
        for entrada in dentro:
            propio = destino / "mi_pipeline" / entrada
            if propio.is_dir():
                shutil.rmtree(paquete / entrada, ignore_errors=True)
                shutil.copytree(propio, paquete / entrada, ignore=shutil.ignore_patterns(*IGNORAR, "_respaldo_*"))
            elif propio.is_file():
                shutil.copy2(propio, paquete / entrada)
        for nombre in junto:   # el pyproject.toml se prueba como está en el repositorio del equipo: si falta, falta también aquí
            if (destino / nombre).is_file():
                shutil.copy2(destino / nombre, base / nombre)
            else:
                (base / nombre).unlink(missing_ok=True)
        pruebas = [f"mi_pipeline/tests/{p}" for p in PRUEBAS[funcion] if (paquete / "tests" / p).is_file()]
        if not pruebas:
            return False, "no hay pruebas de la función en la carpeta tests"
        entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        entorno.pop("PYTHONPATH", None)
        try:
            corrida = subprocess.run([python, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", f"--basetemp={base / 'temporal'}", *pruebas],
                                     cwd=base, capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno, timeout=1500)
        except subprocess.TimeoutExpired:
            return False, "las pruebas no terminaron en 25 minutos"
    lineas = [x for x in corrida.stdout.strip().splitlines() if x.strip()]
    resumen = lineas[-1] if lineas else corrida.stderr.strip()[-300:]
    if corrida.returncode != 0:
        fallas = [x for x in lineas if x.startswith(("FAILED", "ERROR"))][:8]
        return False, "\n".join([*fallas, resumen])
    return True, resumen


def main(argumentos: list[str] | None = None) -> int:
    consola()
    analizador = argparse.ArgumentParser(description="Rescate de la sesión 9: trae las carpetas de una función desde la referencia del curso.")
    analizador.add_argument("--funcion", required=True, choices=sorted(FUNCIONES), help="la función del integrante")
    analizador.add_argument("--solo-probar", action="store_true", help="no copia nada: solo corre las pruebas de la función")
    analizador.add_argument("--sin-probar", action="store_true", help="repone sin correr las pruebas")
    analizador.add_argument("--destino", default=".", help="raíz del repositorio del equipo (por omisión, la carpeta actual)")
    analizador.add_argument("--referencia", default=str(LABORATORIOS / "referencia_mi_pipeline_s07"), help="mi_pipeline de referencia")
    analizador.add_argument("--python", default=sys.executable, help="Python con el que se corren las pruebas")
    opciones = analizador.parse_args(argumentos)
    destino, referencia = Path(opciones.destino).resolve(), Path(opciones.referencia).resolve()
    nombre = NOMBRES[opciones.funcion]
    if not (referencia / "__init__.py").is_file():
        print(f"[ERROR] No está la referencia del curso en {referencia}: se repite 07_preparar_sesion.ps1 -Sesion 9 o se avisa al docente.")
        return 2
    if not (destino / ".git").exists():
        print(f"[AVISO] {destino} no parece la raíz de un repositorio (no tiene .git): se revisa que el comando empiece con cd a la carpeta del equipo.")
    if not opciones.solo_probar:
        print(f"== Rescate de {nombre}: {', '.join(FUNCIONES[opciones.funcion][0] + FUNCIONES[opciones.funcion][1])}")
        repuestos, iguales = reponer(opciones.funcion, referencia, destino)
        if repuestos:
            print(f"[REPUESTO] {len(repuestos)} " + ("archivo traído" if len(repuestos) == 1 else "archivos traídos") + f" de la referencia; {iguales} ya eran iguales.")
        else:
            print(f"[OK] Las carpetas de {nombre} ya eran iguales a la referencia ({iguales} archivos).")
    if opciones.sin_probar:
        return 0
    faltan = [e for e in FUNCIONES[opciones.funcion][0] if not (destino / "mi_pipeline" / e).exists()]
    if faltan:
        print(f"[FALTA] En mi_pipeline faltan: {', '.join(faltan)}. Se traen con Copy-Item o con este comando sin --solo-probar.")
        return 1
    print(f"== Pruebas de {nombre} (sobre una copia temporal con la referencia del curso)")
    bien, resumen = probar(opciones.funcion, referencia, destino, opciones.python)
    print(resumen)
    if bien:
        print(f"[OK] Pruebas de {nombre} en verde.")
        return 0
    print(f"[FALLA] Fallan pruebas de {nombre}: se repite el comando sin --solo-probar (trae la versión de referencia, con respaldo de lo propio).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
