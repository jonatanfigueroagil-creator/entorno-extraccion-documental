# 06_traer_datos.ps1: deja los documentos ficticios de practica en C:\curso\datos.
# Incluye el lote publico real: queda en $Destino\14_Publico_Real (la ruta que usa el codigo del curso).
# Uso (PowerShell, desde la carpeta clonada):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\06_traer_datos.ps1
#   Opcion con archivo comprimido (ruta local o enlace https):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\06_traer_datos.ps1 -Zip <ruta-o-enlace>
# Se puede repetir: si los datos ya estan, no hace nada (use -Forzar para reemplazarlos).
[CmdletBinding()]
param(
    [string]$Zip = "",
    [string]$Destino = "C:\curso\datos",
    [switch]$Forzar
)
$ErrorActionPreference = "Stop"
$Raiz = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Marca = "01_Lote_S02"

function Contiene([string]$carpeta) { return (Test-Path (Join-Path $carpeta $Marca)) }

function ContieneLote([string]$carpeta) { return (Test-Path (Join-Path $carpeta "14_Publico_Real\00_FICHAS.json")) }

if ((Contiene $Destino) -and (ContieneLote $Destino) -and -not $Forzar) { Write-Host "[OK] datos de practica ya estan en $Destino"; exit 0 }

$origen = ""
$temporal = Join-Path $env:TEMP ("datos_curso_" + [guid]::NewGuid().ToString("N"))
try {
    if ($Zip) {
        $archivo = $Zip
        if ($Zip -match "^https?://") {
            New-Item -ItemType Directory -Force $temporal | Out-Null
            $archivo = Join-Path $temporal "datos.zip"
            Invoke-WebRequest -Uri $Zip -OutFile $archivo -UseBasicParsing
        }
        if (-not (Test-Path $archivo)) { throw "no existe el archivo comprimido: $archivo" }
        $extraido = Join-Path $temporal "extraido"
        Expand-Archive -Path $archivo -DestinationPath $extraido -Force
        $hallada = Get-ChildItem -Path $extraido -Recurse -Directory -Filter $Marca | Select-Object -First 1
        if (-not $hallada) { throw "el archivo comprimido no contiene la carpeta $Marca" }
        $origen = $hallada.Parent.FullName
    } else {
        $local = Join-Path $Raiz "05_Laboratorios\02_Datos_Practica"
        if (-not (Contiene $local)) { throw "no esta la carpeta 05_Laboratorios\02_Datos_Practica junto a este script; use -Zip" }
        $origen = $local
    }
    New-Item -ItemType Directory -Force $Destino | Out-Null
    Copy-Item -Path (Join-Path $origen "*") -Destination $Destino -Recurse -Force
    if (-not (Contiene $Destino)) { throw "la copia no dejo $Marca en $Destino" }
    $n = (Get-ChildItem -Path $Destino -Recurse -File).Count
    Write-Host "[OK] datos de practica copiados a ${Destino}: $n archivos"
} catch {
    Write-Host "[ERROR] datos de practica: $($_.Exception.Message)"
    exit 1
} finally {
    if (Test-Path $temporal) { Remove-Item -Recurse -Force $temporal -ErrorAction SilentlyContinue }
}
