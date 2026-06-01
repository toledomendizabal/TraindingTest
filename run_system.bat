@echo off
title TradingSignal Pro - Sistema de Trading
echo ============================================================
echo    TradingSignal Pro - Sistema Inteligente de Trading
echo ============================================================
echo.

:: Check Python exists
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado en PATH.
    echo [ERROR] Instale Python 3.11.9 o 3.12.x desde https://www.python.org
    echo [ERROR] Asegurese de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

:: Verify Python version compatibility (must be 3.11 or 3.12)
python -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor in (11,12,13) else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo [ADVERTENCIA] =====================================================
    echo [ADVERTENCIA] Su version de Python puede no ser compatible.
    echo [ADVERTENCIA] Este proyecto requiere Python 3.11.x, 3.12.x o 3.13.x
    echo [ADVERTENCIA] Python 3.14 NO es compatible con pandas actualmente.
    echo [ADVERTENCIA] Descargue Python 3.11.9: https://www.python.org/downloads/release/python-3119/
    echo [ADVERTENCIA] =====================================================
    echo.
    echo Presione cualquier tecla para intentar continuar de todas formas...
    pause >nul
)

:: Check if virtual environment exists
if not exist "venv" (
    echo [INFO] Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Upgrade pip
echo [INFO] Actualizando pip...
python -m pip install --upgrade pip --quiet 2>nul

:: Install dependencies with binary-only fallback for pandas/numpy
echo [INFO] Instalando dependencias...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo.
    echo [INFO] Reintentando instalacion con binarios precompilados...
    echo [INFO] (Esto resuelve errores de compilacion en Windows)
    echo.
    pip install pandas numpy --only-binary=:all: --quiet
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo.
        echo [ERROR] =====================================================
        echo [ERROR] No se pudieron instalar las dependencias.
        echo [ERROR] Posibles soluciones:
        echo [ERROR]   1. Instale Python 3.11.9 (recomendado)
        echo [ERROR]   2. Instale Visual Studio Build Tools
        echo [ERROR]   3. Ejecute: pip install pandas --only-binary=:all:
        echo [ERROR] =====================================================
        pause
        exit /b 1
    )
)

echo [OK] Dependencias instaladas correctamente.

:: Check .env file
if not exist ".env" (
    echo.
    echo [ADVERTENCIA] Archivo .env no encontrado.
    echo [INFO] Creando .env desde .env.example...
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] Archivo .env creado. Edite las credenciales antes de usar el sistema.
    ) else (
        echo [ERROR] No se encontro .env.example. Configure manualmente.
        pause
        exit /b 1
    )
)

:: Create necessary directories
if not exist "logs" mkdir logs
if not exist "excel" mkdir excel
if not exist "reports" mkdir reports
if not exist "config" mkdir config

echo.
echo ============================================================
echo [INFO] Iniciando sistema multi-hilo...
echo [INFO] - Motor de Senales (cada 10s)
echo [INFO] - Monitor de Posiciones (cada 1s)
echo [INFO] - API FastAPI (puerto 8000)
echo [INFO] - Programador APScheduler
echo.
echo [INFO] Dashboard: http://localhost:8000
echo [INFO] API Docs:  http://localhost:8000/docs
echo ============================================================
echo.

:: Start the system
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
