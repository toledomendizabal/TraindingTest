@echo off
title TradingSignal Pro - Sistema de Trading
echo ============================================================
echo    TradingSignal Pro - Sistema Inteligente de Trading
echo ============================================================
echo.

:: Check Python version
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instale Python 3.11.9
    pause
    exit /b 1
)

:: Check if virtual environment exists
if not exist "venv" (
    echo [INFO] Creando entorno virtual...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install dependencies
echo [INFO] Verificando dependencias...
pip install -r requirements.txt --quiet

:: Check .env file
if not exist ".env" (
    echo [ERROR] Archivo .env no encontrado.
    echo [INFO] Copie .env.example a .env y configure las variables.
    pause
    exit /b 1
)

:: Create necessary directories
if not exist "logs" mkdir logs
if not exist "excel" mkdir excel
if not exist "reports" mkdir reports
if not exist "config" mkdir config

echo.
echo [INFO] Iniciando sistema multi-hilo...
echo [INFO] - Motor de Senales (cada 10s)
echo [INFO] - Monitor de Posiciones (cada 1s)
echo [INFO] - API FastAPI (puerto 8000)
echo [INFO] - Programador APScheduler
echo.
echo [INFO] Dashboard: http://localhost:8000
echo [INFO] API Docs:  http://localhost:8000/docs
echo.

:: Start the system
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
