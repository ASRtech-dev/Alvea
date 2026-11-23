@echo off
setlocal EnableExtensions
title ALVEA - Process Architecture and Intelligence Studio

rem Switch to the directory containing this launcher (supports spaces and other drives)
cd /d "%~dp0"

echo.
echo ========================================================
echo   ALVEA v3.0 - Starting Process Architecture Studio...
echo ========================================================
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="
set "USE_VENV=0"

rem 1. Prefer local virtual environment (.venv) if present
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "USE_VENV=1"
    goto :check_deps
)

rem 2. Detect Python 3.11+ on PATH (python, py -3, python3)
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        goto :check_deps
    )
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
        goto :check_deps
    )
)

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python3"
        goto :check_deps
    )
)

echo [ERROR] Python 3.11 or newer was not found on this machine.
echo Download Python from: https://www.python.org/downloads/
echo Make sure to check "Add python.exe to PATH" during installation.
echo.
pause
exit /b 1

:check_deps
rem Verify required Python packages
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import pydantic, networkx, httpx, reportlab, yaml, PIL" >nul 2>&1
if not errorlevel 1 goto :launch

echo [INFO] Missing Python dependencies. Creating local virtual environment (.venv)...
if "%USE_VENV%"=="0" (
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv virtual environment.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "PYTHON_ARGS="
)

echo [INFO] Installing dependencies from requirements.txt...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Please check your internet connection.
    pause
    exit /b 1
)

:launch
rem Forward any CLI arguments (e.g. --check or --port 8080), otherwise auto-open browser
if "%~1"=="" (
    "%PYTHON_EXE%" %PYTHON_ARGS% run_alvea.py --open
) else (
    "%PYTHON_EXE%" %PYTHON_ARGS% run_alvea.py %*
)

set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] ALVEA exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%