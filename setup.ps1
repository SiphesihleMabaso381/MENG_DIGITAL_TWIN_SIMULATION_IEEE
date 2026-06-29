param(
    [switch]$SkipVenv,
    [switch]$SkipInstall,
    [string]$PythonCmd = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/4] Checking Python..."
& $PythonCmd --version

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not $SkipVenv) {
    Write-Host "[2/4] Creating virtual environment (.venv)..."
    if (-not (Test-Path ".venv")) {
        & $PythonCmd -m venv .venv
    } else {
        Write-Host "      .venv already exists, reusing it."
    }

    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
} else {
    Write-Host "[2/4] Skipping virtual environment creation."
    $venvPython = $PythonCmd
}

if (-not $SkipInstall) {
    Write-Host "[3/4] Installing dependencies..."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
} else {
    Write-Host "[3/4] Skipping dependency installation."
}

Write-Host "[4/4] Checking feeder entry files..."
$requiredPaths = @(
    "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/IEEE13Nodeckt.dss",
    "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-34Bus/electricdss-code-r4166-trunk-Distrib-IEEETestCases-34Bus/Run_IEEE34Mod1.dss",
    "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-123Bus/electricdss-code-r4166-trunk-Distrib-IEEETestCases-123Bus/Run_IEEE123Bus.DSS"
)

$missing = @()
foreach ($p in $requiredPaths) {
    if (Test-Path $p) {
        Write-Host "      OK: $p"
    } else {
        Write-Warning "      MISSING: $p"
        $missing += $p
    }
}

Write-Host ""
Write-Host "Setup complete."
if ($missing.Count -gt 0) {
    Write-Warning "Some feeder files are missing. Full simulations may fail until feeder folders are copied in."
}

if (-not $SkipVenv) {
    Write-Host "To run with virtual environment:"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  python main.py"
    Write-Host "  python main.py --full-ieee13"
} else {
    Write-Host "Run commands:"
    Write-Host "  python main.py"
    Write-Host "  python main.py --full-ieee13"
}
