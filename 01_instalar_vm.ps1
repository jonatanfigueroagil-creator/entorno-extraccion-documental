# 01_instalar_vm.ps1: prepara desde cero una VM Windows del curso (sin credenciales ni IP). No necesita Git ni Python previos.
#
# ARRANQUE SIN GIT (PowerShell como administrador; pegar las cuatro lineas):
#   [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
#   New-Item -ItemType Directory -Force C:\curso\trabajo | Out-Null
#   Invoke-WebRequest "https://raw.githubusercontent.com/jonatanfigueroagil-creator/entorno-extraccion-documental/sesion-05/01_instalar_vm.ps1" -OutFile C:\curso\trabajo\01_instalar_vm.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\curso\trabajo\01_instalar_vm.ps1 -Rama sesion-05
#
# Que hace: instala Git, Python 3.12, Java 17 y Tesseract (spa y osd); crea C:\curso\{datos,trabajo,modelos,venv,paquete};
# crea el entorno virtual con PyTorch, las librerias del curso, el modelo de spaCy y los modelos de Hugging Face (sesion 4);
# clona el repositorio del curso en C:\curso\trabajo\entorno-extraccion-documental; deja los datos de practica en C:\curso\datos
# y ejecuta el verificador. Si 02_requirements.txt, 03_verificar_entorno.py o 06_traer_datos.ps1 no estan junto a este
# script, los descarga de la misma rama (-Rama).
# Con -ConOllama (desde la sesion 5) instala ademas Ollama para el usuario de la sesion de Windows, sin administrador, con
# OLLAMA_MODELS=C:\curso\modelos\ollama y OLLAMA_NO_CLOUD=1, y descarga los modelos qwen3.5:4b, glm-ocr y qwen3.5:9b.
# En clase, Ollama se instala con este instalador y -SoloOllama en una ventana normal (paso 3 de la guia de la sesion 5).
#
# Opciones: -Rama sesion-05 (rama del repositorio) -Sesion 5 (hasta que sesion verifica) -Curso <carpeta> (por omision C:\curso)
#           -SoloEntorno (no instala programas del sistema ni pide administrador; para pruebas) -SinClon (no clona el repositorio)
#           -SinModelosHF (no descarga los modelos de Hugging Face) -CacheHF <carpeta con hub\> (copia los modelos en lugar de descargarlos)
#           -SinGpu o -IndiceTorch cpu (PyTorch de CPU de PyPI) -Zip <zip del paquete>
#           -ConOllama (Ollama y sus modelos, desde la sesion 5) -SoloOllama (solo Ollama y sus modelos, sin administrador)
#           -Modelos qwen3.5:4b,glm-ocr (otros modelos de Ollama) -SinModelo (instala Ollama sin descargar modelos)
#           -InstaladorOllama <ruta a OllamaSetup.exe ya descargado> -VersionOllama v0.40.15
# Es idempotente: lo que ya esta instalado se omite. Registro en <Curso>\trabajo\instalacion.log.
# Requiere salida a Internet (python.org, github.com, pypi.org, download.pytorch.org, huggingface.co, ollama.com).
[CmdletBinding()]
param(
    [string]$Requirements = "",
    [string]$Curso = "C:\curso",
    [string]$Rama = "sesion-05",
    [string]$Repositorio = "https://github.com/jonatanfigueroagil-creator/entorno-extraccion-documental",
    [string]$Zip = "",
    [Alias("Modelo")][string[]]$Modelos = @("qwen3.5:4b", "glm-ocr", "qwen3.5:9b"),
    [switch]$SinModelo,
    [switch]$ConOllama,
    [switch]$SoloOllama,
    [string]$InstaladorOllama = "",
    [string]$VersionOllama = "v0.40.15",
    [switch]$SinGpu,
    [switch]$SoloEntorno,
    [switch]$SinClon,
    [switch]$SinModelosHF,
    [string]$CacheHF = "",
    [string]$IndiceTorch = "",
    [int]$Sesion = 5
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
if ($SoloOllama) { $ConOllama = $true; $SoloEntorno = $true; $SinClon = $true }
# con -File, PowerShell entrega «a,b» como un solo texto: se separa por comas
$Modelos = @($Modelos | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not $SoloEntorno -and -not $esAdmin) {
    Write-Host "[ERROR] Este instalador instala programas del sistema: abra PowerShell con 'Ejecutar como administrador' y vuelva a ejecutarlo."
    Write-Host "        (Para instalar solo Ollama y sus modelos no hace falta administrador: agregue -SoloOllama.)"
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
    Anotar "INFO" $nombre "se instala..."
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
        Anotar "INFO" $nombre "se descarga de la rama $Rama"
        try { Invoke-WebRequest -Uri "$RawBase/$nombre" -OutFile $destino -UseBasicParsing -ErrorAction Stop } catch { Remove-Item $destino -ErrorAction SilentlyContinue }
    }
    if (Test-Path $destino) { return $destino }
    Anotar "ERROR" $nombre "no esta junto al script y no se pudo descargar de $RawBase"
    return $null
}
$Raiz0 = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
if (-not $Requirements -or -not (Test-Path $Requirements)) { $Requirements = Join-Path $Raiz0 "02_requirements.txt" }
if (-not $SoloOllama) { $Requirements = ObtenerArchivo "02_requirements.txt" $Requirements }
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
} elseif ($SoloOllama) { Anotar "INFO" "programas del sistema" "omitidos por -SoloOllama (solo se instala Ollama y sus modelos)" }
else { Anotar "INFO" "programas del sistema" "omitidos por -SoloEntorno (Python, Git, Java y Tesseract deben estar instalados)" }

# 6. Entorno virtual y librerías
$venvPy = "$Curso\venv\Scripts\python.exe"
if (-not $SoloOllama) {
$py = $null
foreach ($candidata in @("$env:ProgramFiles\Python312\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
    if (-not $py -and (Test-Path $candidata)) { $py = $candidata }
}
if (-not $py -and (Existe "py") -and ((& py -3.12 --version 2>&1) -match "3\.12")) { $py = "py" }
if (-not (Test-Path $venvPy)) {
    if (-not $py) { Anotar "ERROR" "venv" "no hay Python 3.12: ejecutar este script como administrador, sin -SoloEntorno" }
    else {
        Anotar "INFO" "venv" "se crea $Curso\venv"
        if ($py -eq "py") { & py -3.12 -m venv "$Curso\venv" } else { & $py -m venv "$Curso\venv" }
    }
}
if (Test-Path $venvPy) {
    & $venvPy -m pip install --upgrade pip 2>&1 | Out-Null
    # PyTorch primero (indice propio): GPU con CUDA 13.2 y, si falla, la rueda de CPU de PyPI (se usa desde la sesion 4)
    if ($Sesion -lt 4) {
        Anotar "INFO" "torch" "se instala desde la sesion 4 (repetir este instalador con -Sesion 4)"
    } elseif ($SinGpu -or $IndiceTorch -eq "cpu") {
        Anotar "INFO" "torch" "se instala la versión de CPU (PyPI)"
        & $venvPy -m pip install torch==2.15.0 2>&1 | Select-Object -Last 1
    } else {
        $indice = if ($IndiceTorch) { $IndiceTorch } else { "https://download.pytorch.org/whl/cu132" }
        Anotar "INFO" "torch GPU" "se instala desde $indice (unos 2 GB)"
        & $venvPy -m pip install torch==2.15.0 --index-url $indice 2>&1 | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) {
            Anotar "AVISO" "torch GPU" "fallo el indice de GPU; se instala la version de CPU (PyPI)"
            & $venvPy -m pip install torch==2.15.0 2>&1 | Select-Object -Last 1
        }
    }
    if ($Sesion -ge 4) { if ($LASTEXITCODE -eq 0) { Anotar "OK" "torch" "2.15.0" } else { Anotar "ERROR" "torch" "fallo; revisar versión y salida a Internet" } }
    if ($Requirements -and (Test-Path $Requirements)) {
        Anotar "INFO" "pip" "se instala $Requirements (puede tardar varios minutos)"
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
    if ($SinModelosHF) { Anotar "INFO" "modelos de Hugging Face" "no se descargan (-SinModelosHF)" }
    elseif ($Sesion -lt 4) { Anotar "INFO" "modelos de Hugging Face" "no se descargan ahora (se usan desde la sesión 4; repetir este instalador con -Sesion 4)" }
    else {
        foreach ($m in @("Davlan/xlm-roberta-base-ner-hrl", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")) {
            $nombreCarpeta = "models--" + ($m -replace "/", "--")
            $carpetaModelo = "$hf\hub\$nombreCarpeta"
            if (Test-Path "$carpetaModelo\snapshots") { Anotar "OK" "modelo $m" "ya descargado"; continue }
            if ($CacheHF -and (Test-Path "$CacheHF\hub\$nombreCarpeta")) {
                Anotar "INFO" "modelo $m" "se copia desde $CacheHF"
                robocopy "$CacheHF\hub\$nombreCarpeta" $carpetaModelo /E /NFL /NDL /NJH /NJS /NP | Out-Null
                if (Test-Path "$carpetaModelo\snapshots") { Anotar "OK" "modelo $m" "copiado" } else { Anotar "ERROR" "modelo $m" "no se pudo copiar" }
                continue
            }
            Anotar "INFO" "modelo $m" "se descarga de huggingface.co (unos 1,1 GB entre los dos; puede tardar varios minutos)"
            & $venvPy -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$m')" 2>&1 | Select-Object -Last 1
            if ($LASTEXITCODE -eq 0 -and (Test-Path "$carpetaModelo\snapshots")) { Anotar "OK" "modelo $m" "descargado" } else { Anotar "ERROR" "modelo $m" "fallo la descarga: revisar la salida a Internet y repetir el instalador" }
        }
    }
} else { Anotar "ERROR" "venv" "no se creó" }
}

# 7. Repositorio del curso (clon) y datos de practica
$clon = "$Curso\trabajo\entorno-extraccion-documental"
if (Test-Path (Join-Path $Raiz0 ".git")) { $clon = $Raiz0 }
if (-not $SinClon -and -not (Test-Path "$clon\.git")) {
    $git = if (Existe "git") { "git" } elseif (Test-Path "$env:ProgramFiles\Git\cmd\git.exe") { "$env:ProgramFiles\Git\cmd\git.exe" } else { $null }
    if ($git) {
        Anotar "INFO" "repositorio" "se clona la rama $Rama en $clon"
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
if (-not $SoloOllama -and (Test-Path "$clon\06_traer_datos.ps1")) {
    $global:LASTEXITCODE = 0
    & "$clon\06_traer_datos.ps1" -Destino "$Curso\datos"
    if ($LASTEXITCODE -eq 0) { Anotar "OK" "datos de practica" "$Curso\datos" } else { Anotar "ERROR" "datos de practica" "ver 06_traer_datos.ps1" }
}
if ($Zip -and (Test-Path $Zip)) {
    Expand-Archive -Path $Zip -DestinationPath "$Curso\paquete" -Force
    Anotar "OK" "paquete" "descomprimido en $Curso\paquete"
}

# 8. GPU
if (Existe "nvidia-smi") { Anotar "OK" "GPU" ((& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) -join "; ") }
else { Anotar "AVISO" "GPU" "nvidia-smi no está: falta el controlador NVIDIA; se necesita desde la sesión 4 (pedir a soporte la extensión de GPU de Azure)" }

# 9. Ollama y sus modelos (desde la sesion 5, solo con -ConOllama). Ollama se instala para el usuario de la sesion de Windows
#    (%LOCALAPPDATA%\Programs\Ollama), sin administrador. Las variables se fijan ANTES del instalador, porque el instalador abre
#    Ollama al terminar y Ollama lee la carpeta de modelos al arrancar. No se espera con Start-Process -Wait: esa opcion espera
#    tambien a la aplicacion que el instalador deja abierta y la consola queda colgada.
$ApiOllama = "http://127.0.0.1:11434"
function VersionApiOllama {
    try { return (Invoke-RestMethod -Uri "$ApiOllama/api/version" -TimeoutSec 3 -UseBasicParsing).version } catch { return $null }
}
function EsperarApiOllama([int]$segundos) {
    $fin = (Get-Date).AddSeconds($segundos)
    do {
        $v = VersionApiOllama
        if ($v) { return $v }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $fin)
    return $null
}
function VersionProgramaOllama([string]$exe) {
    # ollama --version escribe en la salida normal o en la de errores (si el servidor no corre): se leen las dos
    if (-not (Test-Path $exe)) { return $null }
    try {
        $psi = New-Object Diagnostics.ProcessStartInfo $exe, "--version"
        $psi.UseShellExecute = $false; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true; $psi.CreateNoWindow = $true
        $p = [Diagnostics.Process]::Start($psi)
        $texto = $p.StandardOutput.ReadToEnd() + " " + $p.StandardError.ReadToEnd()
        $null = $p.WaitForExit(30000)
    } catch { return $null }
    if ($texto -match "(\d+\.\d+\.\d+)") { return $Matches[1] }
    return $null
}
function ModelosOllama {
    try { return @((Invoke-RestMethod -Uri "$ApiOllama/api/tags" -TimeoutSec 10 -UseBasicParsing).models | ForEach-Object { $_.name }) } catch { return @() }
}
function NombreCompleto([string]$m) { if ($m -match ":") { return $m } else { return "${m}:latest" } }
function CarpetaModelosDelServidor {
    # La ultima linea «server config» del registro dice con que carpeta arranco el servidor de Ollama
    $registro = Join-Path $env:LOCALAPPDATA "Ollama\server.log"
    if (-not (Test-Path $registro)) { return $null }
    $linea = Select-String -Path $registro -Pattern "server config" -SimpleMatch | Select-Object -Last 1
    if ($linea -and $linea.Line -match "OLLAMA_MODELS:(\S*)") { return ($Matches[1] -replace "\\\\", "\") }
    return $null
}
function CuentaDeLaSesion {
    # Cuenta duena del escritorio (explorer.exe) en esta sesion de Windows; $null si no se puede leer
    try {
        $idSesion = (Get-Process -Id $PID).SessionId
        $explorador = Get-CimInstance Win32_Process -Filter "Name='explorer.exe' AND SessionId=$idSesion" -ErrorAction Stop | Select-Object -First 1
        if ($explorador) {
            $duenio = Invoke-CimMethod -InputObject $explorador -MethodName GetOwner -ErrorAction Stop
            if ($duenio.User) { return "$($duenio.Domain)\$($duenio.User)" }
        }
    } catch { }
    return $null
}

if ($ConOllama) {
    $dirOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    $exeOllama = Join-Path $dirOllama "ollama.exe"
    $appOllama = Join-Path $dirOllama "ollama app.exe"
    $carpetaModelos = "$Curso\modelos\ollama"
    $cuentaActual = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $cuentaSesion = CuentaDeLaSesion
    $otraCuenta = ($cuentaSesion -and ($cuentaSesion -ne $cuentaActual))
    if ($otraCuenta) {
        Anotar "AVISO" "Ollama" ("PowerShell corre con la cuenta $cuentaActual, pero la sesión de Windows es de ${cuentaSesion}: " +
            "Ollama quedaría en el perfil de $cuentaActual y no se vería en la sesión. No se instala. " +
            "Se abre PowerShell SIN 'Ejecutar como administrador' (en la sesión propia) y se repite este instalador con -SoloOllama.")
    } else {
        if ($esAdmin) { Anotar "INFO" "Ollama" "PowerShell corre como administrador con la misma cuenta de la sesión ($cuentaActual): Ollama queda en su perfil" }
        # 9a. Variables de usuario ANTES de instalar (en la VM del curso) y en esta consola
        New-Item -ItemType Directory -Force $carpetaModelos | Out-Null
        if ($Curso -eq "C:\curso") {   # una prueba con otra carpeta no toca las variables del usuario
            [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $carpetaModelos, "User")
            [Environment]::SetEnvironmentVariable("OLLAMA_NO_CLOUD", "1", "User")
        }
        $env:OLLAMA_MODELS = $carpetaModelos
        $env:OLLAMA_NO_CLOUD = "1"
        Anotar "OK" "OLLAMA_MODELS" "$carpetaModelos; OLLAMA_NO_CLOUD=1 (sin modelos en la nube)"

        # 9b. Programa: se instala si falta o si su version es anterior a 0.15.5 (glm-ocr la exige)
        $version = VersionProgramaOllama $exeOllama
        $vieja = $false
        if ($version) { try { $vieja = ([version]$version -lt [version]"0.15.5") } catch { $vieja = $false } }
        if ($version -and -not $vieja) {
            Anotar "OK" "Ollama" "ya instalado (versión $version en $dirOllama)"
        } else {
            if ($vieja) {
                Anotar "INFO" "Ollama" "versión $version anterior a 0.15.5: se actualiza"
                Get-Process -Name "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
            }
            $exe = if ($InstaladorOllama -and (Test-Path $InstaladorOllama)) { $InstaladorOllama } else { Join-Path $Tmp "OllamaSetup.exe" }
            $firmado = (Test-Path $exe) -and ((Get-AuthenticodeSignature $exe).Status -eq "Valid")
            if (-not $firmado) {
                Remove-Item $exe -Force -ErrorAction SilentlyContinue
                foreach ($url in @("https://github.com/ollama/ollama/releases/download/$VersionOllama/OllamaSetup.exe", "https://ollama.com/download/OllamaSetup.exe")) {
                    Anotar "INFO" "Ollama" "se descarga OllamaSetup.exe (unos 1,7 GB) desde $url"
                    if (Existe "curl.exe") { & curl.exe -L --fail --retry 3 -o $exe $url } else { try { Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing } catch { } }
                    $firmado = (Test-Path $exe) -and ((Get-AuthenticodeSignature $exe).Status -eq "Valid")
                    if ($firmado) { break }
                    Remove-Item $exe -Force -ErrorAction SilentlyContinue
                    Anotar "AVISO" "Ollama" "la descarga no terminó o el archivo no trae la firma de Ollama; se prueba con otro enlace"
                }
            }
            if (-not $firmado) {
                Anotar "ERROR" "Ollama" "no se pudo descargar OllamaSetup.exe completo: revisar la salida a Internet y repetir el instalador"
            } else {
                Anotar "INFO" "Ollama" "se instala en $dirOllama (sin ventanas; unos minutos)"
                $registroInst = Join-Path $Tmp "ollama_instalacion.log"
                $proc = Start-Process -FilePath $exe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$registroInst`"" -PassThru
                $null = $proc.Handle   # conserva el proceso para leer su codigo de salida
                if (-not $proc.WaitForExit(900000)) { Anotar "ERROR" "Ollama" "el instalador no terminó en 15 min (registro: $registroInst)" }
                elseif ($proc.ExitCode -ne 0) { Anotar "ERROR" "Ollama" "el instalador terminó con el código $($proc.ExitCode) (registro: $registroInst)" }
                ActualizarPath
                $version = VersionProgramaOllama $exeOllama
                if ($version) { Anotar "OK" "Ollama" "instalado (versión $version en $dirOllama)" } else { Anotar "ERROR" "Ollama" "no quedó $exeOllama (registro: $registroInst)" }
            }
        }

        # 9c. Servicio: la API debe responder en localhost:11434 (hasta 90 s; si no, se abre Ollama y, si sigue sin responder, ollama serve)
        if (Test-Path $exeOllama) {
            $api = EsperarApiOllama 30
            if (-not $api -and (Test-Path $appOllama) -and -not (Get-Process -Name "ollama app" -ErrorAction SilentlyContinue)) {
                Anotar "INFO" "Ollama" "la API no responde: se abre la aplicación Ollama"
                Start-Process -FilePath $appOllama
                $api = EsperarApiOllama 30
            }
            if (-not $api) {
                Anotar "INFO" "Ollama" "la API sigue sin responder: se inicia ollama serve en segundo plano"
                Start-Process -FilePath $exeOllama -ArgumentList "serve" -WindowStyle Hidden
                $api = EsperarApiOllama 30
            }
            if ($api) { Anotar "OK" "Ollama (API)" "responde en localhost:11434 (versión $api)" }
            else { Anotar "ERROR" "Ollama (API)" "no responde en localhost:11434 tras 90 s: abrir «Ollama» desde Inicio y revisar $env:LOCALAPPDATA\Ollama\server.log" }

            $carpetaServidor = CarpetaModelosDelServidor
            if ($api -and $carpetaServidor -and ($carpetaServidor.TrimEnd("\") -ne $carpetaModelos.TrimEnd("\"))) {
                Anotar "AVISO" "Ollama (carpeta de modelos)" ("el servidor usa $carpetaServidor y no $carpetaModelos (Ollama ya estaba abierto al fijar OLLAMA_MODELS). " +
                    "Se cierra Ollama desde su ícono junto al reloj (Quit Ollama), se abre de nuevo desde Inicio y se repite este instalador.")
            }

            # 9d. Modelos: ollama pull muestra el avance y retoma la descarga si se corta; lo ya descargado se omite
            if ($api -and -not $SinModelo) {
                $libre = [math]::Round((Get-PSDrive -Name $carpetaModelos.Substring(0, 1)).Free / 1GB)
                if ($libre -lt 15) { Anotar "AVISO" "disco" "quedan $libre GB libres; los tres modelos ocupan 12,5 GB" }
                foreach ($m in $Modelos) {
                    if ((ModelosOllama) -contains (NombreCompleto $m)) { Anotar "OK" "modelo $m" "ya descargado"; continue }
                    Anotar "INFO" "modelo $m" "se descarga (qwen3.5:4b 3,3 GB; glm-ocr 2,7 GB; qwen3.5:9b 6,6 GB)"
                    & $exeOllama pull $m
                    if ($LASTEXITCODE -ne 0) {
                        Anotar "AVISO" "modelo $m" "la descarga se cortó: se repite (retoma donde quedó)"
                        & $exeOllama pull $m
                    }
                    if ((ModelosOllama) -contains (NombreCompleto $m)) { Anotar "OK" "modelo $m" "descargado" }
                    else { Anotar "ERROR" "modelo $m" "no quedó descargado: repetir 'ollama pull $m' (retoma donde quedó)" }
                }
            } elseif ($SinModelo) { Anotar "INFO" "modelos de Ollama" "no se descargan (-SinModelo)" }
        }
    }
} elseif ($Sesion -ge 5) { Anotar "INFO" "Ollama" "no se instala ahora: en la sesión 5 se instala con el paso 3 de la guía (este instalador con -SoloOllama)" }

# 10. Verificacion final
$verif = if (Test-Path "$clon\03_verificar_entorno.py") { "$clon\03_verificar_entorno.py" } else { $Verificador }
if ((Test-Path $venvPy) -and $verif) {
    Write-Host "`n===== VERIFICACION DEL ENTORNO (sesiones 1 a $Sesion) ====="
    $extra = @()
    if ($ConOllama -and -not $otraCuenta) { $extra += "--con-llm" }
    & $venvPy $verif --sesion $Sesion --curso $Curso @extra
}

Write-Host "`n===== RESUMEN ====="
$Resumen | Where-Object { $_ -notmatch "^\[INFO\]" } | ForEach-Object { Write-Host $_ }
Write-Host "Registro: $Log"
Write-Host "`nSIGUIENTES PASOS (en una consola de PowerShell NUEVA; no hace falta administrador):"
Write-Host "  1. Si se instalaron programas del sistema, abrir la consola nueva: el PATH, HF_HOME y OLLAMA_MODELS se actualizan al abrirla."
Write-Host "  2. Verificar el entorno: $venvPy $verif --sesion $Sesion"
Write-Host "  3. Carpeta del curso: cd $clon"
Write-Host "  4. Cuaderno: $venvPy -m jupyterlab (desde $clon)"
if ($ConOllama) { Write-Host "  5. Modelos de Ollama: ollama list (deben figurar $($Modelos -join ', '))" }
