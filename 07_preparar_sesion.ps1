# 07_preparar_sesion.ps1: deja lista la maquina para una sesion del curso.
# Hace, en orden: 1) Git, 2) la copia del curso, 3) los datos propios, 4) la rama de la sesion,
# 5) el entorno (instalador y verificador) y 6) JupyterLab.
# Uso (PowerShell o terminal de JupyterLab; el instalador pide PowerShell como administrador la primera vez):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\07_preparar_sesion.ps1 -Sesion 4
# Se puede repetir sin riesgo: lo que ya esta hecho se comprueba y se omite.
#   -SinInstalar   omite el instalador y solo ejecuta el verificador del entorno
#   -Rehacer       vuelve a preguntar el nombre, el correo y el usuario de GitHub
#   -Trabajo       carpeta donde queda la copia del curso (por omision C:\curso\trabajo)
[CmdletBinding()]
param(
    [int]$Sesion = 4,
    [switch]$SinInstalar,
    [switch]$Rehacer,
    [string]$Repositorio = "https://github.com/jonatanfigueroagil-creator/entorno-extraccion-documental.git",
    [string]$Trabajo = "C:\curso\trabajo"
)
$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# carpeta de trabajo y cuaderno de cada sesion: numero = @{ carpeta; cuaderno de origen; cuaderno de trabajo }
$Sesiones = @{
    3 = @{ Carpeta = "s03_ocr";        Origen = "02_LAB_S03_OCR_Imagenes.ipynb"; Destino = "02_LAB_S03_OCR_Imagenes.ipynb" }
    4 = @{ Carpeta = "s04_extraccion"; Origen = "03_LAB_S04_PLN_Extraccion.ipynb"; Destino = "02_LAB_S04_PLN_Extraccion.ipynb" }
}
if (-not $Sesiones.ContainsKey($Sesion)) { Write-Host "[ERROR] Sesion $Sesion no disponible en este script." -ForegroundColor Red; exit 2 }
$Datos = $Sesiones[$Sesion]
$Anterior = $Sesion - 1
$Clon = Join-Path $Trabajo "entorno-extraccion-documental"
$Venv = "C:\curso\venv"

function Titulo([string]$texto) { Write-Host ""; Write-Host "=== $texto" -ForegroundColor Cyan }
function Ejecutar-Git { & git @args 2>&1 | ForEach-Object { "$_" } | Write-Host }
function Pedir([string]$dato) { do { $r = (Read-Host $dato).Trim() } while (-not $r); $r }

# ---------------------------------------------------------------- 1. Git
Titulo "1/6 Git"
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
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host "[ERROR] Git no quedo instalado. Se cierra PowerShell, se abre otra ventana como administrador y se repite el script." -ForegroundColor Red; exit 1 }
Ejecutar-Git --version

# ---------------------------------------------------------------- 2. Copia del curso
Titulo "2/6 Copia del curso"
New-Item -ItemType Directory -Force $Trabajo | Out-Null
if (-not (Test-Path $Clon)) {
    Set-Location $Trabajo
    Ejecutar-Git clone --branch "sesion-0$Sesion" $Repositorio
    if (-not (Test-Path $Clon)) { Write-Host "[ERROR] No se pudo descargar el curso. Se revisa la conexion a Internet y se repite el script." -ForegroundColor Red; exit 1 }
}
Set-Location $Clon
Ejecutar-Git status --short --branch

# ---------------------------------------------------------------- 3. Datos propios
Titulo "3/6 Datos propios"
$nombre = (& git config --global user.name 2>$null)
$correo = (& git config --global user.email 2>$null)
$hayRemoto = [bool](& git remote | Select-String -SimpleMatch -Quiet mio)
if ($Rehacer -or -not $nombre -or -not $correo -or -not $hayRemoto) {
    $nombre = Pedir "Nombre y apellido"
    $correo = Pedir "Correo electronico"
    $usuario = Pedir "Usuario de GitHub"
    Ejecutar-Git config --global user.name $nombre
    Ejecutar-Git config --global user.email $correo
    $url = "https://github.com/$usuario/extraccion-documental-sbs.git"
    if ($hayRemoto) { Ejecutar-Git remote set-url mio $url } else { Ejecutar-Git remote add mio $url }
} else {
    Write-Host "Datos ya configurados: $nombre <$correo>. Para cambiarlos, se repite el script con -Rehacer."
}
Ejecutar-Git remote -v

# ---------------------------------------------------------------- 4. Rama de la sesion
Titulo "4/6 Rama trabajo-s0$Sesion"
Ejecutar-Git add -A
Ejecutar-Git commit -m "Avance guardado antes de empezar la sesion"
Ejecutar-Git fetch origin
Ejecutar-Git fetch mio
if (-not (& git branch --list "trabajo-s0$Anterior")) { Ejecutar-Git switch -c "trabajo-s0$Anterior" --no-track "mio/trabajo-s0$Anterior" }
if (& git branch --list "trabajo-s0$Sesion") { Ejecutar-Git switch "trabajo-s0$Sesion" } else { Ejecutar-Git switch -c "trabajo-s0$Sesion" --no-track "trabajo-s0$Anterior" }
Ejecutar-Git restore --source "origin/sesion-0$Sesion" -- 01_instalar_vm.ps1 03_verificar_entorno.py 04_pipeline_sbs 05_Laboratorios 06_traer_datos.ps1 07_preparar_sesion.ps1
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Clon "06_traer_datos.ps1")
New-Item -ItemType Directory -Force (Join-Path $Clon $Datos.Carpeta) | Out-Null
Copy-Item (Join-Path $Clon "05_Laboratorios\$($Datos.Origen)") (Join-Path $Clon "$($Datos.Carpeta)\$($Datos.Destino)") -Force
$rama = (& git branch --show-current)
Write-Host "Rama actual: $rama"
if ($rama -ne "trabajo-s0$Sesion") { Write-Host "[ERROR] No se pudo cambiar a trabajo-s0$Sesion. Si mio/trabajo-s0$Anterior no existe, el avance de la sesion anterior no se subio a GitHub: se avisa al docente." -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 5. Entorno
Titulo "5/6 Entorno"
if ($SinInstalar) { Write-Host "Instalador omitido (-SinInstalar)." }
else { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Clon "01_instalar_vm.ps1") }
$python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Host "[ERROR] Falta el entorno en $Venv. Se repite el script en PowerShell abierto como administrador, sin -SinInstalar." -ForegroundColor Red; exit 1 }
& $python (Join-Path $Clon "03_verificar_entorno.py") --sesion $Sesion
$codigo = $LASTEXITCODE
if ($codigo -ne 0) { Write-Host "[AVISO] El verificador informo errores (codigo $codigo). Se avisa al docente con la salida de arriba." -ForegroundColor Yellow }

# ---------------------------------------------------------------- 6. JupyterLab
Titulo "6/6 JupyterLab"
if ($env:JPY_PARENT_PID) {
    Write-Host "Este script corre dentro de JupyterLab: ya esta abierto. Se abre el cuaderno $($Datos.Carpeta)\$($Datos.Destino)."
} else {
    $orden = "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; & '$Venv\Scripts\Activate.ps1'; Set-Location '$Clon'; jupyter lab"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $orden
    Write-Host "JupyterLab se abre en otra ventana de PowerShell. Esa ventana debe quedar abierta mientras se trabaja."
}
Write-Host ""
Write-Host "Listo: sesion $Sesion preparada en la rama $rama." -ForegroundColor Green
exit $codigo
