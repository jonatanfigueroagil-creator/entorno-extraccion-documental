# -*- coding: utf-8 -*-
"""verificar_entorno.py — comprueba que la máquina virtual del participante está lista para el curso.

Uso (PowerShell, con el entorno del curso activo):
    python 03_verificar_entorno.py            informe legible
    python 03_verificar_entorno.py --json     informe en JSON en pantalla
    python 03_verificar_entorno.py --salida informe_entorno.json
                                              guarda el informe JSON en ese archivo (UTF-8; crea la carpeta si falta).
                                              Se usa en lugar de ">" de PowerShell, que guarda en otra codificación.

Niveles:  OK = listo · AVISO = el curso funciona pero más lento o con respaldo · ERROR = requiere corrección.
Código de salida: 0 si no hay errores, 1 si los hay.

Pensado para la máquina virtual del curso (Windows). No usa colores, así que se lee igual en cualquier consola.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata as md
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ES_WINDOWS = os.name == "nt"

LIBRERIAS = [  # (módulo, paquete, versión fijada o None)
    ("pypdf", "pypdf", "6.19.0"), ("pymupdf", "pymupdf", "1.28.2"), ("pdfplumber", "pdfplumber", "0.11.10"),
    ("docx", "python-docx", "1.2.0"), ("bs4", "beautifulsoup4", "4.15.0"), ("tabula", "tabula-py", "2.10.0"),
    ("camelot", "camelot-py", "2.0.0"), ("pytesseract", "pytesseract", "0.3.13"), ("PIL", "pillow", "12.3.0"),
    ("cv2", "opencv-python-headless", "4.10.0.84"), ("numpy", "numpy", "2.3.5"), ("pandas", "pandas", "3.0.6"),
    ("pyarrow", "pyarrow", "26.0.0"), ("duckdb", "duckdb", "1.5.6"), ("pydantic", "pydantic", "2.14.1"),
    ("yaml", "PyYAML", "6.0.2"), ("spacy", "spacy", "3.8.16"), ("transformers", "transformers", "5.19.0"),
    ("ollama", "ollama", "0.6.3"), ("openai", "openai", "3.31.0"), ("pytest", "pytest", "9.1.1"),
    ("paddleocr", "paddleocr", "3.7.0"),
]
MODELOS_OLLAMA = ["qwen3:14b", "qwen3:4b-instruct-2507-q4_K_M"]
CON_LLM = False  # con --con-llm, la falta de Ollama y de sus modelos es un error; por defecto es un aviso (se usa desde la sesión 5)


def nivel_llm() -> str:
    """Nivel con que se informa lo que falta de Ollama: ERROR si se pidió --con-llm, AVISO si no."""
    return "ERROR" if CON_LLM else "AVISO"
RESULTADOS: list[dict[str, str]] = []

# Ubicaciones habituales en Windows cuando el instalador no agrega el programa al PATH
UNIDAD = os.environ.get("SystemDrive", "C:") + os.sep  # unidad del sistema, normalmente C:
ARCHIVOS = Path(UNIDAD) / "Program Files"
RUTAS_WINDOWS = {
    "tesseract": [ARCHIVOS / "Tesseract-OCR" / "tesseract.exe"],
    "git": [ARCHIVOS / "Git" / "cmd" / "git.exe"],
    "ollama": [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"],
    "nvidia-smi": [ARCHIVOS / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"],
}


def registrar(nivel: str, grupo: str, nombre: str, detalle: str = "") -> None:
    """Anota el resultado de una comprobación."""
    RESULTADOS.append({"nivel": nivel, "grupo": grupo, "nombre": nombre, "detalle": detalle})


def buscar_programa(nombre: str) -> str | None:
    """Devuelve la ruta del programa (PATH o ubicaciones habituales de Windows) o None."""
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    if ES_WINDOWS:
        for candidata in RUTAS_WINDOWS.get(nombre, []):
            if candidata.is_file():
                return str(candidata)
    return None


def ejecutar(cmd: list[str], tiempo: int = 15) -> tuple[int | None, str]:
    """Ejecuta un comando y devuelve (código, salida). Código None si no pudo ejecutarse."""
    ruta = buscar_programa(cmd[0])
    if ruta is None:
        return None, "no está instalado o no está en el PATH"
    try:
        r = subprocess.run([ruta, *cmd[1:]], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=tiempo)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return None, f"no respondió en {tiempo} s"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def carpeta_curso() -> Path:
    """Raíz de las carpetas del curso: la carpeta «curso» de la unidad del sistema (C:)."""
    return Path(UNIDAD) / "curso"


def memoria_gb() -> float | None:
    """Memoria RAM total en GB, o None si no se puede leer."""
    try:
        if ES_WINDOWS:
            import ctypes

            class Estado(ctypes.Structure):
                _fields_ = [("longitud", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                            ("total_fisica", ctypes.c_ulonglong), ("libre_fisica", ctypes.c_ulonglong),
                            ("total_pagina", ctypes.c_ulonglong), ("libre_pagina", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong), ("libre_virtual", ctypes.c_ulonglong),
                            ("libre_ext", ctypes.c_ulonglong)]

            estado = Estado()
            estado.longitud = ctypes.sizeof(Estado)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))  # type: ignore[attr-defined]
            return estado.total_fisica / 2**30
        with open("/proc/meminfo", encoding="utf-8") as f:  # rama de pruebas fuera de Windows
            return int(f.readline().split()[1]) / 2**20
    except Exception:  # noqa: BLE001
        return None


def verificar_sistema() -> None:
    """Sistema operativo, Python, entorno virtual, disco y memoria."""
    g = "Sistema"
    registrar("OK", g, "Sistema operativo", f"{platform.system()} {platform.release()} ({platform.version()})")
    v = sys.version_info
    registrar("OK" if (v.major, v.minor) == (3, 12) else "AVISO", g, "Python",
              f"{v.major}.{v.minor}.{v.micro}" + ("" if (v.major, v.minor) == (3, 12) else " (se espera 3.12)"))
    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    activar = str(carpeta_curso() / "venv" / "Scripts" / "Activate.ps1")
    registrar("OK" if en_venv else "AVISO", g, "Entorno virtual",
              f"activo ({sys.prefix})" if en_venv else f"no activo: falta activar el entorno del curso ({activar})")
    raiz = UNIDAD
    try:
        libre = shutil.disk_usage(raiz).free / 2**30
        registrar("OK" if libre >= 40 else "AVISO", g, "Disco libre", f"{libre:.0f} GB (mínimo 40 GB)")
    except OSError:
        registrar("AVISO", g, "Disco libre", "no se pudo leer")
    gb = memoria_gb()
    if gb is None:
        registrar("AVISO", g, "Memoria RAM", "no se pudo leer en este sistema")
    else:
        registrar("OK" if gb >= 24 else "AVISO", g, "Memoria RAM", f"{gb:.0f} GB (se esperan 28 GB)")


def verificar_carpetas() -> None:
    """Carpetas del curso y permiso de escritura en la carpeta de trabajo."""
    g = "Carpetas del curso"
    raiz = carpeta_curso()
    for nombre, nota in (("datos", "documentos ficticios, solo lectura"), ("trabajo", "carpeta de escritura del participante"),
                         ("modelos", "modelos descargados")):
        ruta = raiz / nombre
        registrar("OK" if ruta.is_dir() else "AVISO", g, str(ruta),
                  nota if ruta.is_dir() else "no existe: el participante avisa a la coordinación (el curso puede usar respaldos)")
    trabajo = raiz / "trabajo"
    if trabajo.is_dir():
        prueba = trabajo / ".prueba_escritura.tmp"
        try:
            prueba.write_text("ok", encoding="utf-8")
            prueba.unlink()
            registrar("OK", g, "Escritura en la carpeta de trabajo", "se puede escribir")
        except OSError as e:
            registrar("ERROR", g, "Escritura en la carpeta de trabajo", f"no se puede escribir ({type(e).__name__})")


def verificar_librerias() -> None:
    """Librerías de Python con su versión fijada."""
    g = "Librerías de Python"
    for modulo, paquete, version in LIBRERIAS:
        try:
            importlib.import_module(modulo)
            instalada = md.version(paquete)
        except Exception as e:  # noqa: BLE001
            registrar("ERROR", g, paquete, f"no se pudo importar ({type(e).__name__})")
            continue
        if version and instalada != version:
            registrar("AVISO", g, paquete, f"versión {instalada} (el curso usa {version})")
        else:
            registrar("OK", g, paquete, instalada)


def verificar_programas() -> None:
    """Programas externos: Tesseract, Java, Docker, Git."""
    g = "Programas del sistema"
    cod, sal = ejecutar(["tesseract", "--list-langs"])
    if cod is None:
        registrar("ERROR", g, "Tesseract", sal)
    else:
        langs = [x.strip() for x in sal.splitlines()]
        faltan = [x for x in ("spa", "osd") if x not in langs]
        registrar("ERROR" if faltan else "OK", g, "Tesseract (idiomas)",
                  f"faltan {faltan}" if faltan else "spa y osd disponibles")
    cod, sal = ejecutar(["java", "-version"])
    registrar("OK" if cod == 0 else "ERROR", g, "Java (tabula-py)",
              sal.splitlines()[0] if cod == 0 and sal else "no instalado o no está en el PATH")
    cod, sal = ejecutar(["git", "--version"])
    registrar("OK" if cod == 0 else "AVISO", g, "Git", sal if cod == 0 else "no instalado: se necesita desde la sesión 0")
    verificar_docker()


def verificar_docker() -> None:
    """Docker: en Windows puede no estar disponible y la sesión 7 se vería como demostración."""
    g = "Programas del sistema"
    aviso_win = ("Docker Desktop requiere WSL2 o Hyper-V; en esta VM puede no estar disponible: "
                 "la sesión 7 puede verse como demostración")
    if buscar_programa("docker") is None:
        registrar("AVISO", g, "Docker", aviso_win)
        return
    cod, sal = ejecutar(["docker", "info", "--format", "{{.ServerVersion}}"], 30)
    if cod == 0 and sal:
        registrar("OK", g, "Docker", f"motor activo (versión {sal.splitlines()[0]})")
    else:
        registrar("AVISO", g, "Docker", f"instalado pero no arranca. {aviso_win}")


def verificar_gpu() -> None:
    """GPU, PyTorch, modelo de spaCy y Ollama."""
    g = "GPU y modelos"
    cod, sal = ejecutar(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    if cod != 0:
        registrar("AVISO", g, "GPU NVIDIA", "no detectada: el curso funciona en CPU (más lento) y con respaldos")
    else:
        nombre = sal.splitlines()[0]
        registrar("OK" if "T4" in nombre else "AVISO", g, "GPU NVIDIA (nombre, VRAM, controlador)",
                  nombre if "T4" in nombre else f"{nombre} (se espera una Tesla T4)")
    try:
        import torch  # noqa: WPS433
        ok = bool(torch.cuda.is_available())
        registrar("OK" if ok else "AVISO", g, "PyTorch con CUDA", "CUDA disponible" if ok else "se usa CPU")
    except Exception:  # noqa: BLE001
        registrar("AVISO", g, "PyTorch", "no instalado (necesario desde la sesión 4)")
    try:
        import spacy
        spacy.load("es_core_news_md")
        registrar("OK", g, "Modelo spaCy en español", "es_core_news_md")
    except Exception:  # noqa: BLE001
        registrar("ERROR", g, "Modelo spaCy en español", "no se pudo cargar es_core_news_md")
    verificar_ollama(g)


def verificar_ollama(g: str) -> None:
    """Servicio de Ollama, modelos descargados y modelos cargados (ollama ps)."""
    if buscar_programa("ollama") is None:
        registrar(nivel_llm(), g, "Ollama (programa)", "no instalado o no está en el PATH (se necesita desde la sesión 5)")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            nombres = [m["name"] for m in json.load(r).get("models", [])]
        faltan = [m for m in MODELOS_OLLAMA if m not in nombres]
        registrar(nivel_llm() if faltan else "OK", g, "Ollama (modelos)",
                  f"faltan {faltan}" if faltan else ", ".join(MODELOS_OLLAMA))
        cod, sal = ejecutar(["ollama", "ps"])
        if cod == 0:
            cargados = [linea.split()[0] for linea in sal.splitlines()[1:] if linea.strip()]
            registrar("OK", g, "Ollama (ollama ps)", ", ".join(cargados) if cargados else "sin modelos cargados ahora (se cargan al usarlos)")
    except Exception:  # noqa: BLE001
        registrar(nivel_llm(), g, "Ollama (servicio)", "el servicio no responde en localhost:11434 (se necesita desde la sesión 5)")


def imprimir() -> None:
    """Informe legible en consola."""
    marcas = {"OK": "[ OK  ]", "AVISO": "[AVISO]", "ERROR": "[ERROR]"}
    grupo = None
    for r in RESULTADOS:
        if r["grupo"] != grupo:
            grupo = r["grupo"]
            print(f"\n== {grupo}")
        print(f"  {marcas[r['nivel']]} {r['nombre']}: {r['detalle']}")
    n = {k: sum(1 for r in RESULTADOS if r["nivel"] == k) for k in marcas}
    print(f"\nResumen: {n['OK']} OK · {n['AVISO']} avisos · {n['ERROR']} errores")
    if n["ERROR"]:
        print("Los errores requieren corrección; el participante envía este informe a la coordinación (opción --salida).")


def configurar_consola() -> None:
    """Fuerza UTF-8 en la salida (la consola de Windows suele usar cp1252)."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    """Punto de entrada: ejecuta todas las comprobaciones y devuelve el código de salida."""
    ap = argparse.ArgumentParser(description="Verificación del entorno del curso")
    ap.add_argument("--json", action="store_true", help="informe en JSON en pantalla")
    ap.add_argument("--salida", metavar="RUTA", help="guarda el informe JSON en este archivo (UTF-8)")
    ap.add_argument("--con-llm", action="store_true", help="exige Ollama y sus modelos (desde la sesión 5)")
    a = ap.parse_args()
    global CON_LLM
    CON_LLM = a.con_llm
    configurar_consola()
    verificar_sistema()
    verificar_carpetas()
    verificar_librerias()
    verificar_programas()
    verificar_gpu()
    if a.salida:
        destino = Path(a.salida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(RESULTADOS, ensure_ascii=False, indent=1), encoding="utf-8")  # UTF-8 sin BOM
        imprimir()
        print(f"Informe JSON guardado en: {destino}")
    elif a.json:
        print(json.dumps(RESULTADOS, ensure_ascii=False, indent=1))
    else:
        imprimir()
    return 1 if any(r["nivel"] == "ERROR" for r in RESULTADOS) else 0


if __name__ == "__main__":
    sys.exit(main())
