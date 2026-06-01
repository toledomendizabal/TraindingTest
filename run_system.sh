#!/bin/bash
echo "============================================================"
echo "   TradingSignal Pro - Sistema Inteligente de Trading"
echo "============================================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 no encontrado. Instale Python 3.11.9"
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "[INFO] Creando entorno virtual..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "[INFO] Verificando dependencias..."
pip install -r requirements.txt --quiet

# Check .env file
if [ ! -f ".env" ]; then
    echo "[ERROR] Archivo .env no encontrado."
    echo "[INFO] Copie .env.example a .env y configure las variables."
    exit 1
fi

# Create necessary directories
mkdir -p logs excel reports config

echo ""
echo "[INFO] Iniciando sistema multi-hilo..."
echo "[INFO] - Motor de Señales (cada 10s)"
echo "[INFO] - Monitor de Posiciones (cada 1s)"
echo "[INFO] - API FastAPI (puerto 8000)"
echo "[INFO] - Programador APScheduler"
echo ""
echo "[INFO] Dashboard: http://localhost:8000"
echo "[INFO] API Docs:  http://localhost:8000/docs"
echo ""

# Start the system
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
