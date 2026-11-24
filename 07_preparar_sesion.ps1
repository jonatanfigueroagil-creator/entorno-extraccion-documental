# 07_preparar_sesion.ps1: deja lista la maquina para una sesion del curso.
# Hace, en orden: 1) Git, 2) la copia del curso, 3) los datos propios, 4) la rama de la sesion,
# 5) el entorno (instalador y verificador), 6) la puesta al dia de mi_pipeline (desde la sesion 5) y 7) JupyterLab.
# La sesion 6 no usa modelos de lenguaje: no instala ni comprueba Ollama; trae la lista de la bandeja a mi_pipeline\config.
# La sesion 8 (proyecto final) tampoco usa modelos de lenguaje ni contenedores: repone de S03 a S06 y crea trabajo-s08 desde trabajo-s06
# (la sesion 7 se dicta despues, el 20/11/2026).
# La sesion 7 crea trabajo-s07 desde trabajo-s08 (o desde trabajo-s06 si falta), repone de S03 a S06 y tampoco usa modelos de lenguaje
# ni contenedores en la VM; con -Completar repone tambien los archivos de la sesion 7 y el pyproject.toml junto a mi_pipeline.
# La sesion 9 (clase adicional, 25/11/2026) crea trabajo-s09 desde trabajo-s07 (o desde trabajo-s08 o trabajo-s06 si faltan) y repone de
# S03 a S07 (mi_pipeline completo y el pyproject.toml junto a mi_pipeline): asi cada integrante tiene las carpetas que trae al
# repositorio del equipo. No usa modelos de lenguaje ni contenedores.
# Uso (PowerShell o terminal de JupyterLab; si falta instalar algo y la ventana no es de administrador, el archivo pide el permiso
# con la ventana de Windows y corre el instalador en otra ventana; con el entorno completo no pide nada):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\07_preparar_sesion.ps1 -Sesion 6
# Se puede repetir sin riesgo: lo que ya esta hecho se comprueba y se omite. Nunca se borra trabajo propio.
#   -SinInstalar   omite el instalador y solo ejecuta el verificador del entorno
#   -ConOllama     el instalador instala tambien Ollama y sus modelos (en la sesion 5 se instalan en vivo con la guia)
#   -Rehacer       vuelve a preguntar el nombre, el correo y el usuario de GitHub
#   -Completar     (sesion 6) plan B del participante atrasado: ademas de lo anterior, repone los archivos de la PROPIA sesion
#                  que falten o cuyas pruebas fallen, desde 05_Laboratorios\referencia_mi_pipeline_sNN, con respaldo y avisos
#                  [REPUESTO]. No abre otra ventana de JupyterLab. Sin -Completar no se toca nada de la sesion en curso.
#   -Venv, -DatosCurso   otras carpetas del entorno y de los datos (solo para pruebas; por omision C:\curso\venv y C:\curso\datos)
#   -Trabajo       carpeta donde queda la copia del curso (por omision C:\curso\trabajo)
#
# Puesta al dia (sesion 5 en adelante): si a mi_pipeline le faltan archivos de las sesiones anteriores o sus pruebas fallan,
# se respalda lo propio en mi_pipeline\_respaldo_AAAAMMDD_HHMM\, se repone solo lo que falta o falla desde la referencia
# publicada en la rama de la sesion (05_Laboratorios\referencia_mi_pipeline_sNN\), se vuelven a correr las pruebas y se
# guarda un commit. Si no existe la rama de la sesion anterior, la rama nueva parte de la rama publicada de la sesion.
[CmdletBinding()]
param(
    [int]$Sesion = 9,
    [switch]$SinInstalar,
    [switch]$ConOllama,
    [switch]$Rehacer,
    [switch]$Completar,
    [string]$Venv = "C:\curso\venv",
    [string]$DatosCurso = "C:\curso\datos",
    [string]$Repositorio = "https://github.com/jonatanfigueroagil-creator/entorno-extraccion-documental.git",
    [string]$Trabajo = "C:\curso\trabajo"
)
$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# carpeta de trabajo y cuaderno de cada sesion: numero = @{ carpeta; cuaderno de origen; cuaderno de trabajo }
$Sesiones = @{
    3 = @{ Carpeta = "s03_ocr";        Origen = "02_LAB_S03_OCR_Imagenes.ipynb";   Destino = "02_LAB_S03_OCR_Imagenes.ipynb" }
    4 = @{ Carpeta = "s04_extraccion"; Origen = "03_LAB_S04_PLN_Extraccion.ipynb"; Destino = "02_LAB_S04_PLN_Extraccion.ipynb" }
    5 = @{ Carpeta = "s05_llm";        Origen = "04_LAB_S05_LLM_Extraccion.ipynb"; Destino = "02_LAB_S05_LLM_Extraccion.ipynb"; Repone = "S03 y S04"; Commit = "Puesta al día S03-S04" }
    8 = @{ Carpeta = "s08_pf";         Origen = "06_LAB_S08_PF_Implementacion.ipynb"; Destino = "02_LAB_S08_PF_Implementacion.ipynb"; Repone = "S03 a S06"; Commit = "Puesta al día S03-S06"; Traer = @("05_Laboratorios\datos_s06\bandeja_s06.json") }
    7 = @{ Carpeta = "s07_despliegue"; Origen = "07_LAB_S07_Despliegue_Monitoreo.ipynb"; Destino = "02_LAB_S07_Despliegue_Monitoreo.ipynb"; Repone = "S03 a S06"; Commit = "Puesta al día S03-S06"; Referencia = 6; Alternativa = 6 }
    9 = @{ Carpeta = "s09_equipo";     Origen = "08_LAB_S09_Pipeline_Desde_Cero.ipynb"; Destino = "02_LAB_S09_Pipeline_Desde_Cero.ipynb"; Repone = "S03 a S07"; Commit = "Puesta al día S03-S07"; Referencia = 7; Alternativa = @(8, 6) }
    6 = @{ Carpeta = "s06_pipeline";   Origen = "05_LAB_S06_Pipelines_E2E.ipynb";  Destino = "02_LAB_S06_Pipelines_E2E.ipynb"; Repone = "S03 a S05"; Commit = "Puesta al día S03-S05"; Traer = @("05_Laboratorios\datos_s06\bandeja_s06.json") }
}
if (-not $Sesiones.ContainsKey($Sesion)) { Write-Host "[ERROR] Sesión $Sesion no disponible en este archivo." -ForegroundColor Red; exit 2 }
$Datos = $Sesiones[$Sesion]
$Anterior = if ($Sesion -eq 8) { 6 } elseif ($Sesion -eq 7) { 8 } elseif ($Sesion -eq 9) { 7 } else { $Sesion - 1 }   # orden real: S06, S08 (18/11), S07 (20/11), S09 (25/11)
$NumReferencia = if ($Datos.Referencia) { $Datos.Referencia } else { $Anterior }   # S07: la referencia es la de S06 (S08 no agrega módulos)
$Clon = Join-Path $Trabajo "entorno-extraccion-documental"
$ConPuesta = [bool]$Datos.Repone
$Total = if ($ConPuesta) { 7 } else { 6 }

function Titulo([int]$n, [string]$texto) { Write-Host ""; Write-Host "=== $n/$Total $texto" -ForegroundColor Cyan }
function Ejecutar-Git { & git @args 2>&1 | ForEach-Object { "$_" } | Write-Host }
function Pedir([string]$dato) { do { $r = (Read-Host $dato).Trim() } while (-not $r); $r }
function Rama-Existe([string]$nombre) { & git rev-parse --verify --quiet "refs/heads/$nombre" *> $null; return ($LASTEXITCODE -eq 0) }
function Remota-Existe([string]$nombre) { & git rev-parse --verify --quiet "refs/remotes/$nombre" *> $null; return ($LASTEXITCODE -eq 0) }

# ---------------------------------------------------------------- 1. Git
Titulo 1 "Git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    } else {
        $instalador = Join-Path $env:TEMP "Git-instalador.exe"
        Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe" -OutFile $instalador -UseBasicParsing
        Start-Process $instalador -ArgumentList "/VERYSILENT /NORESTART" -Wait
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host "[ERROR] Git no quedó instalado. Se cierra PowerShell, se abre otra ventana como administrador y se repite el archivo." -ForegroundColor Red; exit 1 }
Ejecutar-Git --version

# ---------------------------------------------------------------- 2. Copia del curso
Titulo 2 "Copia del curso"
New-Item -ItemType Directory -Force $Trabajo | Out-Null
if (-not (Test-Path $Clon)) {
    Set-Location $Trabajo
    Ejecutar-Git clone --branch "sesion-0$Sesion" $Repositorio
    if (-not (Test-Path $Clon)) { Write-Host "[ERROR] No se pudo descargar el curso. Se revisa la conexión a Internet y se repite el archivo." -ForegroundColor Red; exit 1 }
}
Set-Location $Clon
Ejecutar-Git status --short --branch

# ---------------------------------------------------------------- 3. Datos propios
Titulo 3 "Datos propios"
$nombre = (& git config --global user.name 2>$null)
$correo = (& git config --global user.email 2>$null)
$hayRemoto = [bool](& git remote | Select-String -SimpleMatch -Quiet mio)
if ($Rehacer -or -not $nombre -or -not $correo -or -not $hayRemoto) {
    $nombre = Pedir "Nombre y apellido"
    $correo = Pedir "Correo electrónico"
    $usuario = Pedir "Usuario de GitHub"
    Ejecutar-Git config --global user.name $nombre
    Ejecutar-Git config --global user.email $correo
    # el usuario va tambien antes de github.com: Git usa la cuenta de ese usuario aunque la maquina guarde otra
    $url = "https://${usuario}@github.com/$usuario/extraccion-documental-sbs.git"
    if ($hayRemoto) { Ejecutar-Git remote set-url mio $url } else { Ejecutar-Git remote add mio $url }
} else {
    Write-Host "Datos ya configurados: $nombre <$correo>. Para cambiarlos, se repite el archivo con -Rehacer."
    # remoto de una version anterior, sin el usuario antes de github.com: se agrega
    $actual = "$(& git remote get-url mio 2>$null)"
    if ($actual -match '^https://github\.com/([^/]+)/extraccion-documental-sbs\.git$') {
        $u = $Matches[1]
        Ejecutar-Git remote set-url mio "https://${u}@github.com/${u}/extraccion-documental-sbs.git"
    }
}
Ejecutar-Git remote -v
# comprobacion: GitHub debe encontrar el repositorio personal con esta cuenta
Ejecutar-Git ls-remote --heads mio
$faltaRepo = ($LASTEXITCODE -ne 0)
if ($faltaRepo) {
    Write-Host "[FALTA] GitHub no encuentra el repositorio personal con esta cuenta. Se crea en https://github.com/new?name=extraccion-documental-sbs&visibility=private (privado, sin README) o se revisa en el navegador que la sesión abierta sea la de esta cuenta, y se repite el archivo con -Rehacer." -ForegroundColor Yellow
} else {
    Write-Host "[OK] GitHub encuentra el repositorio personal con esta cuenta." -ForegroundColor Green
}

# ---------------------------------------------------------------- 4. Rama de la sesion
Titulo 4 "Rama trabajo-s0$Sesion"
$ramaInicial = (& git branch --show-current)
Ejecutar-Git add -A
Ejecutar-Git commit -m "Avance guardado antes de empezar la sesión"
Ejecutar-Git fetch origin
# una copia hecha con --single-branch solo trae su rama: se pide tambien la rama publicada de esta sesion
Ejecutar-Git fetch origin "+refs/heads/sesion-0${Sesion}:refs/remotes/origin/sesion-0${Sesion}"
if (-not $faltaRepo) { Ejecutar-Git fetch mio }
$sinAnterior = $false
if (-not (Rama-Existe "trabajo-s0$Anterior") -and (Remota-Existe "mio/trabajo-s0$Anterior")) { Ejecutar-Git switch -c "trabajo-s0$Anterior" --no-track "mio/trabajo-s0$Anterior" }
# S07: si no está trabajo-s08 (ni en esta máquina ni en el repositorio personal), se parte de trabajo-s06
# S09: si no está trabajo-s07, se parte de trabajo-s08 y, si tampoco está, de trabajo-s06 (en ese orden)
if ($Datos.Alternativa -and -not (Rama-Existe "trabajo-s0$Sesion") -and -not (Rama-Existe "trabajo-s0$Anterior")) {
    foreach ($alt in @($Datos.Alternativa)) {
        if (-not (Rama-Existe "trabajo-s0$alt") -and (Remota-Existe "mio/trabajo-s0$alt")) { Ejecutar-Git switch -c "trabajo-s0$alt" --no-track "mio/trabajo-s0$alt" }
        if (Rama-Existe "trabajo-s0$alt") {
            Write-Host "[AVISO] No está la rama trabajo-s0${Anterior}: trabajo-s0$Sesion parte de trabajo-s0$alt." -ForegroundColor Yellow
            $Anterior = $alt
            break
        }
    }
}
if (Rama-Existe "trabajo-s0$Sesion") { Ejecutar-Git switch "trabajo-s0$Sesion" }
elseif (Rama-Existe "trabajo-s0$Anterior") { Ejecutar-Git switch -c "trabajo-s0$Sesion" --no-track "trabajo-s0$Anterior" }
elseif ($ConPuesta) {
    $sinAnterior = $true
    Write-Host "[AVISO] No está la rama trabajo-s0$Anterior (ni en esta máquina ni en el repositorio personal): trabajo-s0$Sesion parte de la rama publicada sesion-0$Sesion y la puesta al día repone mi_pipeline completo." -ForegroundColor Yellow
    if ($ramaInicial) { Write-Host "        Lo que había en la rama $ramaInicial sigue guardado en esa rama." -ForegroundColor Yellow }
    Ejecutar-Git switch -c "trabajo-s0$Sesion" --no-track "origin/sesion-0$Sesion"
}
$rama = (& git branch --show-current)
if ($rama -ne "trabajo-s0$Sesion") { Write-Host "[ERROR] No se pudo cambiar a trabajo-s0$Sesion. Si mio/trabajo-s0$Anterior no existe, el avance de la sesión anterior no se subió a GitHub: se avisa al docente." -ForegroundColor Red; exit 1 }
Ejecutar-Git restore --source "origin/sesion-0$Sesion" -- 00_LEEME.txt 01_instalar_vm.ps1 02_requirements.txt 03_verificar_entorno.py 04_pipeline_sbs 05_Laboratorios 06_traer_datos.ps1 07_preparar_sesion.ps1
# Los archivos del curso recien traidos se guardan en un commit propio: asi la version (git describe) no sale «-dirty» por ellos.
$rutasCurso = @("00_LEEME.txt", "01_instalar_vm.ps1", "02_requirements.txt", "03_verificar_entorno.py", "04_pipeline_sbs", "05_Laboratorios", "06_traer_datos.ps1", "07_preparar_sesion.ps1")
$existentes = @($rutasCurso | Where-Object { (Test-Path (Join-Path $Clon $_)) -and (& git ls-files -- $_) })
# S09: también los archivos NUEVOS del curso (05_Laboratorios\s09, datos_s09, la referencia completa): sin ellos quedaban sin guardar
if ($existentes.Count -gt 0 -and (& git status --porcelain --untracked-files=all -- @existentes)) {
    Ejecutar-Git add -- @existentes
    Ejecutar-Git commit -m "Archivos del curso de la sesión $Sesion" -- @existentes
    Write-Host "[OK] Archivos del curso de la sesión $Sesion guardados en un commit propio." -ForegroundColor Green
}
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Clon "06_traer_datos.ps1") -Destino $DatosCurso
New-Item -ItemType Directory -Force (Join-Path $Clon $Datos.Carpeta) | Out-Null
$cuadernoOrigen = Join-Path $Clon "05_Laboratorios\$($Datos.Origen)"
$cuadernoDestino = Join-Path $Clon "$($Datos.Carpeta)\$($Datos.Destino)"
if (Test-Path $cuadernoDestino) { Write-Host "El cuaderno $($Datos.Carpeta)\$($Datos.Destino) ya existe: se conserva (no se reemplaza el trabajo propio)." }
elseif (Test-Path $cuadernoOrigen) { Copy-Item $cuadernoOrigen $cuadernoDestino }
else { Write-Host "[AVISO] Todavía no está publicado el cuaderno $($Datos.Origen): se avisa al docente." -ForegroundColor Yellow }
Write-Host "Rama actual: $rama"

# ---------------------------------------------------------------- 5. Entorno
Titulo 5 "Entorno"
if ($SinInstalar) { Write-Host "Instalador omitido (-SinInstalar)." }
else {
    $opciones = @("-Sesion", "$Sesion", "-Rama", "sesion-0$Sesion")
    if ($ConOllama) { $opciones += "-ConOllama" }
    $instalador = Join-Path $Clon "01_instalar_vm.ps1"
    $esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($esAdmin) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $instalador @opciones
    } else {
        # ventana sin administrador: si el entorno ya esta completo no se pide nada; si falta algo, el propio archivo pide el permiso
        $pyVenv = Join-Path $Venv "Scripts\python.exe"
        $completo = $false
        if (Test-Path $pyVenv) {
            & $pyVenv (Join-Path $Clon "03_verificar_entorno.py") --sesion $Sesion *> $null
            $completo = ($LASTEXITCODE -eq 0)
        }
        if ($completo) {
            Write-Host "[OK] El entorno ya está completo: no hace falta el permiso de administrador."
        } else {
            Write-Host "Falta instalar programas del entorno y esta ventana no es de administrador." -ForegroundColor Yellow
            Write-Host "Windows muestra ahora una ventana de permiso: se responde «Sí». El instalador corre en otra ventana, que se cierra sola al terminar (tarda varios minutos); esta ventana espera."
            $registro = Join-Path $env:TEMP "instalar_vm_s0$Sesion.log"
            Remove-Item $registro -ErrorAction SilentlyContinue
            $orden = "& '$instalador' $($opciones -join ' ') *>&1 | Tee-Object -FilePath '$registro'"
            try {
                Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "`"$orden`"" -ErrorAction Stop
                if (Test-Path $registro) {
                    Write-Host "Últimas líneas del instalador (la salida completa está en $registro):"
                    Get-Content $registro -Tail 15 | Write-Host
                }
            } catch {
                Write-Host "[ERROR] No se obtuvo el permiso de administrador (se respondió «No» o la cuenta no lo tiene). Se repite el archivo y se responde «Sí»; si Windows pide una contraseña que no se conoce, se avisa al docente." -ForegroundColor Red
            }
        }
    }
    # lo que el instalador agrega (Tesseract, Java y Python en el Path; HF_HOME y las variables de Ollama) no llega solo a esta ventana: se vuelve a leer
    $rutas = @(([Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path) -split ";" | Where-Object { $_ }) | Select-Object -Unique
    $env:Path = $rutas -join ";"
    foreach ($variable in "HF_HOME", "HF_HUB_DISABLE_SYMLINKS_WARNING", "OLLAMA_MODELS", "OLLAMA_NO_CLOUD") {
        $valor = [Environment]::GetEnvironmentVariable($variable, "User")
        if (-not $valor) { $valor = [Environment]::GetEnvironmentVariable($variable, "Machine") }
        if ($valor) { Set-Item "Env:$variable" $valor }
    }
}
$python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Host "[ERROR] Falta el entorno en ${Venv}: el instalador no terminó. Se repite el archivo, sin -SinInstalar, y se acepta el permiso de administrador cuando Windows lo pida." -ForegroundColor Red; exit 1 }
& $python (Join-Path $Clon "03_verificar_entorno.py") --sesion $Sesion
$codigo = $LASTEXITCODE
if ($codigo -ne 0) { Write-Host "[AVISO] El verificador informó errores (código $codigo). Se avisa al docente con la salida de arriba." -ForegroundColor Yellow }

# ---------------------------------------------------------------- 6. Puesta al dia de mi_pipeline (desde la sesion 5)
if ($ConPuesta) {
    Titulo 6 "Puesta al día de mi_pipeline ($($Datos.Repone))"
    $referencia = Join-Path $Clon "05_Laboratorios\referencia_mi_pipeline_s0$NumReferencia"
    $ayudante = Join-Path $env:TEMP "puesta_al_dia_s0$Sesion.py"
    $codigoPy = @'
"""Puesta al día de mi_pipeline: repone desde la referencia publicada solo lo que falta o falla. Nunca borra trabajo propio."""
import ast
import atexit
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

CLON, REF, ETIQUETA = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
MIO = CLON / "mi_pipeline"
IGNORAR = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints"}
for flujo in (sys.stdout, sys.stderr):
    try:
        flujo.reconfigure(encoding="utf-8")
    except Exception:
        pass


def archivos(base):
    if not base.is_dir():
        return []
    salida = []
    for f in base.rglob("*"):
        partes = f.relative_to(base).parts
        if f.is_file() and f.suffix != ".pyc" and not any(p in IGNORAR or p.startswith("_respaldo_") for p in partes):
            salida.append(f.relative_to(base).as_posix())
    return sorted(salida)


def leer(ruta):
    try:
        return ruta.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def normalizar(texto):
    return "\n".join(x.rstrip() for x in (texto or "").replace("\r\n", "\n").split("\n")).strip("\n")


def nombres(texto):
    arbol = ast.parse(texto)
    salida = set()
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            salida.add(nodo.name)
        elif isinstance(nodo, ast.Assign):
            salida.update(t.id for t in nodo.targets if isinstance(t, ast.Name))
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            salida.add(nodo.target.id)
    return salida


def claves(dato, prefijo=""):
    if not isinstance(dato, dict):
        return set()
    salida = set()
    for k, v in dato.items():
        salida.add(prefijo + str(k))
        salida |= claves(v, prefijo + str(k) + ".")
    return salida


def modulo(rel):
    partes = rel[:-3].split("/")
    if partes[-1] == "__init__":
        partes = partes[:-1]
    return ".".join(["mi_pipeline", *partes])


def dependencias(rel, texto):
    """Archivos de mi_pipeline que importa un archivo (imports absolutos y relativos)."""
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return set()
    paquete = modulo(rel).split(".") if rel.endswith("__init__.py") else modulo(rel).split(".")[:-1]
    salida = set()
    for nodo in ast.walk(arbol):
        destinos = []
        if isinstance(nodo, ast.Import):
            destinos = [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            base = paquete[: len(paquete) - nodo.level + 1] if nodo.level else []
            raiz = ".".join(base + ([nodo.module] if nodo.module else []))
            destinos = [raiz] + [raiz + "." + a.name for a in nodo.names]
        for d in destinos:
            partes = d.split(".")
            if not partes or partes[0] != "mi_pipeline":
                continue
            for i in range(1, len(partes) + 1):
                ruta = "/".join(partes[1:i])
                for candidato in ((ruta + ".py") if ruta else None, (ruta + "/__init__.py") if ruta else "__init__.py"):
                    if candidato:
                        salida.add(candidato)
    return salida


REFERENCIA = archivos(REF)
if not REFERENCIA:
    print(f"[ERROR] No está la referencia {REF}: se repite este archivo (trae la rama publicada) o se avisa al docente.")
    sys.exit(2)
TEXTO_REF = {r: leer(REF / r) for r in REFERENCIA}
PRUEBAS = [r for r in REFERENCIA if r.startswith("tests/test_") and r.endswith(".py")]
DEPS = {r: dependencias(r, TEXTO_REF[r]) & set(REFERENCIA) for r in REFERENCIA if r.endswith(".py")}
sello = datetime.datetime.now().strftime("%Y%m%d_%H%M")
RESPALDO = MIO / f"_respaldo_{sello}"
n_respaldo = 2
while RESPALDO.exists():
    RESPALDO = MIO / f"_respaldo_{sello}_{n_respaldo}"
    n_respaldo += 1
repuestos = []
HABIA_PROPIOS = bool(archivos(MIO))   # se decide antes de reponer nada: el respaldo es solo de lo que hizo el participante


def respaldar():
    if RESPALDO.exists() or not HABIA_PROPIOS:
        return
    shutil.copytree(MIO, RESPALDO, ignore=lambda d, nombres_: [n for n in nombres_ if n in IGNORAR or n.startswith("_respaldo_")])
    # pytest no recoge las pruebas del respaldo aunque se ejecute sobre toda la carpeta mi_pipeline
    (RESPALDO / "conftest.py").write_text('collect_ignore_glob = ["*"]\n', encoding="utf-8")


def reponer(rel, motivo, silencioso=False):
    respaldar()
    destino = MIO / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REF / rel, destino)
    repuestos.append(rel)
    if not silencioso:
        print(f"[REPUESTO] {rel} ({motivo})", flush=True)


def distinto(rel):
    return normalizar(leer(MIO / rel)) != normalizar(TEXTO_REF[rel])


def cierre(rel, vistos=None):
    vistos = set() if vistos is None else vistos
    for d in DEPS.get(rel, ()):
        if d not in vistos:
            vistos.add(d)
            cierre(d, vistos)
    return vistos


COPIA_REF = Path(tempfile.mkdtemp(prefix="referencia_"))   # la referencia como mi_pipeline/, para separar fallas del entorno
shutil.copytree(REF, COPIA_REF / "mi_pipeline")
atexit.register(shutil.rmtree, COPIA_REF, True)


def correr_pruebas(base=CLON, solo=None):
    """Corre las pruebas de la referencia que hay en base/mi_pipeline/tests; devuelve (pasan, total, archivos que fallan)."""
    presentes = [r for r in (solo or PRUEBAS) if (base / "mi_pipeline" / r).is_file()]
    if not presentes:
        return 0, 0, set(solo or PRUEBAS)
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "pruebas.xml"
        orden = [sys.executable, "-m", "pytest", "-q", "--color=no", "-p", "no:cacheprovider", f"--junitxml={xml}",
                 f"--basetemp={Path(tmp) / 'temporal'}", *[f"mi_pipeline/{r}" for r in presentes]]
        entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        try:
            corrida = subprocess.run(orden, cwd=base, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     env=entorno, timeout=1200)
        except subprocess.TimeoutExpired:
            return 0, 0, set(presentes)
        if not xml.is_file():
            print((corrida.stdout + corrida.stderr)[-1500:])
            return 0, 0, set(presentes)
        raiz = ET.parse(xml).getroot()
    total, fallan, pasan = 0, set(), 0
    for caso in raiz.iter("testcase"):
        total += 1
        problema = caso.find("failure") is not None or caso.find("error") is not None
        omitida = caso.find("skipped") is not None
        texto = (caso.get("classname") or "") + "." + (caso.get("name") or "")
        archivo = next((p + ".py" for p in texto.split(".") if p.startswith("test_")), None)
        if problema:
            fallan.add(f"tests/{archivo}" if archivo else "tests/?")
        elif not omitida:
            pasan += 1
    return pasan, total, fallan


def comprobar_importacion(candidatos, base=CLON):
    """Importa cada módulo en orden de dependencias; devuelve los que fallan por sí mismos (no por un módulo del que dependen)."""
    codigo = r"""
import importlib, json, sys
sys.path.insert(0, sys.argv[1])
orden, deps = json.loads(sys.argv[2]), json.loads(sys.argv[3])
fallan = {}
for rel, nombre in orden:
    try:
        importlib.import_module(nombre)
    except BaseException as e:
        fallan[rel] = type(e).__name__
propios = [r for r in fallan if not any(d in fallan for d in deps.get(r, []))]
print(json.dumps(propios))
"""
    orden, vistos = [], set()

    def visitar(rel):
        if rel in vistos:
            return
        vistos.add(rel)
        for d in sorted(DEPS.get(rel, ())):
            visitar(d)
        if not rel.startswith("tests/"):
            orden.append((rel, modulo(rel)))

    for rel in candidatos:
        visitar(rel)
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    try:
        corrida = subprocess.run([sys.executable, "-c", codigo, str(base), json.dumps(orden),
                                  json.dumps({k: sorted(v) for k, v in DEPS.items()})],
                                 cwd=base, capture_output=True, text=True, encoding="utf-8", errors="replace", env=entorno, timeout=600)
        return json.loads(corrida.stdout.strip().splitlines()[-1])
    except Exception:
        return []


resultado = None
propios = archivos(MIO)
if not any(r in propios for r in REFERENCIA):
    for rel in REFERENCIA:
        reponer(rel, "faltaba", silencioso=True)
    print(f"[REPUESTO] mi_pipeline completo de {ETIQUETA}", flush=True)
else:
    # 1. archivos que faltan
    for rel in REFERENCIA:
        if not (MIO / rel).is_file():
            reponer(rel, "faltaba")
    # 2. archivos que no se pueden leer, con errores de sintaxis o incompletos (falta una función o una clave del YAML)
    for rel in REFERENCIA:
        if rel in repuestos or not distinto(rel):
            continue
        texto = leer(MIO / rel)
        if texto is None:
            reponer(rel, "fallaba")
        elif rel.endswith(".py"):
            try:
                faltan = nombres(TEXTO_REF[rel]) - nombres(texto)
            except SyntaxError:
                reponer(rel, "fallaba")
                continue
            if faltan:
                reponer(rel, "incompleto")
        elif rel.endswith((".yaml", ".yml")):
            try:
                import yaml
                mio_yaml = yaml.safe_load(texto)
            except Exception:
                reponer(rel, "fallaba")
                continue
            if claves(yaml.safe_load(TEXTO_REF[rel])) - claves(mio_yaml):
                reponer(rel, "incompleto")
    # 3. módulos que no se pueden importar (si tampoco se importan con la referencia, falta algo en el entorno: no se repone)
    rotos = comprobar_importacion([r for r in REFERENCIA if r.endswith(".py") and not r.startswith("tests/")])
    del_entorno = set(comprobar_importacion(rotos, COPIA_REF)) if rotos else set()
    for rel in rotos:
        if rel in del_entorno:
            print(f"[AVISO] {rel} no se importa ni con la referencia del curso: falta algo en el entorno (paso 5)", flush=True)
        elif rel not in repuestos and distinto(rel):
            reponer(rel, "fallaba")
    # 4. pruebas que fallan: primero la prueba y lo que importa directamente; después todo lo que necesita.
    #    Una prueba que también falla con la referencia del curso es del entorno: no se repone nada por ella.
    for ronda in (1, 2):
        resultado = correr_pruebas()
        if not resultado[2]:
            break
        del_entorno = correr_pruebas(COPIA_REF, sorted(resultado[2]))[2]
        cambios = False
        for prueba in sorted(resultado[2]):
            if prueba not in TEXTO_REF or prueba in del_entorno:
                continue
            candidatos = {prueba} | (DEPS.get(prueba, set()) if ronda == 1 else cierre(prueba))
            for rel in sorted(candidatos):
                if rel in TEXTO_REF and (not (MIO / rel).is_file() or distinto(rel)):
                    reponer(rel, "fallaba")
                    cambios = True
        if not cambios:
            break
        resultado = None

pasan, total, fallan = resultado if resultado is not None else correr_pruebas()
if fallan:
    entorno_falla = correr_pruebas(COPIA_REF, sorted(fallan))[2]
    print(f"[ERROR] Todavía fallan {len(fallan)} archivos de pruebas ({', '.join(sorted(fallan))}): se avisa al docente con esta salida.")
    if entorno_falla:
        print(f"        Con la referencia del curso también fallan {', '.join(sorted(entorno_falla))}: el problema está en el entorno "
              "(se revisa el paso 5, «Entorno»), no en mi_pipeline.")
    sys.exit(1)
if repuestos:
    if RESPALDO.exists():
        print(f"Respaldo de lo propio: mi_pipeline\\{RESPALDO.name}")
    print(f"[OK] mi_pipeline de {ETIQUETA} puesto al día ({pasan} pruebas en verde)")
    sys.exit(10)
print(f"[OK] mi_pipeline de {ETIQUETA} completo ({pasan} pruebas)")
sys.exit(0)
'@
    [IO.File]::WriteAllText($ayudante, $codigoPy, (New-Object Text.UTF8Encoding $false))
    $env:PYTHONIOENCODING = "utf-8"
    # S09: el pyproject.toml de la sesión 7 va junto a mi_pipeline (el líder lo trae al repositorio del equipo); si falta, se repone
    # (antes de la revisión: sin él, test_rueda.py falla y la puesta al día no termina en verde)
    $pyRepuesto = $false
    if ($Sesion -eq 9) {
        $raizRef = Join-Path $Clon "05_Laboratorios\referencia_mi_pipeline_s07_raiz"
        foreach ($archivo in @(Get-ChildItem $raizRef -File -ErrorAction SilentlyContinue)) {
            $destinoRaiz = Join-Path $Clon $archivo.Name
            if (Test-Path $destinoRaiz) { Write-Host "[OK] $($archivo.Name) junto a mi_pipeline" }
            else { Copy-Item $archivo.FullName $destinoRaiz; Write-Host "[REPUESTO] $($archivo.Name) (junto a mi_pipeline)"; $pyRepuesto = $true }
        }
    }
    & $python $ayudante $Clon $referencia $Datos.Repone
    $resultado = $LASTEXITCODE
    if ($pyRepuesto -and $resultado -eq 0) { $resultado = 10 }   # S09: se guarda el pyproject.toml repuesto en el commit de la puesta al día
    # Plan B (-Completar): la misma revision, ahora con los archivos que agrega la propia sesion
    $resultadoSesion = 0
    if ($Completar) {
        $referenciaSesion = Join-Path $Clon "05_Laboratorios\referencia_mi_pipeline_s0$Sesion"
        Write-Host ""
        Write-Host "=== Completar mi_pipeline con los archivos de la sesión $Sesion (-Completar)" -ForegroundColor Cyan
        if (Test-Path $referenciaSesion) {
            if ($resultado -eq 10) { Ejecutar-Git add -A; Ejecutar-Git commit -m $Datos.Commit; $resultado = 0 }
            # S07: el pyproject.toml va junto a mi_pipeline, no dentro: se repone aparte si falta
            $raizSesion = Join-Path $Clon "05_Laboratorios\referencia_mi_pipeline_s0${Sesion}_raiz"
            if (Test-Path $raizSesion) {
                foreach ($archivo in Get-ChildItem $raizSesion -File) {
                    $destinoRaiz = Join-Path $Clon $archivo.Name
                    if (-not (Test-Path $destinoRaiz)) { Copy-Item $archivo.FullName $destinoRaiz; Write-Host "[REPUESTO] $($archivo.Name) (junto a mi_pipeline)" }
                }
            }
            & $python $ayudante $Clon $referenciaSesion "S0$Sesion"
            $resultadoSesion = $LASTEXITCODE
            if ($resultadoSesion -eq 10) {
                Ejecutar-Git add -A
                Ejecutar-Git commit -m "Completar S0$Sesion"
                Write-Host "Se guardó el commit «Completar S0$Sesion» en la rama $rama."
                $resultadoSesion = 0
            } elseif ($resultadoSesion -ne 0) {
                Write-Host "[ERROR] No se pudo completar la sesión $Sesion (código $resultadoSesion). Se avisa al docente con la salida de arriba." -ForegroundColor Red
                if ($codigo -eq 0) { $codigo = 1 }
            }
        } else {
            Write-Host "[AVISO] No está 05_Laboratorios\referencia_mi_pipeline_s0${Sesion}: esta sesión no tiene archivos para completar. Se avisa al docente." -ForegroundColor Yellow
        }
    }
    Remove-Item $ayudante -ErrorAction SilentlyContinue
    if ($resultado -eq 10) {
        Ejecutar-Git add -A
        Ejecutar-Git commit -m $Datos.Commit
        Write-Host "Se guardó el commit «$($Datos.Commit)» en la rama $rama."
    } elseif ($resultado -ne 0) {
        Write-Host "[ERROR] La puesta al día no terminó bien (código $resultado). Se avisa al docente con la salida de arriba." -ForegroundColor Red
        if ($codigo -eq 0) { $codigo = 1 }
    }
}

# Datos que la sesion trae del repositorio a mi_pipeline\config (sesion 6: la lista de la bandeja) y el paquete del curso (control de ingesta de S02)
if ($Datos.Traer) {
    $config = Join-Path $Clon "mi_pipeline\config"
    New-Item -ItemType Directory -Force $config | Out-Null
    foreach ($relativo in $Datos.Traer) {
        $origen = Join-Path $Clon $relativo
        $nombre = Split-Path $relativo -Leaf
        $destino = Join-Path $config $nombre
        if (-not (Test-Path $origen)) { Write-Host "[AVISO] Todavía no está publicado ${relativo}: se avisa al docente." -ForegroundColor Yellow }
        elseif ((Test-Path $destino) -and ((Get-FileHash $origen).Hash -eq (Get-FileHash $destino).Hash)) { Write-Host "[OK] mi_pipeline\config\$nombre" }
        else { Copy-Item $origen $destino -Force; Write-Host "[REPUESTO] mi_pipeline\config\$nombre (traído del repositorio)" }
    }
}
if ($Sesion -ge 6) {
    & $python -c "import pipeline_sbs.ingesta.cargador" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] pipeline_sbs (control de ingesta de la sesión 2) instalado en el entorno" }
    else {
        & $python -m pip install -q -e (Join-Path $Clon "04_pipeline_sbs") 2>&1 | Out-Null
        & $python -c "import pipeline_sbs.ingesta.cargador" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "[REPUESTO] pipeline_sbs instalado en el entorno desde 04_pipeline_sbs" }
        else { Write-Host "[AVISO] pipeline_sbs no quedó instalado: mi_pipeline lo toma de la carpeta 04_pipeline_sbs del repositorio." -ForegroundColor Yellow }
    }
}

# ---------------------------------------------------------------- 7. JupyterLab
Titulo $Total "JupyterLab"
if ($Completar) {
    Write-Host "Con -Completar no se abre otra ventana: se vuelve a JupyterLab y se sigue en el cuaderno $($Datos.Carpeta)\$($Datos.Destino)."
} elseif ($env:JPY_PARENT_PID) {
    Write-Host "Este archivo corre dentro de JupyterLab: ya está abierto. Se abre el cuaderno $($Datos.Carpeta)\$($Datos.Destino)."
} else {
    $orden = "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; & '$Venv\Scripts\Activate.ps1'; Set-Location '$Clon'; jupyter lab"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $orden
    Write-Host "JupyterLab se abre en otra ventana de PowerShell. Esa ventana debe quedar abierta mientras se trabaja."
}
Write-Host ""
if ($faltaRepo) { Write-Host "[FALTA] Repositorio personal: sin él, el avance no se puede subir. Se resuelve como indica el paso 3/$Total y se repite el archivo con -Rehacer." -ForegroundColor Yellow }
Write-Host "Listo: sesión $Sesion preparada en la rama $rama." -ForegroundColor Green
exit $codigo
