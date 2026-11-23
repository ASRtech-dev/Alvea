@echo off
setlocal EnableExtensions
title ALVEA - Estudio de Arquitectura e Inteligencia de Procesos

rem Cambiar al directorio donde vive este script (soporta unidades distintas y espacios)
cd /d "%~dp0"

echo.
echo ========================================================
echo   ALVEA - Iniciando Estudio de Procesos...
echo ========================================================
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="
set "USE_VENV=0"

rem 1. Priorizar entorno virtual local (.venv) si existe
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "USE_VENV=1"
    goto :check_deps
)

rem 2. Detectar Python 3.11+ instalado en el sistema (python, py -3, python3)
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

echo [ERROR] No se encontro Python 3.11 o superior en el sistema.
echo Descarga Python desde: https://www.python.org/downloads/
echo Durante la instalacion marca la casilla "Add python.exe to PATH".
echo.
pause
exit /b 1

:check_deps
rem Verificar dependencias requeridas sin retrasar el arranque
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import pydantic, networkx, httpx, reportlab, yaml, PIL" >nul 2>&1
if not errorlevel 1 goto :launch

echo [INFO] Faltan dependencias de Python. Preparando entorno virtual (.venv)...
if "%USE_VENV%"=="0" (
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual .venv.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    set "PYTHON_ARGS="
)

echo [INFO] Instalando dependencias desde requirements.txt...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias. Verifica tu conexion a internet.
    pause
    exit /b 1
)

:launch
rem Si se pasan argumentos (ej. --check o --port 8080), reenviarlos directamente
if "%~1"=="" (
    "%PYTHON_EXE%" %PYTHON_ARGS% run_alvea.py --open
) else (
    "%PYTHON_EXE%" %PYTHON_ARGS% run_alvea.py %*
)

set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] ALVEA finalizo con codigo de error %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%