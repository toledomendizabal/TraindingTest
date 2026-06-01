# TradingSignal Pro

Sistema Inteligente de Señales de Trading Multi-Activo con Dashboard, Backtesting y Automatización.

## Descripción

TradingSignal Pro es un ecosistema de trading algorítmico robusto estructurado para Forex, índices sintéticos y materias primas. La plataforma unifica un backend analítico basado en Python con una interfaz interactiva moderna en React, facilitando la toma de decisiones basada en datos matemáticos rigurosos.

## Características Principales

| Característica | Descripción |
|---|---|
| 18 Indicadores Técnicos | Sistema de confluencia de 4 capas para señales de alta probabilidad |
| 12 Instrumentos Activos | Forex, Oro e Índices principales |
| Dashboard en Tiempo Real | Interfaz React con WebSockets para actualización instantánea |
| Backtesting Automatizado | Análisis diario y semanal con recomendaciones de mejora |
| Notificaciones Telegram | Señales y cierres enviados automáticamente |
| Excel Autogestionado | Registro y seguimiento offline de todas las operaciones |
| Gestión de Riesgo | 0.3% por operación con ratios 1:3, 1:6, 1:10 |
| Multi-Hilo | Motor de señales, monitor y dashboard simultáneos |

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Python 3.11.9 + FastAPI |
| Frontend | React 18 + TailwindCSS |
| Tiempo Real | WebSockets |
| Datos | Twelve Data API |
| Scheduler | APScheduler |
| Notificaciones | Telegram Bot API |
| Email | Gmail API (OAuth2) |
| Persistencia | Excel (openpyxl) |

## Instalación Rápida

```bash
# Clonar repositorio
git clone https://github.com/YOUR_USER/TraindingTest.git
cd TraindingTest

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con sus credenciales

# Ejecutar sistema
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Estructura del Proyecto

```
TraindingTest/
├── app/
│   ├── api/            # Endpoints FastAPI
│   ├── core/           # Configuración y logging
│   ├── models/         # Modelos de datos
│   ├── services/       # Lógica de negocio
│   └── utils/          # Utilidades
├── frontend/           # React Dashboard
├── config/             # Archivos de configuración
├── excel/              # Archivos Excel autogestionados
├── logs/               # Logs del sistema
├── reports/            # Reportes de backtesting
├── tests/              # Pruebas unitarias
├── .env.example        # Template de variables
├── requirements.txt    # Dependencias Python
├── run_system.bat      # Ejecutar en Windows
└── run_system.sh       # Ejecutar en Linux/Mac
```

## Licencia

Uso privado. Todos los derechos reservados.
