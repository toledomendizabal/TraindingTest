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
    echo [ERROR] Instale Python 3.11+ desde https://www.python.org
    echo [ERROR] Asegurese de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [INFO] %%i detectado

:: Verify Python version compatibility (3.11 to 3.14)
python -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor >= 11 else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo [ADVERTENCIA] =====================================================
    echo [ADVERTENCIA] Se requiere Python 3.11 o superior.
    echo [ADVERTENCIA] Descargue desde: https://www.python.org/downloads/
    echo [ADVERTENCIA] =====================================================
    echo.
    pause
    exit /b 1
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

:: Upgrade pip first
echo [INFO] Actualizando pip...
python -m pip install --upgrade pip --quiet 2>nul

:: Install dependencies
echo [INFO] Instalando dependencias...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo.
    echo [INFO] Primer intento fallo. Reintentando con --only-binary para pandas/numpy...
    pip install pandas numpy --only-binary=:all: --quiet 2>nul
    if errorlevel 1 (
        echo [INFO] Intentando con versiones especificas para su Python...
        pip install "pandas>=2.3.3" "numpy>=2.4.0" --only-binary=:all: --quiet 2>nul
    )
    pip install -r requirements.txt --quiet 2>nul
    if errorlevel 1 (
        echo.
        echo [ERROR] =====================================================
        echo [ERROR] No se pudieron instalar las dependencias.
        echo [ERROR] Intente manualmente:
        echo [ERROR]   pip install -r requirements.txt
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
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] Archivo .env creado desde .env.example.
        echo [INFO] Edite las credenciales antes de usar el sistema.
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
