param(
    [switch]$SkipVenv,
    [switch]$SkipInstall,
    [string]$VenvPath = "",
    [string]$PythonCmd = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/4] Checking Python..."
& $PythonCmd --version

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    # Keep binary packages out of OneDrive-synced folders.
    $VenvPath = Join-Path $env:LOCALAPPDATA "venvs\MENG_DIGITAL_TWIN_SIMULATION_IEEE"
}

if (-not $SkipVenv) {
    Write-Host "[2/4] Creating virtual environment ($VenvPath)..."
    if (-not (Test-Path $VenvPath)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $VenvPath) -Force | Out-Null
        & $PythonCmd -m venv $VenvPath
    } else {
        Write-Host "      Existing environment found, reusing it."
    }

    $venvPython = Join-Path $VenvPath "Scripts\python.exe"
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
    Write-Host ('  & "{0}\Scripts\Activate.ps1"' -f $VenvPath)
    Write-Host "  python main.py"
    Write-Host "  python main.py --full-ieee13"
} else {
    Write-Host "Run commands:"
    Write-Host "  python main.py"
    Write-Host "  python main.py --full-ieee13"
}
