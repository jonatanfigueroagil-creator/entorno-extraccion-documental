# -*- coding: utf-8 -*-
"""verificar_entorno.py — comprueba que la máquina virtual del participante está lista para el curso.

Uso (PowerShell; se puede ejecutar desde cualquier carpeta, con ruta absoluta):
    C:\\curso\\venv\\Scripts\\python.exe C:\\curso\\trabajo\\entorno-extraccion-documental\\03_verificar_entorno.py --sesion 3
    python 03_verificar_entorno.py                informe legible hasta la última sesión publicada (la 5)
    python 03_verificar_entorno.py --sesion 3     comprueba de forma ACUMULADA lo de las sesiones 1 a 3
    python 03_verificar_entorno.py --json         informe en JSON en pantalla
    python 03_verificar_entorno.py --salida informe_entorno.json
                                                  guarda el informe JSON en ese archivo (UTF-8; crea la carpeta si falta).
    python 03_verificar_entorno.py --curso prueba\\curso   usa otra carpeta del curso (pruebas; por omisión C:\\curso)
    python 03_verificar_entorno.py --sesion 5 --con-llm   después de instalar Ollama: si falta el programa (0.15.5 o
                                                  posterior), la API local, un modelo o una variable, es un ERROR

Las librerías y sus versiones se leen de 02_requirements.txt (junto a este archivo): las secciones «# --- Sesión N» dicen
qué necesita cada sesión. Los programas, modelos y variables de entorno de cada sesión están en este archivo.

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
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ES_WINDOWS = os.name == "nt"
ULTIMA_SESION = 5          # última sesión publicada: se actualiza al publicar la siguiente
ARCHIVO_REQUIREMENTS = Path(__file__).resolve().with_name("02_requirements.txt")

# Módulo que se importa cuando no coincide con el nombre del paquete
MODULOS = {
    "python-docx": "docx", "beautifulsoup4": "bs4", "tabula-py": "tabula", "camelot-py": "camelot", "pillow": "PIL",
    "opencv-python-headless": "cv2", "opencv-contrib-python": "cv2", "pyyaml": "yaml", "scikit-learn": "sklearn",
    "protobuf": "google.protobuf", "paddlepaddle": "paddle",
}
# Paquetes que se comprueban solo por su versión (importarlos tarda mucho o duplica a otro)
SOLO_VERSION = {"opencv-contrib-python", "paddlepaddle"}

MODELOS_HF = ["Davlan/xlm-roberta-base-ner-hrl", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"]
MODELOS_OLLAMA = ["qwen3.5:4b", "qwen3.5:9b", "glm-ocr"]   # sesión 5: texto (4B y 9B) y OCR local
VERSION_MINIMA_OLLAMA = (0, 15, 5)   # glm-ocr entra en Ollama con la versión 0.15.5
API_OLLAMA = "http://127.0.0.1:11434"
CON_LLM = False  # con --con-llm, la falta de Ollama, sus modelos o sus variables es un error; por defecto es un aviso (sesión 5)
RESULTADOS: list[dict[str, str]] = []
SESION_ACTUAL = 0
CARPETA_CURSO: Path | None = None


def nivel_llm() -> str:
    """Nivel con que se informa lo que falta de Ollama: ERROR si se pidió --con-llm, AVISO si no."""
    return "ERROR" if CON_LLM else "AVISO"


# Ubicaciones habituales en Windows cuando el instalador no agrega el programa al PATH
UNIDAD = os.environ.get("SystemDrive", "C:") + os.sep  # unidad del sistema, normalmente C:
ARCHIVOS = Path(UNIDAD) / "Program Files"
RUTAS_WINDOWS = {
    "tesseract": [ARCHIVOS / "Tesseract-OCR" / "tesseract.exe"],
    "git": [ARCHIVOS / "Git" / "cmd" / "git.exe"],
    "java": [ARCHIVOS / "Eclipse Adoptium" / "jre-17" / "bin" / "java.exe"],
    "ollama": [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"],
    "nvidia-smi": [ARCHIVOS / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"],
}


def registrar(nivel: str, grupo: str, nombre: str, detalle: str = "") -> None:
    """Anota el resultado de una comprobación, con la sesión que la necesita (0 = sistema)."""
    RESULTADOS.append({"nivel": nivel, "grupo": grupo, "nombre": nombre, "detalle": detalle, "sesion": SESION_ACTUAL})


def buscar_programa(nombre: str) -> str | None:
    """Devuelve la ruta del programa (PATH o ubicaciones habituales de Windows) o None."""
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    # Variables de entorno habituales cuando el programa no está en el PATH
    if nombre == "tesseract" and os.environ.get("TESSERACT_CMD") and Path(os.environ["TESSERACT_CMD"]).is_file():
        return os.environ["TESSERACT_CMD"]
    if nombre == "java" and os.environ.get("JAVA_HOME"):
        candidata = Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if ES_WINDOWS else "java")
        if candidata.is_file():
            return str(candidata)
    if ES_WINDOWS:
        for candidata in RUTAS_WINDOWS.get(nombre, []):
            if candidata.is_file():
                return str(candidata)
        if nombre == "java":
            for base in (ARCHIVOS / "Eclipse Adoptium", ARCHIVOS / "Java"):
                for candidata in sorted(base.glob("*/bin/java.exe")) if base.is_dir() else []:
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
    """Raíz de las carpetas del curso: ``--curso``, la variable SBS_CURSO o la carpeta «curso» de la unidad del sistema (C:)."""
    if CARPETA_CURSO is not None:
        return CARPETA_CURSO
    return Path(os.environ.get("SBS_CURSO") or (UNIDAD + "curso"))


def leer_requirements() -> dict[int, list[tuple[str, str | None]]]:
    """Lee 02_requirements.txt: ``{sesión: [(paquete, versión fijada o None)]}`` según las secciones «# --- Sesión N»."""
    secciones: dict[int, list[tuple[str, str | None]]] = {}
    if not ARCHIVO_REQUIREMENTS.is_file():
        return secciones
    actual: int | None = None
    for linea in ARCHIVO_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        cabecera = re.match(r"#\s*---\s*(.*)", linea)
        if cabecera:
            n = re.match(r"Sesi[oó]n\s+(\d+)", cabecera.group(1))
            actual = int(n.group(1)) if n else None
            continue
        limpia = linea.split("#")[0].strip()
        if actual is None or not limpia:
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:==\s*([\w.+]+))?$", limpia)
        if m:
            secciones.setdefault(actual, []).append((m.group(1), m.group(2)))
    return secciones


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
    venv = carpeta_curso() / "venv"
    python_venv = venv / ("Scripts/python.exe" if ES_WINDOWS else "bin/python")
    en_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if not python_venv.is_file():
        registrar("ERROR", g, "Entorno virtual",
                  f"falta {venv}: ejecute 01_instalar_vm.ps1 como administrador (PowerShell) y vuelva a ejecutar este verificador con {python_venv}")
    elif not en_venv:
        registrar("AVISO", g, "Entorno virtual",
                  f"este verificador corre con otro Python ({sys.executable}); ejecute: {python_venv} {Path(__file__).resolve()}")
    else:
        registrar("OK", g, "Entorno virtual", f"activo ({sys.prefix})")
    try:
        libre = shutil.disk_usage(UNIDAD).free / 2**30
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


def verificar_librerias(sesion: int, requisitos: dict[int, list[tuple[str, str | None]]]) -> None:
    """Librerías de Python de la sesión con su versión fijada (lo que dice 02_requirements.txt)."""
    g = "Librerías de Python"
    if not requisitos:
        registrar("ERROR", g, "02_requirements.txt", f"no se encuentra junto al verificador ({ARCHIVO_REQUIREMENTS})")
        return
    for paquete, version in requisitos.get(sesion, []):
        modulo = MODULOS.get(paquete.lower(), paquete.replace("-", "_"))
        try:
            instalada = md.version(paquete)
            if paquete.lower() not in SOLO_VERSION:
                importlib.import_module(modulo)
        except md.PackageNotFoundError:
            registrar("ERROR", g, paquete, "no está instalado")
            continue
        except Exception as e:  # noqa: BLE001
            registrar("ERROR", g, paquete, f"instalado ({instalada}) pero no se pudo importar ({type(e).__name__})")
            continue
        if version and instalada != version:
            registrar("AVISO", g, paquete, f"versión {instalada} (el curso usa {version})")
        else:
            registrar("OK", g, paquete, instalada)


def verificar_tesseract() -> None:
    """Tesseract con los idiomas español y orientación (sesión 1, usado a fondo en la 3)."""
    g = "Programas del sistema"
    cod, sal = ejecutar(["tesseract", "--list-langs"])
    if cod is None:
        registrar("ERROR", g, "Tesseract", sal + " (ejecute 01_instalar_vm.ps1 como administrador)")
        return
    langs = [x.strip() for x in sal.splitlines()]
    faltan = [x for x in ("spa", "osd") if x not in langs]
    cod_v, ver = ejecutar(["tesseract", "--version"])
    version = ver.splitlines()[0] if cod_v == 0 and ver else "versión desconocida"
    registrar("ERROR" if faltan else "OK", g, "Tesseract (idiomas)",
              f"faltan {faltan}" if faltan else f"spa y osd disponibles ({version})")


def verificar_git() -> None:
    g = "Programas del sistema"
    cod, sal = ejecutar(["git", "--version"])
    registrar("OK" if cod == 0 else "AVISO", g, "Git", sal if cod == 0 else "no instalado: se necesita para guardar el avance (sesión 0)")


def verificar_java() -> None:
    g = "Programas del sistema"
    cod, sal = ejecutar(["java", "-version"])
    registrar("OK" if cod == 0 else "ERROR", g, "Java (tabula-py)",
              sal.splitlines()[0] if cod == 0 and sal else "no instalado o no está en el PATH (lo instala 01_instalar_vm.ps1)")


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


def carpeta_hf() -> Path:
    """Caché de Hugging Face: HF_HOME, o la carpeta de modelos del curso."""
    return Path(os.environ["HF_HOME"]) if os.environ.get("HF_HOME") else carpeta_curso() / "modelos" / "hf"


def verificar_modelos_sesion4() -> None:
    """GPU, PyTorch, modelo de spaCy, modelos de Hugging Face y variables de entorno (sesión 4)."""
    g = "GPU y modelos"
    cod, sal = ejecutar(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    if cod != 0:
        registrar("AVISO", g, "GPU NVIDIA", "no detectada: el curso funciona en CPU (más lento) y con las salidas guardadas")
    else:
        nombre = sal.splitlines()[0]
        registrar("OK" if "T4" in nombre else "AVISO", g, "GPU NVIDIA (nombre, VRAM, controlador)",
                  nombre if "T4" in nombre else f"{nombre} (se espera una Tesla T4)")
    try:
        import torch  # noqa: WPS433
        ok = bool(torch.cuda.is_available())
        arq = ", ".join(torch.cuda.get_arch_list()) if ok else ""
        registrar("OK" if ok else "AVISO", g, f"PyTorch {torch.__version__} con CUDA",
                  f"CUDA disponible (arquitecturas: {arq})" if ok else "sin CUDA: se usa la CPU y las salidas guardadas")
    except Exception:  # noqa: BLE001
        registrar("ERROR", g, "PyTorch", "no se pudo importar (lo instala 01_instalar_vm.ps1)")
    try:
        import spacy
        spacy.load("es_core_news_md")
        registrar("OK", g, "Modelo spaCy en español", f"es_core_news_md {md.version('es_core_news_md')}")
    except Exception:  # noqa: BLE001
        registrar("ERROR", g, "Modelo spaCy en español", "no se pudo cargar es_core_news_md (lo instala 01_instalar_vm.ps1)")
    hf = carpeta_hf()
    for modelo in MODELOS_HF:
        carpeta = hf / "hub" / ("models--" + modelo.replace("/", "--")) / "snapshots"
        listo = carpeta.is_dir() and any(carpeta.glob("*/config.json"))
        registrar("OK" if listo else "AVISO", g, f"Modelo de Hugging Face {modelo}",
                  str(carpeta.parent) if listo else f"no está en {hf}: 01_instalar_vm.ps1 lo descarga (sin él se usan las salidas guardadas)")
    hf_home = os.environ.get("HF_HOME")
    registrar("OK" if hf_home else "AVISO", "Variables de entorno", "HF_HOME",
              hf_home if hf_home else f"sin definir: se usa {hf} (01_instalar_vm.ps1 la define; abrir una consola nueva)")
    simb = os.environ.get("HF_HUB_DISABLE_SYMLINKS_WARNING")
    registrar("OK" if simb == "1" else "AVISO", "Variables de entorno", "HF_HUB_DISABLE_SYMLINKS_WARNING",
              "1" if simb == "1" else "sin definir: Hugging Face avisa por los enlaces simbólicos (solo es un aviso)")


def version_tupla(texto: str | None) -> tuple[int, ...] | None:
    """Primera versión «x.y.z» de un texto como tupla de enteros, o None."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", texto or "")
    return tuple(int(x) for x in m.groups()) if m else None


def api_ollama(ruta: str, tiempo: int = 5) -> dict | None:
    """Respuesta JSON de la API local de Ollama (``/api/version``, ``/api/tags``, ``/api/ps``) o None si no responde."""
    try:
        with urllib.request.urlopen(API_OLLAMA + ruta, timeout=tiempo) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def nombre_completo(modelo: str) -> str:
    """Ollama lista «glm-ocr» como «glm-ocr:latest»: se agrega la etiqueta si falta."""
    return modelo if ":" in modelo else modelo + ":latest"


def variable_usuario(nombre: str) -> tuple[str | None, str]:
    """Valor de una variable de entorno: la de esta consola o, si falta, la del usuario guardada en Windows (consolas nuevas)."""
    if os.environ.get(nombre):
        return os.environ[nombre], "esta consola"
    if ES_WINDOWS:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as clave:
                valor, _ = winreg.QueryValueEx(clave, nombre)
                if valor:
                    return str(valor), "usuario (se aplica al abrir una consola nueva)"
        except OSError:
            pass
    return None, ""


def config_servidor_ollama() -> dict[str, str]:
    """Carpeta de modelos y OLLAMA_NO_CLOUD con que arrancó el servidor, según la última línea «server config» de server.log."""
    registro = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"
    try:
        lineas = [x for x in registro.read_text(encoding="utf-8", errors="replace").splitlines() if "server config" in x]
    except OSError:
        return {}
    if not lineas:
        return {}
    datos = {}
    for clave in ("OLLAMA_MODELS", "OLLAMA_NO_CLOUD"):
        m = re.search(clave + r":(\S*)", lineas[-1])
        if m:
            datos[clave] = m.group(1).replace("\\\\", "\\").rstrip("]")
    return datos


def verificar_ollama() -> None:
    """Sesión 5: programa Ollama (versión mínima), API local, modelos, modelos cargados en GPU, variables y carpeta de modelos."""
    g = "Ollama y modelos de lenguaje"
    nivel = nivel_llm()
    cuando = "se instala en el paso 3 de la guía de la sesión 5" if not CON_LLM else "repetir la instalación de Ollama"
    minima = ".".join(str(x) for x in VERSION_MINIMA_OLLAMA)
    esperada = carpeta_curso() / "modelos" / "ollama"
    # 1. Programa y versión
    if buscar_programa("ollama") is None:
        registrar(nivel, g, "Ollama (programa)", f"no está instalado ({cuando})")
    else:
        cod, sal = ejecutar(["ollama", "--version"])
        version = version_tupla(sal) if cod is not None else None
        if version is None:
            registrar(nivel, g, "Ollama (programa)", f"instalado, pero no informa su versión: {sal[:120]}")
        elif version < VERSION_MINIMA_OLLAMA:
            registrar(nivel, g, "Ollama (programa)",
                      f"versión {'.'.join(map(str, version))}: glm-ocr exige {minima} o posterior (repetir la instalación)")
        else:
            registrar("OK", g, "Ollama (programa)", f"versión {'.'.join(map(str, version))} (mínimo {minima}) en {buscar_programa('ollama')}")
    # 2. Servicio (API local), modelos descargados y modelos cargados ahora (ollama ps)
    info = api_ollama("/api/version")
    if info is None:
        registrar(nivel, g, "Ollama (API)", f"no responde en localhost:11434: se abre «Ollama» desde Inicio ({cuando})")
    else:
        registrar("OK", g, "Ollama (API)", f"responde en localhost:11434 (servidor {info.get('version', '?')})")
        nombres = [m.get("name", "") for m in (api_ollama("/api/tags", 10) or {}).get("models", [])]
        for modelo in MODELOS_OLLAMA:
            if nombre_completo(modelo) in nombres:
                registrar("OK", g, f"Modelo {modelo}", "descargado")
            else:
                registrar(nivel, g, f"Modelo {modelo}", f"no está descargado: ollama pull {modelo} (retoma si se corta)")
        cargados = (api_ollama("/api/ps") or {}).get("models", [])
        if not cargados:
            registrar("OK", g, "Ollama (modelos en memoria)", "ninguno cargado ahora (se cargan al usarlos; ollama ps los muestra)")
        for m in cargados:
            total, vram = m.get("size", 0) or 0, m.get("size_vram", 0) or 0
            parte = round(100 * vram / total) if total else 0
            registrar("OK" if parte >= 100 else "AVISO", g, f"Modelo cargado {m.get('name', '?')}",
                      f"100 % en GPU ({vram / 2**30:.1f} GB)" if parte >= 100 else
                      f"{parte} % en GPU: el resto corre en la CPU (mucho más lento); revisar nvidia-smi o usar el modelo pequeño")
        servidor = config_servidor_ollama()
        if servidor.get("OLLAMA_MODELS") and Path(servidor["OLLAMA_MODELS"]).resolve() != esperada.resolve():
            registrar("AVISO", g, "Ollama (carpeta de modelos del servidor)",
                      f"el servidor arrancó con {servidor['OLLAMA_MODELS']} y no con {esperada}: se cierra Ollama desde su ícono "
                      "junto al reloj (Quit Ollama) y se abre de nuevo desde Inicio")
        if servidor.get("OLLAMA_NO_CLOUD", "").lower() in ("false", "0"):
            registrar("AVISO", g, "Ollama (nube)",
                      "el servidor arrancó sin OLLAMA_NO_CLOUD=1: se cierra Ollama desde su ícono junto al reloj y se abre de nuevo")
    # 3. Variables de entorno del usuario (se fijan antes de instalar Ollama)
    valor, origen = variable_usuario("OLLAMA_MODELS")
    if not valor:
        registrar(nivel, g, "Variable OLLAMA_MODELS", f"sin definir: los modelos irían al perfil del usuario y no a {esperada}")
    elif Path(valor).resolve() != esperada.resolve():
        registrar("AVISO", g, "Variable OLLAMA_MODELS", f"{valor} (el curso usa {esperada}; {origen})")
    else:
        registrar("OK", g, "Variable OLLAMA_MODELS", f"{valor} ({origen})")
    valor, origen = variable_usuario("OLLAMA_NO_CLOUD")
    registrar("OK" if valor == "1" else nivel, g, "Variable OLLAMA_NO_CLOUD",
              f"1: sin modelos en la nube ({origen})" if valor == "1" else "sin definir: debe valer 1 para que Ollama no use modelos en la nube")


def imprimir(hasta: int) -> None:
    """Informe legible en consola, con un resumen por sesión."""
    marcas = {"OK": "[ OK  ]", "AVISO": "[AVISO]", "ERROR": "[ERROR]"}
    grupo = None
    for r in RESULTADOS:
        if r["grupo"] != grupo:
            grupo = r["grupo"]
            print(f"\n== {grupo}")
        etiqueta = f" (S{r['sesion']})" if r["sesion"] else ""
        print(f"  {marcas[r['nivel']]} {r['nombre']}{etiqueta}: {r['detalle']}")
    print("\n== Por sesión (acumulado)")
    for s in range(0, hasta + 1):
        propios = [r for r in RESULTADOS if r["sesion"] == s]
        if not propios:
            continue
        errores = [r["nombre"] for r in propios if r["nivel"] == "ERROR"]
        avisos = [r["nombre"] for r in propios if r["nivel"] == "AVISO"]
        nombre = "Sistema" if s == 0 else f"Sesión {s}"
        estado = "listo" if not errores and not avisos else ""
        if errores:
            estado = "FALTA: " + ", ".join(errores)
        if avisos:
            estado += ("; " if estado else "") + "avisos: " + ", ".join(avisos)
        print(f"  {nombre}: {estado}")
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
    """Punto de entrada: ejecuta las comprobaciones acumuladas hasta la sesión pedida y devuelve el código de salida."""
    ap = argparse.ArgumentParser(description="Verificación del entorno del curso")
    ap.add_argument("--sesion", type=int, default=ULTIMA_SESION, help=f"verifica de forma acumulada las sesiones 1 a N (por omisión, la {ULTIMA_SESION})")
    ap.add_argument("--json", action="store_true", help="informe en JSON en pantalla")
    ap.add_argument("--salida", metavar="RUTA", help="guarda el informe JSON en este archivo (UTF-8)")
    ap.add_argument("--con-llm", action="store_true", help="exige Ollama y sus modelos (desde la sesión 5)")
    ap.add_argument("--curso", metavar="CARPETA", help="carpeta del curso (por omisión C:\\curso)")
    a = ap.parse_args()
    global CON_LLM, CARPETA_CURSO, SESION_ACTUAL
    CON_LLM = a.con_llm
    if a.curso:
        CARPETA_CURSO = Path(a.curso).resolve()
    hasta = max(1, min(a.sesion, 9))
    configurar_consola()
    requisitos = leer_requirements()
    SESION_ACTUAL = 0
    verificar_sistema()
    verificar_carpetas()
    for s in range(1, hasta + 1):
        SESION_ACTUAL = s
        verificar_librerias(s, requisitos)
        if s == 1:
            verificar_tesseract()
            verificar_git()
        elif s == 2:
            verificar_java()
        elif s == 4:
            verificar_modelos_sesion4()
        elif s == 5:
            verificar_ollama()
        elif s == 7:
            verificar_docker()
    if a.salida:
        destino = Path(a.salida).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(RESULTADOS, ensure_ascii=False, indent=1), encoding="utf-8")  # UTF-8 sin BOM
        imprimir(hasta)
        print(f"Informe JSON guardado en: {destino}")
    elif a.json:
        print(json.dumps(RESULTADOS, ensure_ascii=False, indent=1))
    else:
        imprimir(hasta)
    return 1 if any(r["nivel"] == "ERROR" for r in RESULTADOS) else 0


if __name__ == "__main__":
    sys.exit(main())
