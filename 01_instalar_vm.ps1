# 01_instalar_vm.ps1: prepara desde cero una VM Windows del curso (sin credenciales ni IP).
# Uso (PowerShell como administrador, desde la carpeta clonada):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\01_instalar_vm.ps1
#   Opciones: -SinGpu (omite PyTorch GPU) -ConOllama (instala Ollama y el modelo, desde la sesion 5) -Modelo qwen3:4b-instruct-2507-q4_K_M -SinModelo
# Se puede repetir: lo que ya esta instalado se omite. Registro en C:\curso\trabajo\instalacion.log.
# Requiere salida a Internet (python.org, github.com, pypi.org, ollama.com).
[CmdletBinding()]
param(
    [string]$Requirements = "",
    [string]$Zip = "",
    [string]$Modelo = "qwen3:4b-instruct-2507-q4_K_M",
    [switch]$SinModelo,
    [switch]$ConOllama,
    [switch]$SinGpu
)
$ErrorActionPreference = "Continue"
$Raiz = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
if (-not $Requirements) { $Requirements = Join-Path $Raiz "02_requirements.txt" }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Curso = "C:\curso"
$Tmp = "$env:TEMP\instalacion"
$Log = "$Curso\trabajo\instalacion.log"
$Resumen = @()

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
    if (& $yaEsta) { Anotar "OK" $nombre "instalado" } else { Anotar "ERROR" $nombre "no quedó disponible; revisar el registro" }
}

$tieneWinget = Existe "winget"

# 1. Python 3.12
Instalar "Python 3.12" { (Test-Path "$env:ProgramFiles\Python312\python.exe") -or (Existe "py" -and ((& py -3.12 --version 2>&1) -match "3\.12")) } {
    $exe = "$Tmp\python-3.12.8-amd64.exe"
    if (Descargar "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" $exe) {
        Start-Process $exe -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1" -Wait
    }
}

# 2. Git
Instalar "Git" { Existe "git" } {
    if ($tieneWinget) { winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements }
    else {
        $exe = "$Tmp\Git-2.47.1-64-bit.exe"
        if (Descargar "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe" $exe) { Start-Process $exe -ArgumentList "/VERYSILENT /NORESTART" -Wait }
    }
}

# 3. Java (para tabula-py)
Instalar "Java 17" { Existe "java" } {
    if ($tieneWinget) { winget install --id EclipseAdoptium.Temurin.17.JRE -e --silent --accept-package-agreements --accept-source-agreements }
    else {
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

# 6. Entorno virtual y librerías
$py = if (Test-Path "$env:ProgramFiles\Python312\python.exe") { "$env:ProgramFiles\Python312\python.exe" } else { "py" }
$venvPy = "$Curso\venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Anotar "INFO" "venv" "creando"
    if ($py -eq "py") { & py -3.12 -m venv "$Curso\venv" } else { & $py -m venv "$Curso\venv" }
}
if (Test-Path $venvPy) {
    if (Test-Path $Requirements) {
        Anotar "INFO" "pip" "instalando $Requirements (puede tardar varios minutos)"
        & $venvPy -m pip install --upgrade pip 2>&1 | Out-Null
        & $venvPy -m pip install -r $Requirements 2>&1 | Tee-Object -FilePath "$Curso\trabajo\pip_requirements.log" | ForEach-Object { if ($_ -match "^(Collecting|Installing collected|Successfully|ERROR)") { Write-Host "  pip: $_" } }
        if ($LASTEXITCODE -eq 0) { Anotar "OK" "librerías del curso" "" } else { Anotar "ERROR" "librerías del curso" "ver pip_requirements.log" }
    } else { Anotar "ERROR" "requirements" "no existe $Requirements" }
    & $venvPy -m pip install "https://github.com/explosion/spacy-models/releases/download/es_core_news_md-3.8.0/es_core_news_md-3.8.0-py3-none-any.whl" 2>&1 | Select-Object -Last 1
    if (-not $SinGpu) {
        Anotar "INFO" "torch GPU" "instalando (cu126)"
        & $venvPy -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu126 2>&1 | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) { Anotar "ERROR" "torch GPU" "falló; revisar versión y salida a Internet" }
    }
} else { Anotar "ERROR" "venv" "no se creó" }

# 7. Paquete del curso
if ($Zip -and (Test-Path $Zip)) {
    Expand-Archive -Path $Zip -DestinationPath "$Curso\paquete" -Force
    Anotar "OK" "paquete" "descomprimido en $Curso\paquete"
} else { Anotar "INFO" "paquete" "sin -Zip: copiar y descomprimir el zip a $Curso\paquete" }

# 7b. Documentos ficticios de practica
$traer = Join-Path $Raiz "06_traer_datos.ps1"
if (Test-Path $traer) { & $traer; if ($LASTEXITCODE -eq 0) { Anotar "OK" "datos de practica" "" } else { Anotar "ERROR" "datos de practica" "ver 06_traer_datos.ps1" } }

# 8. GPU y modelo
if (Existe "nvidia-smi") { Anotar "OK" "GPU" ((& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) -join "; ") }
else { Anotar "AVISO" "GPU" "nvidia-smi no está: falta el controlador NVIDIA; se necesita desde la sesión 4 (pedir a soporte la extensión de GPU de Azure)" }
if ($ConOllama -and -not $SinModelo -and (Existe "ollama")) {
    Anotar "INFO" "modelo" "descargando $Modelo"
    & ollama pull $Modelo 2>&1 | Select-Object -Last 1
    if ($LASTEXITCODE -eq 0) { Anotar "OK" "modelo" $Modelo } else { Anotar "ERROR" "modelo" "ollama pull falló" }
}

Write-Host "`n===== RESUMEN ====="
$Resumen | Where-Object { $_ -notmatch "^\[INFO\]" } | ForEach-Object { Write-Host $_ }
Write-Host "Registro: $Log"
Write-Host "Siguiente paso: $venvPy $(Join-Path $Raiz '03_verificar_entorno.py')"
