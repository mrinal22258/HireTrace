# HireTrace Live Launcher for PowerShell
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "                    HIRETRACE LIVE LAUNCHER                        " -ForegroundColor Cyan
Write-Host "              Zero Paid API Calls - 100% Offline Evaluator         " -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host ""

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python not found in PATH!" -ForegroundColor Red
    Write-Host "Please ensure Python is installed and added to PATH." -ForegroundColor Yellow
    exit 1
}

$env:HIRETRACE_DEV_MODE = "1"
& python run_live.py
