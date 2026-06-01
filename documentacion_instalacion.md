# TradingSignal Pro - Documento de Instalación y Requerimientos

Este documento contiene las especificaciones técnicas, requerimientos de hardware y software, e instrucciones detalladas de instalación para el despliegue del sistema **TradingSignal Pro**.

---

## 1. Requerimientos del Sistema

Para garantizar el correcto funcionamiento del motor de señales multi-activo y el dashboard en tiempo real, el entorno de ejecución debe cumplir con los siguientes requerimientos mínimos y recomendados:

### Hardware

| Componente | Requerimiento Mínimo | Requerimiento Recomendado |
|---|---|---|
| **Procesador (CPU)** | Intel Core i3 o equivalente (2 núcleos, 2.0 GHz) | Intel Core i5/i7 o equivalente (4+ núcleos, 3.0+ GHz) |
| **Memoria RAM** | 4 GB | 8 GB o superior |
| **Almacenamiento** | 5 GB de espacio libre (HDD) | 10 GB de espacio libre (SSD de alta velocidad) |
| **Conectividad** | Conexión a internet de 10 Mbps | Conexión a internet de 50+ Mbps (baja latencia) |

### Software y Compatibilidad

| Componente | Versión Mínima | Versión Recomendada | Notas |
|---|---|---|---|
| **Sistema Operativo** | Windows 10 / Ubuntu 20.04 | Windows 11 / Ubuntu 22.04 LTS | Soporte completo para sistemas de 64 bits |
| **Python** | 3.11.0 | 3.11.9 | Requerido para la compatibilidad de tipos y sintaxis |
| **Node.js** | 18.0.0 | 22.13.0 | Necesario para compilar el frontend de React |
| **Gestor de Paquetes** | npm 9.0.0 / pnpm 8.0.0 | pnpm 9.0.0 | Para la instalación eficiente de dependencias React |
| **Navegador Web** | Chrome 100 / Firefox 100 | Chrome estable / Edge | Con soporte para WebSockets |

---

## 2. Arquitectura del Proyecto

El sistema está diseñado bajo una arquitectura modular desacoplada que separa la lógica de análisis técnico del frontend de visualización:

```
TraindingTest/
├── app/
│   ├── api/            # Controladores de la API REST y WebSockets (FastAPI)
│   ├── core/           # Configuraciones globales, variables de entorno y logging
│   ├── models/         # Definiciones de datos (Señales, Activos, Indicadores)
│   ├── services/       # Lógica de negocio (Análisis, Excel, Telegram, Gmail, Backtesting)
│   └── utils/          # Funciones auxiliares y cálculos matemáticos de riesgo
├── frontend/           # Interfaz de usuario (React 18 + TailwindCSS + Vite)
├── config/             # Secretos y credenciales de APIs (Google OAuth2)
├── excel/              # Archivo autogestionado para el tracking offline de operaciones
├── logs/               # Registro detallado de eventos del sistema por día
├── reports/            # Historial de reportes de backtesting diarios y semanales
└── tests/              # Suite de pruebas unitarias y de validación
```

---

## 3. Instrucciones de Instalación Paso a Paso

Siga estos pasos detallados para realizar el despliegue del sistema en su entorno local:

### Paso 1: Clonar el Repositorio de GitHub

Abra su terminal o consola de comandos y clone el repositorio que acabamos de crear:

```bash
git clone https://github.com/toledomendizabal/TraindingTest.git
cd TraindingTest
```

### Paso 2: Configuración del Entorno Virtual de Python

Es fundamental aislar las dependencias del proyecto utilizando un entorno virtual:

#### En Windows:
```cmd
python -m venv venv
call venv\Scripts\activate
```

#### En Linux / macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### Paso 3: Instalación de Dependencias de Python

Con el entorno virtual activo, instale todos los paquetes necesarios especificados en el archivo `requirements.txt`:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Las dependencias principales que se instalarán incluyen:
* **FastAPI**: Framework web de alto rendimiento para la API.
* **Uvicorn**: Servidor ASGI rápido para ejecutar la aplicación.
* **Pandas** y **Numpy**: Procesamiento matemático de series temporales.
* **Openpyxl**: Manipulación y autogestión de hojas de cálculo Excel.
* **Loguru**: Sistema avanzado de logging asíncrono.
* **APScheduler**: Programador de tareas en segundo plano (análisis, reportes).
* **Pydantic**: Validación estricta de esquemas de datos.

### Paso 4: Configuración de Variables de Entorno

Copie el archivo de plantilla `.env.example` para crear su archivo de configuración `.env`:

```bash
cp .env.example .env
```

Abra el archivo `.env` con su editor de texto favorito y configure las credenciales correspondientes:

```ini
# Configuración del Servidor
API_HOST=0.0.0.0
API_PORT=8000

# Parámetros de Trading
INITIAL_CAPITAL=10000.0
RISK_PERCENTAGE=0.3

# Integración con APIs de Terceros
TWELVE_DATA_API_KEY=su_api_key_de_twelve_data
TELEGRAM_BOT_TOKEN=su_token_de_telegram_bot
TELEGRAM_CHAT_ID=su_chat_id_de_telegram

# Configuración de Gmail para Reportes
EMAIL_SENDER=su_correo@gmail.com
EMAIL_RECIPIENT=correo_destino@gmail.com
```

> **Nota sobre Twelve Data**: Puede obtener una clave de API gratuita registrándose en [Twelve Data](https://twelvedata.com/).
> **Nota sobre Telegram**: Cree un bot a través de `@BotFather` para obtener el token y obtenga su ID de chat usando `@userinfobot`.

### Paso 5: Preparación de la Integración con Gmail (Opcional)

Para habilitar el envío automático de reportes de backtesting por correo electrónico:
1. Vaya a la consola de Google Cloud Console.
2. Cree un proyecto y habilite la **Gmail API**.
3. Configure la pantalla de consentimiento de OAuth y cree credenciales de tipo **ID de cliente de OAuth 2.0**.
4. Descargue el archivo JSON de credenciales, renombre el archivo como `client_secret.json` y colóquelo dentro de la carpeta `config/` del proyecto.
5. La primera vez que el sistema intente enviar un correo o cuando inicie sesión desde el dashboard, se abrirá una ventana en su navegador para autorizar el acceso de la aplicación a su cuenta de Gmail. Esto generará el archivo `token.json` automáticamente.

### Paso 6: Compilación del Frontend (Dashboard React)

Para que el servidor de FastAPI sirva el dashboard interactivo de manera local, debe compilar el frontend:

```bash
cd frontend
pnpm install  # o 'npm install'
pnpm build    # o 'npm run build'
cd ..
```

Esto generará una carpeta `build` dentro de `frontend/` que FastAPI detectará y servirá automáticamente en la ruta raíz `http://localhost:8000`.

---

## 4. Ejecución del Sistema

El sistema cuenta con scripts automatizados de inicio para facilitar su despliegue con un solo clic:

### En Windows (Doble clic o consola):
```cmd
run_system.bat
```

### En Linux / macOS:
```bash
chmod +x run_system.sh
./run_system.sh
```

Una vez iniciado, podrá acceder a los siguientes servicios:
* **Dashboard Interactivo**: [http://localhost:8000](http://localhost:8000)
* **Documentación Interactiva de la API (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 5. Verificación e Integridad del Sistema

Antes de poner el sistema en producción o modo de monitoreo activo, se recomienda ejecutar la suite de pruebas de validación de módulos para verificar que no existan inconsistencias en su entorno local:

```bash
python tests/run_tests.py
```

El script de validación ejecutará de forma secuencial las pruebas para los 12 módulos principales:
1. **Configuración**: Carga correcta de variables y parámetros de trading.
2. **Modelos de Datos**: Validación de esquemas de señales, activos y pips.
3. **Indicadores Técnicos**: Verificación matemática de las fórmulas de los 18 indicadores técnicos (EMA, RSI, MACD, Bollinger, ATR, ADX, Stochastic, Ichimoku, etc.).
4. **Gestión de Riesgo**: Cálculo exacto de lotajes según el capital y la distancia de stop loss.
5. **Gestor Excel**: Integridad y estructura de las hojas de cálculo autogestionadas.
6. **Datos de Mercado**: Mapeo de símbolos y detección de sesiones operativas.
7. **Motor de Señales**: Algoritmo de confluencia y generación de alertas.
8. **Backtesting**: Análisis histórico de win rate, profit factor y drawdown.
9. **Scheduler**: Planificación y tiempos de ejecución de las tareas en segundo plano.
10. **API Endpoints**: Disponibilidad de rutas y estructura JSON de respuestas.
11. **Servicio de Telegram**: Conectividad y formateo de mensajes de alerta.
12. **Monitor de Posiciones**: Lógica de seguimiento de precios para activar TP1, TP2, TP3 o SL.

Si todos los tests devuelven un estado de `✓ PASS`, el sistema se encuentra en óptimas condiciones para operar de forma robusta.
