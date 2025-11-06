@echo off
setlocal ENABLEDELAYEDEXPANSION

rem Determine repository root (directory where this script resides)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul

rem Ensure dist directory exists
if not exist dist mkdir dist >nul

rem Generate timestamp in a locale-independent way using PowerShell
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TIMESTAMP=%%I"

set "OUTPUT_PATH=dist\invoice-archiver-%TIMESTAMP%.zip"

rem Remove existing archive with same name if present
if exist "%OUTPUT_PATH%" del /f /q "%OUTPUT_PATH%" >nul

rem Verify that tar is available
where tar >nul 2>&1
if errorlevel 1 (
    echo [ERROR] tar command not found. Please ensure tar is available in PATH.& goto :end
)

rem Package required artifacts into a zip archive
tar -a -c -f "%OUTPUT_PATH%" ^
    --exclude=backend/.venv ^
    --exclude="*/__pycache__" ^
    --exclude="*/__pycache__/*" ^
    --exclude=frontend/node_modules ^
    --exclude=frontend/dist ^
    --exclude=data/invoice-test ^
    --exclude=data/tmp ^
    --exclude="*.pyc" ^
    backend ^
    frontend ^
    data ^
    docker-compose.yml ^
    package_project.cmd

if errorlevel 1 (
    echo [ERROR] Packaging failed.& goto :end
)

echo [OK] Package created at %OUTPUT_PATH%

:end
popd >nul
endlocal
