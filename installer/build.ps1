<#
.SYNOPSIS
    Compila nox.exe + HeyNox.exe e gera dist\HeyNox-Setup.exe.

.DESCRIPTION
    Os pacotes de voz (kokoro, silero-vad via torch) só resolvem em Python 3.11
    no Windows. Por isso o build corre num venv 3.11 obtido com `uv`
    (uv venv -p 3.11), sem mexer no Python do sistema.

.PARAMETER SkipInstaller
    Compila os executáveis mas não gera o setup.exe (útil para iterar rápido).

.PARAMETER Version
    Versão do instalador, ex.: 0.1.0. Por defeito lê de nox\__init__.py.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\build.ps1
#>
param(
    [switch]$SkipInstaller,
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BuildVenv = Join-Path $Root ".build-venv"
$PythonVersion = "3.11"
$IsccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-Version {
    if ($Version) { return $Version }
    $init = Get-Content (Join-Path $Root "nox\__init__.py") -Raw
    if ($init -match '__version__\s*=\s*"([^"]+)"') { return $Matches[1] }
    throw "Não consegui ler a versão de nox\__init__.py"
}

function New-BuildVenv {
    if (Test-Path (Join-Path $BuildVenv "Scripts\python.exe")) {
        $v = & (Join-Path $BuildVenv "Scripts\python.exe") -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
        if ($v -eq $PythonVersion) { return }
        Write-Host "Venv de build com Python $v; a recriar com $PythonVersion." -ForegroundColor Yellow
        Remove-Item $BuildVenv -Recurse -Force
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "O 'uv' é necessário para obter Python $PythonVersion (winget install astral-sh.uv)."
    }
    & uv venv -p $PythonVersion $BuildVenv
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o venv de build" }
}

function Get-Iscc {
    foreach ($candidate in $IsccCandidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Inno Setup 6 não encontrado. Instala com: winget install JRSoftware.InnoSetup"
    }
    Write-Host "Inno Setup 6 não encontrado; a instalar via winget..." -ForegroundColor Yellow
    & winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
    foreach ($candidate in $IsccCandidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Inno Setup instalado mas ISCC.exe não encontrado."
}

$ResolvedVersion = Get-Version
Write-Host "HeyNox $ResolvedVersion — build para Windows" -ForegroundColor Green

Write-Step "Preparar venv de build (Python $PythonVersion)"
New-BuildVenv
$Py = Join-Path $BuildVenv "Scripts\python.exe"
# O uv falha a compilar sdists antigos (pygetwindow/pytweening) por causa da
# limpeza da cache de build; o pip instala-os sem problema.
& uv pip install -q --python $Py pip
& $Py -m pip install -q -e ".[voice,browser,desktop]" pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Falha a instalar dependências de build" }

Write-Step "Verificar dependências de voz"
& $Py -m nox.main --check
if ($LASTEXITCODE -ne 0) { throw "nox --check falhou; revisão a configuração antes de empacotar" }

Write-Step "Gerar .spec do PyInstaller"
& $Py -m installer.pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Falha a gerar .spec" }

Write-Step "Compilar executáveis"
if (Test-Path (Join-Path $Root "build")) { Remove-Item (Join-Path $Root "build") -Recurse -Force }
if (Test-Path (Join-Path $Root "dist")) { Remove-Item (Join-Path $Root "dist") -Recurse -Force }
$DistRoot = Join-Path $Root "dist"
foreach ($spec in @("nox", "HeyNox")) {
    & $Py -m PyInstaller --noconfirm --clean --distpath $DistRoot --workpath (Join-Path $Root "build") (Join-Path $Root "installer\$spec.spec")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar $spec.spec" }
    if (-not (Test-Path (Join-Path $DistRoot "$spec\$spec.exe"))) {
        throw "$spec.exe não foi gerado em dist\$spec\"
    }
}

Write-Step "Testar executável compilado"
& (Join-Path $Root "dist\nox\nox.exe") --check
if ($LASTEXITCODE -ne 0) { throw "nox.exe compilado não passou no --check" }

# O HeyNox.exe é windowed; o código de saída continua a ser válido.
& (Join-Path $Root "dist\HeyNox\HeyNox.exe") --check
if ($LASTEXITCODE -ne 0) { throw "HeyNox.exe compilado não passou no --check" }

if ($SkipInstaller) {
    Write-Host ""
    Write-Host "Executáveis em dist\. Instalador ignorado (-SkipInstaller)." -ForegroundColor Green
    exit 0
}

Write-Step "Gerar instalador com Inno Setup"
$Iscc = Get-Iscc
$env:HEYNOX_BUILD_VERSION = $ResolvedVersion
& $Iscc (Join-Path $Root "installer\installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador" }

$Setup = Join-Path $Root "dist\HeyNox-Setup.exe"
if (-not (Test-Path $Setup)) { throw "O instalador não foi criado em $Setup" }

$SizeMb = [math]::Round((Get-Item $Setup).Length / 1MB, 1)
Write-Host ""
Write-Host ("Concluído: {0} ({1} MB)" -f $Setup, $SizeMb) -ForegroundColor Green
