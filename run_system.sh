#!/bin/bash
echo "============================================================"
echo "   TradingSignal Pro - Sistema Inteligente de Trading"
echo "============================================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 no encontrado. Instale Python 3.11.9 o 3.12.x"
    exit 1
fi

# Verify Python version compatibility
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [[ "$PYTHON_MINOR" -lt 11 ]] || [[ "$PYTHON_MINOR" -ge 14 ]]; then
    echo ""
    echo "[ADVERTENCIA] ====================================================="
    echo "[ADVERTENCIA] Python $PYTHON_VERSION detectado."
    echo "[ADVERTENCIA] Este proyecto requiere Python 3.11.x, 3.12.x o 3.13.x"
    echo "[ADVERTENCIA] Python 3.14 NO es compatible con pandas actualmente."
    echo "[ADVERTENCIA] Descargue Python 3.11.9 desde:"
    echo "[ADVERTENCIA] https://www.python.org/downloads/release/python-3119/"
    echo "[ADVERTENCIA] ====================================================="
    echo ""
    read -p "Presione Enter para intentar continuar de todas formas..."
fi

echo "[INFO] Python $PYTHON_VERSION detectado"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "[INFO] Creando entorno virtual..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] No se pudo crear el entorno virtual."
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "[INFO] Actualizando pip..."
python -m pip install --upgrade pip --quiet 2>/dev/null

# Install dependencies
echo "[INFO] Instalando dependencias..."
pip install -r requirements.txt --quiet 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "[INFO] Reintentando con binarios precompilados..."
    pip install pandas numpy --only-binary=:all: --quiet
    pip install -r requirements.txt --quiet
    if [ $? -ne 0 ]; then
        echo "[ERROR] No se pudieron instalar las dependencias."
        echo "[ERROR] Instale Python 3.11.9 para compatibilidad completa."
        exit 1
    fi
fi

echo "[OK] Dependencias instaladas correctamente."

# Check .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "[ADVERTENCIA] Archivo .env no encontrado."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[INFO] Archivo .env creado desde .env.example."
        echo "[INFO] Edite las credenciales antes de usar el sistema."
    else
        echo "[ERROR] No se encontró .env.example. Configure manualmente."
        exit 1
    fi
fi

# Create necessary directories
mkdir -p logs excel reports config

echo ""
echo "============================================================"
echo "[INFO] Iniciando sistema multi-hilo..."
echo "[INFO] - Motor de Señales (cada 10s)"
echo "[INFO] - Monitor de Posiciones (cada 1s)"
echo "[INFO] - API FastAPI (puerto 8000)"
echo "[INFO] - Programador APScheduler"
echo ""
echo "[INFO] Dashboard: http://localhost:8000"
echo "[INFO] API Docs:  http://localhost:8000/docs"
echo "============================================================"
echo ""

# Start the system
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
