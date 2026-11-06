# 01_instalar_vm.ps1: prepara desde cero una VM Windows del curso (sin credenciales ni IP). No necesita Git ni Python previos.
#
# ARRANQUE SIN GIT (PowerShell como administrador; pegar las cuatro lineas):
#   [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
#   New-Item -ItemType Directory -Force C:\curso\trabajo | Out-Null
#   Invoke-WebRequest "https://raw.githubusercontent.com/jonatanfigueroagil-creator/entorno-extraccion-documental/sesion-04/01_instalar_vm.ps1" -OutFile C:\curso\trabajo\01_instalar_vm.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\curso\trabajo\01_instalar_vm.ps1 -Rama sesion-04
#
# Que hace: instala Git, Python 3.12, Java 17 y Tesseract (spa y osd); crea C:\curso\{datos,trabajo,modelos,venv,paquete};
# crea el entorno virtual con PyTorch, las librerias del curso, el modelo de spaCy y los modelos de Hugging Face (sesion 4);
# clona el repositorio del curso en C:\curso\trabajo\entorno-extraccion-documental; deja los datos de practica en C:\curso\datos
# y ejecuta el verificador. Si 02_requirements.txt, 03_verificar_entorno.py o 06_traer_datos.ps1 no estan junto a este
# script, los descarga de la misma rama (-Rama).
#
# Opciones: -Rama sesion-04 (rama del repositorio) -Sesion 4 (hasta que sesion verifica) -Curso <carpeta> (por omision C:\curso)
#           -SoloEntorno (no instala programas del sistema ni pide administrador; para pruebas) -SinClon (no clona el repositorio)
#           -SinModelosHF (no descarga los modelos de Hugging Face) -CacheHF <carpeta con hub\> (copia los modelos en lugar de descargarlos)
#           -SinGpu o -IndiceTorch cpu (PyTorch de CPU de PyPI) -Zip <zip del paquete> -Modelo qwen3:4b-instruct-2507-q4_K_M -SinModelo
# Es idempotente: lo que ya esta instalado se omite. Registro en <Curso>\trabajo\instalacion.log.
#           -ConOllama (instala Ollama y el modelo, desde la sesion 5)
# Requiere salida a Internet (python.org, github.com, pypi.org, download.pytorch.org, huggingface.co, ollama.com).
[CmdletBinding()]
param(
    [string]$Requirements = "",
    [string]$Curso = "C:\curso",
    [string]$Rama = "sesion-04",
    [string]$Repositorio = "https://github.com/jonatanfigueroagil-creator/entorno-extraccion-documental",
    [string]$Zip = "",
    [string]$Modelo = "qwen3:4b-instruct-2507-q4_K_M",
    [switch]$SinModelo,
    [switch]$ConOllama,
    [switch]$SinGpu,
    [switch]$SoloEntorno,
    [switch]$SinClon,
    [switch]$SinModelosHF,
    [string]$CacheHF = "",
    [string]$IndiceTorch = "",
    [int]$Sesion = 4
)
$ErrorActionPreference = "Continue"
$Raiz = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
if (-not $Requirements) { $Requirements = Join-Path $Raiz "02_requirements.txt" }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"   # sin barra de progreso: Invoke-WebRequest es mucho mas lento con ella en PowerShell 5.1
$Tmp = "$env:TEMP\instalacion"
$Log = "$Curso\trabajo\instalacion.log"
$Resumen = @()
$RawBase = ($Repositorio -replace "^https://github.com/", "https://raw.githubusercontent.com/") + "/$Rama"
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $SoloEntorno -and -not $esAdmin) {
    Write-Host "[ERROR] Este instalador instala programas del sistema: abra PowerShell con 'Ejecutar como administrador' y vuelva a ejecutarlo."
    exit 1
}

foreach ($c in @("datos", "trabajo", "modelos", "venv", "paquete")) { New-Item -ItemType Directory -Force "$Curso\$c" | Out-Null }
New-Item -ItemType Directory -Force $Tmp | Out-Null

function Anotar([string]$nivel, [string]$nombre, [string]$detalle = "") {
    $linea = "[{0}] {1} {2}" -f $nivel, $nombre, $detalle
    Write-Host $linea
    Add-Content -Path $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $linea)
    $script:Resumen += $linea
}

function Existe([string]$cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function ActualizarPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

function Descargar([string]$url, [string]$destino) {
    if (Test-Path $destino) { return $true }
    try { Invoke-WebRequest -Uri $url -OutFile $destino -UseBasicParsing; return $true }
    catch { Anotar "ERROR" "descarga" "$url : $($_.Exception.Message)"; return $false }
}

function Instalar([string]$nombre, [scriptblock]$yaEsta, [scriptblock]$accion) {
    if (& $yaEsta) { Anotar "OK" $nombre "ya instalado"; return }
    Anotar "INFO" $nombre "instalando..."
    try { & $accion } catch { Anotar "ERROR" $nombre $_.Exception.Message }
    ActualizarPath
    if (& $yaEsta) { Anotar "OK" $nombre "instalado" } else { Anotar "ERROR" $nombre "no quedó disponible; si el programa quedó instalado, cierre esta consola, abra una NUEVA como administrador y repita el instalador" }
}

$tieneWinget = Existe "winget"

# 0. Archivos del repositorio que el instalador necesita: se usan los que estan junto al script o se descargan de la misma rama
function ObtenerArchivo([string]$nombre, [string]$actual) {
    if ($actual -and (Test-Path $actual)) { return $actual }
    $destino = "$Curso\trabajo\$nombre"
    if (-not (Test-Path $destino)) {
        Anotar "INFO" $nombre "descargando de la rama $Rama"
        try { Invoke-WebRequest -Uri "$RawBase/$nombre" -OutFile $destino -UseBasicParsing -ErrorAction Stop } catch { Remove-Item $destino -ErrorAction SilentlyContinue }
    }
    if (Test-Path $destino) { return $destino }
    Anotar "ERROR" $nombre "no esta junto al script y no se pudo descargar de $RawBase"
    return $null
}
$Raiz0 = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
if (-not $Requirements -or -not (Test-Path $Requirements)) { $Requirements = Join-Path $Raiz0 "02_requirements.txt" }
$Requirements = ObtenerArchivo "02_requirements.txt" $Requirements
$Verificador = ObtenerArchivo "03_verificar_entorno.py" (Join-Path $Raiz0 "03_verificar_entorno.py")

if (-not $SoloEntorno) {
# 0b. Rutas largas de Windows (algunos paquetes de Python tienen rutas de mas de 260 caracteres)
try { New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force | Out-Null; Anotar "OK" "rutas largas" "habilitadas" } catch { Anotar "AVISO" "rutas largas" $_.Exception.Message }

# 1. Python 3.12
Instalar "Python 3.12" { (Test-Path "$env:ProgramFiles\Python312\python.exe") -or ((Existe "py") -and ((& py -3.12 --version 2>&1) -match "3\.12")) } {
    $exe = "$Tmp\python-3.12.8-amd64.exe"
    if (Descargar "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" $exe) {
        Start-Process $exe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1" -Wait
    }
}

# 2. Git
Instalar "Git" { (Existe "git") -or (Test-Path "$env:ProgramFiles\Git\cmd\git.exe") } {
    if ($tieneWinget) { winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements }
    if (-not (Existe "git") -and -not (Test-Path "$env:ProgramFiles\Git\cmd\git.exe")) {
        $exe = "$Tmp\Git-2.47.1-64-bit.exe"
        if (Descargar "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe" $exe) { Start-Process $exe -ArgumentList "/VERYSILENT /NORESTART" -Wait }
    }
}

# 3. Java (para tabula-py)
Instalar "Java 17" { (Existe "java") -or (@(Get-ChildItem "$env:ProgramFiles\Eclipse Adoptium\*\bin\java.exe" -ErrorAction SilentlyContinue).Count -gt 0) } {
    if ($tieneWinget) { winget install --id EclipseAdoptium.Temurin.17.JRE -e --silent --accept-package-agreements --accept-source-agreements }
    if (-not (Existe "java") -and @(Get-ChildItem "$env:ProgramFiles\Eclipse Adoptium\*\bin\java.exe" -ErrorAction SilentlyContinue).Count -eq 0) {
        $msi = "$Tmp\temurin17-jre.msi"
        if (Descargar "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jre_x64_windows_hotspot_17.0.13_11.msi" $msi) {
            Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qn ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJavaHome" -Wait
        }
    }
}

# 4. Tesseract con idiomas spa y osd
$tess = "$env:ProgramFiles\Tesseract-OCR"
Instalar "Tesseract OCR" { Test-Path "$tess\tesseract.exe" } {
    $exe = "$Tmp\tesseract-setup.exe"
    if (Descargar "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe" $exe) {
        Start-Process $exe -ArgumentList "/S" -Wait
    }
}
if (Test-Path "$tess\tessdata") {
    foreach ($idioma in @("spa", "osd")) {
        if (-not (Test-Path "$tess\tessdata\$idioma.traineddata")) {
            Descargar "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$idioma.traineddata" "$tess\tessdata\$idioma.traineddata" | Out-Null
        }
    }
    if ($env:Path -notlike "*Tesseract-OCR*") {
        [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "Machine") + ";$tess", "Machine")
        ActualizarPath
    }
}

# 5. Ollama
if ($ConOllama) {
Instalar "Ollama" { (Existe "ollama") -or (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe") } {
    $exe = "$Tmp\OllamaSetup.exe"
    if (Descargar "https://ollama.com/download/OllamaSetup.exe" $exe) { Start-Process $exe -ArgumentList "/SILENT" -Wait }
}
} else { Anotar "INFO" "Ollama" "omitido: se instala desde la sesion 5 con -ConOllama" }
} else { Anotar "INFO" "programas del sistema" "omitidos por -SoloEntorno (Python, Git, Java y Tesseract deben estar instalados)" }

# 6. Entorno virtual y librerías
$py = $null
foreach ($candidata in @("$env:ProgramFiles\Python312\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
    if (-not $py -and (Test-Path $candidata)) { $py = $candidata }
}
if (-not $py -and (Existe "py") -and ((& py -3.12 --version 2>&1) -match "3\.12")) { $py = "py" }
$venvPy = "$Curso\venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    if (-not $py) { Anotar "ERROR" "venv" "no hay Python 3.12: ejecutar este script como administrador, sin -SoloEntorno" }
    else {
        Anotar "INFO" "venv" "creando $Curso\venv"
        if ($py -eq "py") { & py -3.12 -m venv "$Curso\venv" } else { & $py -m venv "$Curso\venv" }
    }
}
if (Test-Path $venvPy) {
    & $venvPy -m pip install --upgrade pip 2>&1 | Out-Null
    # PyTorch primero (indice propio): GPU con CUDA 13.2 y, si falla, la rueda de CPU de PyPI (se usa desde la sesion 4)
    if ($Sesion -lt 4) {
        Anotar "INFO" "torch" "se instala desde la sesion 4 (repetir este instalador con -Sesion 4)"
    } elseif ($SinGpu -or $IndiceTorch -eq "cpu") {
        Anotar "INFO" "torch" "instalando la version de CPU (PyPI)"
        & $venvPy -m pip install torch==2.15.0 2>&1 | Select-Object -Last 1
    } else {
        $indice = if ($IndiceTorch) { $IndiceTorch } else { "https://download.pytorch.org/whl/cu132" }
        Anotar "INFO" "torch GPU" "instalando desde $indice (unos 2 GB)"
        & $venvPy -m pip install torch==2.15.0 --index-url $indice 2>&1 | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) {
            Anotar "AVISO" "torch GPU" "fallo el indice de GPU; se instala la version de CPU (PyPI)"
            & $venvPy -m pip install torch==2.15.0 2>&1 | Select-Object -Last 1
        }
    }
    if ($Sesion -ge 4) { if ($LASTEXITCODE -eq 0) { Anotar "OK" "torch" "2.15.0" } else { Anotar "ERROR" "torch" "fallo; revisar versión y salida a Internet" } }
    if ($Requirements -and (Test-Path $Requirements)) {
        Anotar "INFO" "pip" "instalando $Requirements (puede tardar varios minutos)"
        & $venvPy -m pip install -r $Requirements 2>&1 | Tee-Object -FilePath "$Curso\trabajo\pip_requirements.log" | ForEach-Object { if ($_ -match "^(Collecting|Installing collected|Successfully|ERROR)") { Write-Host "  pip: $_" } }
        if ($LASTEXITCODE -eq 0) { Anotar "OK" "librerías del curso" "" } else { Anotar "ERROR" "librerías del curso" "ver pip_requirements.log" }
        & $venvPy -m pip check 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Anotar "OK" "pip check" "sin conflictos de versiones" } else { Anotar "AVISO" "pip check" "hay conflictos de versiones; revisar con pip check" }
    } else { Anotar "ERROR" "requirements" "no existe 02_requirements.txt" }
    & $venvPy -m pip install "https://github.com/explosion/spacy-models/releases/download/es_core_news_md-3.8.0/es_core_news_md-3.8.0-py3-none-any.whl" 2>&1 | Select-Object -Last 1
    if ($LASTEXITCODE -eq 0) { Anotar "OK" "modelo spaCy es_core_news_md" "3.8.0" } else { Anotar "ERROR" "modelo spaCy es_core_news_md" "fallo la descarga desde github.com" }

    # Modelos de Hugging Face (sesion 4): se guardan en <Curso>\modelos\hf y HF_HOME queda definida para el usuario
    $hf = "$Curso\modelos\hf"
    New-Item -ItemType Directory -Force $hf | Out-Null
    if ($Curso -eq "C:\curso") {   # solo en la VM del curso: una prueba con otra carpeta no toca las variables del usuario
        [Environment]::SetEnvironmentVariable("HF_HOME", $hf, "User")
        [Environment]::SetEnvironmentVariable("HF_HUB_DISABLE_SYMLINKS_WARNING", "1", "User")
    }
    $env:HF_HOME = $hf
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
    Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
    Anotar "OK" "HF_HOME" "$hf (se aplica en consolas nuevas)"
    if ($SinModelosHF -or $Sesion -lt 4) { Anotar "INFO" "modelos de Hugging Face" "no se descargan ahora (se usan desde la sesion 4; repetir este instalador con -Sesion 4)" }
    else {
        foreach ($m in @("Davlan/xlm-roberta-base-ner-hrl", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")) {
            $nombreCarpeta = "models--" + ($m -replace "/", "--")
            $carpetaModelo = "$hf\hub\$nombreCarpeta"
            if (Test-Path "$carpetaModelo\snapshots") { Anotar "OK" "modelo $m" "ya descargado"; continue }
            if ($CacheHF -and (Test-Path "$CacheHF\hub\$nombreCarpeta")) {
                Anotar "INFO" "modelo $m" "copiando desde $CacheHF"
                robocopy "$CacheHF\hub\$nombreCarpeta" $carpetaModelo /E /NFL /NDL /NJH /NJS /NP | Out-Null
                if (Test-Path "$carpetaModelo\snapshots") { Anotar "OK" "modelo $m" "copiado" } else { Anotar "ERROR" "modelo $m" "no se pudo copiar" }
                continue
            }
            Anotar "INFO" "modelo $m" "descargando de huggingface.co (unos 1,1 GB entre los dos; puede tardar varios minutos)"
            & $venvPy -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$m')" 2>&1 | Select-Object -Last 1
            if ($LASTEXITCODE -eq 0 -and (Test-Path "$carpetaModelo\snapshots")) { Anotar "OK" "modelo $m" "descargado" } else { Anotar "ERROR" "modelo $m" "fallo la descarga: revisar la salida a Internet y repetir el instalador" }
        }
    }
} else { Anotar "ERROR" "venv" "no se creó" }

# 7. Repositorio del curso (clon) y datos de practica
$clon = "$Curso\trabajo\entorno-extraccion-documental"
if (Test-Path (Join-Path $Raiz0 ".git")) { $clon = $Raiz0 }
if (-not $SinClon -and -not (Test-Path "$clon\.git")) {
    $git = if (Existe "git") { "git" } elseif (Test-Path "$env:ProgramFiles\Git\cmd\git.exe") { "$env:ProgramFiles\Git\cmd\git.exe" } else { $null }
    if ($git) {
        Anotar "INFO" "repositorio" "clonando la rama $Rama en $clon"
        & $git clone --branch $Rama --single-branch "$Repositorio.git" $clon 2>&1 | Select-Object -Last 1
        if (Test-Path "$clon\.git") { Anotar "OK" "repositorio" "clonado en $clon" } else { Anotar "ERROR" "repositorio" "git clone fallo: revisar la salida a Internet y repetir el instalador" }
    } else {
        Anotar "AVISO" "repositorio" "Git no esta disponible en esta consola: se descarga el ZIP de la rama (sin historial); cierre esta consola, abra una NUEVA y repita el instalador para clonar"
        $zipRama = "$Tmp\rama.zip"
        if (Descargar "$Repositorio/archive/refs/heads/$Rama.zip" $zipRama) {
            Expand-Archive -Path $zipRama -DestinationPath "$Tmp\rama" -Force
            Move-Item (Get-ChildItem "$Tmp\rama" | Select-Object -First 1).FullName $clon -Force
            Anotar "OK" "repositorio" "ZIP descomprimido en $clon"
        }
    }
} elseif (Test-Path "$clon\.git") { Anotar "OK" "repositorio" "ya existe $clon" }
if (Test-Path "$clon\06_traer_datos.ps1") {
    $global:LASTEXITCODE = 0
    & "$clon\06_traer_datos.ps1" -Destino "$Curso\datos"
    if ($LASTEXITCODE -eq 0) { Anotar "OK" "datos de practica" "$Curso\datos" } else { Anotar "ERROR" "datos de practica" "ver 06_traer_datos.ps1" }
}
if ($Zip -and (Test-Path $Zip)) {
    Expand-Archive -Path $Zip -DestinationPath "$Curso\paquete" -Force
    Anotar "OK" "paquete" "descomprimido en $Curso\paquete"
}

# 8. GPU y modelo
if (Existe "nvidia-smi") { Anotar "OK" "GPU" ((& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) -join "; ") }
else { Anotar "AVISO" "GPU" "nvidia-smi no está: falta el controlador NVIDIA; se necesita desde la sesión 4 (pedir a soporte la extensión de GPU de Azure)" }
if ($ConOllama -and -not $SinModelo -and (Existe "ollama")) {
    Anotar "INFO" "modelo" "descargando $Modelo"
    & ollama pull $Modelo 2>&1 | Select-Object -Last 1
    if ($LASTEXITCODE -eq 0) { Anotar "OK" "modelo" $Modelo } else { Anotar "ERROR" "modelo" "ollama pull falló" }
}

# 9. Verificacion final
$verif = if (Test-Path "$clon\03_verificar_entorno.py") { "$clon\03_verificar_entorno.py" } else { $Verificador }
if ((Test-Path $venvPy) -and $verif) {
    Write-Host "`n===== VERIFICACION DEL ENTORNO (sesiones 1 a $Sesion) ====="
    & $venvPy $verif --sesion $Sesion --curso $Curso
}

Write-Host "`n===== RESUMEN ====="
$Resumen | Where-Object { $_ -notmatch "^\[INFO\]" } | ForEach-Object { Write-Host $_ }
Write-Host "Registro: $Log"
Write-Host "`nSIGUIENTES PASOS (en una consola de PowerShell NUEVA; no hace falta administrador):"
Write-Host "  1. Si se instalaron programas del sistema, abrir la consola nueva: el PATH y HF_HOME se actualizan al abrirla."
Write-Host "  2. Verificar el entorno: $venvPy $verif --sesion $Sesion"
Write-Host "  3. Carpeta del curso: cd $clon"
Write-Host "  4. Cuaderno: $venvPy -m jupyterlab (desde $clon)"
