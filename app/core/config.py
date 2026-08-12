"""Application configuration using pydantic-settings."""
import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Twelve Data API
    TWELVE_DATA_API_KEY: str = "e046f5d7b689457fb44308ef76dc434c"

    # Trading Configuration
    INITIAL_CAPITAL: float = 10000.0
    RISK_PERCENTAGE: float = 0.3

    # Email
    EMAIL_RECIPIENT: str = "toledomendizabal.invertision@gmail.com"
    EMAIL_SENDER: str = "toledomendizabal@gmail.com"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    EXCEL_DIR: str = ""
    LOGS_DIR: str = ""
    REPORTS_DIR: str = ""
    CONFIG_DIR: str = ""

    # MetaTrader Integration
    MT4_FILES_PATH: str = os.getenv("MT4_FILES_PATH", "")
    MT4_SYNC_ENABLED: bool = True

    # --- MetaTrader 5: ejecución en vivo (órdenes reales) ---
    # IMPORTANTE: el paquete oficial `MetaTrader5` de Python se conecta a
    # una instancia LOCAL de la terminal MT5 vía IPC -- no es una API
    # remota. Esto requiere que la terminal MT5 esté instalada y abierta en
    # la MISMA máquina donde corre este backend (normalmente Windows; en
    # Linux/Mac se necesita correr MT5 bajo Wine o en una VM/servidor
    # Windows dedicado).
    #
    # MT5_LIVE_TRADING_ENABLED es un interruptor de seguridad explícito:
    # por defecto es False (el sistema solo genera señales, sin tocar el
    # bróker). Debe activarse a propósito en .env, e idealmente probarse
    # primero contra una cuenta DEMO antes de usar una cuenta real.
    MT5_LIVE_TRADING_ENABLED: bool = os.getenv("MT5_LIVE_TRADING_ENABLED", "false").lower() == "true"
    MT5_LOGIN: str = os.getenv("MT5_LOGIN", "")
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")
    # Ruta al ejecutable terminal64.exe. Opcional: si se deja vacío, se usa
    # la terminal MT5 ya instalada por defecto en el sistema (la que se
    # encuentre registrada). Solo hace falta si tienes varias terminales
    # instaladas o una instalación portable.
    MT5_TERMINAL_PATH: str = os.getenv("MT5_TERMINAL_PATH", "")
    # Número "mágico" para identificar las órdenes de este sistema entre
    # las demás operaciones de la cuenta (útil si operas manualmente
    # también en la misma cuenta).
    MT5_MAGIC_NUMBER: int = int(os.getenv("MT5_MAGIC_NUMBER", "202607"))
    # Desviación máxima de precio permitida (en puntos del bróker) al
    # enviar una orden a mercado, antes de que se rechace por slippage.
    MT5_DEVIATION_POINTS: int = int(os.getenv("MT5_DEVIATION_POINTS", "20"))

    # --- Risk / Win-Rate Tuning (CAMBIO: revisión de causas del 25% win rate) ---
    # Session Filter: restrict trading to higher-liquidity hours (UTC).
    # Operar 24h (incluyendo sesión asiática de baja liquidez) degrada el ratio señal/ruido.
    SESSION_FILTER_ENABLED: bool = True
    # CAMBIO (fix "dejó de mandar señales"): la ventana original (07-17 UTC,
    # 10h/24h = 41.7% del día) era razonable en aislamiento, pero combinada
    # con el resto de filtros (indicadores, spread, estructura en 30m/1h/4h,
    # FVG) multiplicaba la restricción hasta casi cero señales. Se amplía a
    # 06:00-21:00 UTC (15h), que sigue excluyendo la franja de menor liquidez
    # (21:00-06:00 UTC) pero da más margen. Ajustable según tus activos.
    # CAMBIO (análisis de win rate, datos reales 2026-07-07): la sesión
    # "Tokyo" (ver market_data_service.get_current_session) está definida
    # como horas 0-7 UTC. El valor anterior (SESSION_START_HOUR_UTC=6)
    # dejaba pasar 2 horas de sesión Tokyo hacia el motor de señales. Los
    # datos reales mostraron que Tokyo es, con diferencia, la peor sesión:
    # 26.3% WR y -$414 de P/L, mala de forma UNIFORME en los 7 activos
    # operados (20-40% WR en cada uno individualmente, no concentrado en un
    # solo par). Se sube el inicio a las 8:00 UTC, justo cuando
    # get_current_session() empieza a clasificar como "London", para
    # excluir por completo la sesión Tokyo del motor de señales.
    SESSION_START_HOUR_UTC: int = 8   # Inicio de la sesión de Londres (excluye Tokyo por completo)
    SESSION_END_HOUR_UTC: int = 21    # Cierre de Nueva York

    # Minimum Stop Loss distances (in pips) per asset class.
    # Subidos respecto al valor anterior (6 pips FX) para que el spread no
    # represente una fracción excesiva del SL.
    MIN_SL_PIPS_FX: float = 10.0
    MIN_SL_PIPS_INDEX_GOLD: float = 30.0

    # Maximum allowed spread (in pips) per asset class.
    # Bajado respecto al valor anterior (10 pips FX) para evitar que el spread
    # distorsione el R:R real cerca de SL mínimos ajustados.
    # CAMBIO (fix "dejó de mandar señales"): 3.0 pips resultó demasiado
    # estricto para spreads reales de bróker en vivo (vía MT4), sobre todo en
    # pares cruzados o fuera del pico de liquidez. 5.0 sigue siendo más
    # estricto que el original (10.0) pero no bloquea operativa normal.
    MAX_SPREAD_PIPS_FX: float = 5.0
    MAX_SPREAD_PIPS_INDEX_GOLD: float = 30.0
    MAX_SPREAD_PIPS_XAU: float = 50.0

    # Take Profit structure expressed as multiples of the SL distance (R).
    # TP1 se usa para cierre parcial + mover SL a breakeven (sube el win rate
    # real, porque una operación que llega a 1R y luego revierte deja de ser
    # una pérdida total y pasa a ser una ganancia parcial o un breakeven).
    #
    # CAMBIO (análisis de datos reales, 2026-07-22, 375 trades del
    # 2026-07-16 al 2026-07-21): la advertencia hecha al bajar TP1 a 0.7R se
    # confirmó exactamente en los datos reales:
    #   - Pérdida promedio por SL: -$29.94
    #   - Ganancia promedio por breakeven (tocó TP1, revirtió): +$14.59
    #   - Ratio: una sola pérdida por SL borra ~2 ganancias de breakeven.
    #   - Solo 21.9% de las operaciones alcanzaban TP3 completo (<30%).
    # Se sube TP1 de 0.7R a 0.85R (a medio camino entre el original 1.0R y
    # el 0.7R agresivo) y se sube TP1_CLOSE_PCT de 50% a 60% -- ambos
    # cambios apuntan directamente a que la ganancia "asegurada" en
    # breakeven sea más comparable a una pérdida por SL, sin perder toda la
    # ventaja de que TP1 siga siendo más fácil de alcanzar que el original.
    # TP3 bajado de 3.0R a 2.2R para que el objetivo final sea más
    # alcanzable (buscando subir el 21.9% de operaciones que llegan a TP3
    # completo), conservando una recompensa todavía sólida.
    # CAMBIO (a pedido del usuario, 2026-08-11 -- prueba comparativa por
    # estrategia hasta el viernes): se pide explícitamente que las señales
    # sean 1:3 (relación riesgo:beneficio). Se sube TP1 de 0.85R a 3.0R,
    # y TP2/TP3 se reescalan proporcionalmente a 6R/10R -- esto además
    # coincide exactamente con las etiquetas que el frontend
    # (SignalsPage.jsx) ya mostraba desde antes ("TP1 (1:3)", "TP2 (1:6)",
    # "TP3 (1:10)"), que habían quedado desincronizadas del valor real
    # (0.85R) usado en el motor. Con este cambio, ambos vuelven a coincidir.
    #
    # OJO -- tensión con el hallazgo anterior (2026-07-22, ver historial
    # arriba): con 375 trades reales, subir TP1 de 0.7R a un valor más alto
    # ya había mostrado ser más difícil de alcanzar (<30% llegaban a TP
    # completo con 2.2R). Subir ahora a 3R es un cambio aún más agresivo en
    # esa misma dirección. Se aplica de todas formas porque el objetivo
    # actual es distinto: comparar el desempeño de cada estrategia con una
    # relación riesgo:beneficio fija y pareja (1:3) entre el 11 y el
    # viernes, no maximizar win rate todavía. Si el resultado real de esta
    # semana muestra que 1:3 es demasiado difícil de alcanzar (revisa
    # signals_tracking.xlsx: % de señales que llegan a take_profit_1 vs las
    # que cierran en stop_loss), vale la pena bajarlo de nuevo con esa
    # evidencia fresca en mano.
    TP1_R_MULTIPLE: float = 3.0
    TP2_R_MULTIPLE: float = 6.0
    TP3_R_MULTIPLE: float = 10.0

    # Percentage of the position closed at each take-profit level.
    # Debe sumar 100.
    # CAMBIO (mismo análisis 2026-07-22): TP1 sube de 50% a 60% para que la
    # ganancia asegurada en breakeven sea mayor por operación (ver
    # justificación arriba). TP2 baja de 25% a 20% para compensar; TP3
    # (remanente) queda en 20% en vez de 25%.
    TP1_CLOSE_PCT: float = 60.0
    TP2_CLOSE_PCT: float = 20.0
    TP3_CLOSE_PCT: float = 20.0

    # Active Assets
    # HISTORIAL (mantenido por trazabilidad, ya NO aplica tal cual):
    # el motor anterior (basado en 18 indicadores) había excluido USDJPY,
    # USDCHF y USDCAD de ACTIVE_ASSETS por bajo win rate real:
    #   USDJPY: peor activo en las 3 sesiones (10-25% WR)
    #   USDCHF: n=47, 42.6% WR, P/L -$225.30
    #   USDCAD: n=43, 37.2% WR, P/L -$176.40
    # CAMBIO (migración a motor de estrategias, a pedido explícito del
    # usuario): se reincorporan estos 3 pares porque ahora son señales
    # generadas por ESTRATEGIAS SMC específicas por grupo (ver
    # app/services/strategy_engine.py), no por el mismo conteo de
    # indicadores que produjo esos números. Aun así, ES RECOMENDABLE volver
    # a medir el win rate real de USDJPY/USDCHF/USDCAD específicamente
    # bajo el nuevo motor antes de asumir que el problema de fondo (USD
    # como divisa BASE) ya no aplica -- el filtro de tendencia macro
    # (_validate_macro_trend) sigue activo y sin cambios.
    #
    # CAMBIO (a pedido del usuario): ACTIVE_ASSETS ahora es el listado
    # COMPLETO de "Tablas_de_aplicacion.html" (28 activos: 19 pares de
    # divisas + 5 índices + 4 metales/materias primas). La tarjeta de
    # resumen del dashboard adjunto decía "24 Divisas, Índices y Metales",
    # pero la tabla en sí enumera 28 activos distintos -- se usó el
    # listado explícito de la tabla (más específico) como fuente de
    # verdad. Si en realidad son 24, dime cuáles 4 quitar.
    ACTIVE_ASSETS: List[str] = [
        # --- Divisas: Majors (Fila 1) ---
        "EURUSD", "GBPUSD", "USDCHF", "NZDUSD",
        # --- Divisas: Yen & Commodity (Fila 2) ---
        "USDJPY", "AUDUSD", "USDCAD",
        # --- Divisas: Cruces / Minors (Fila 3) ---
        "EURGBP", "EURJPY", "EURCHF", "GBPJPY", "CHFJPY", "AUDJPY",
        "CADJPY", "NZDJPY", "AUDNZD", "AUDCHF", "GBPCHF", "CADCHF",
        # --- Índices Bursátiles (Fila 4) ---
        "US30Cash", "US500Cash", "US100Cash", "GER40Cash", "STOXX50Cash",
        # --- Materias Primas y Metales (Fila 5) ---
        "XAUUSD", "WTI", "BRENT", "COPPER",
    ]

    # Available Assets (full list) -- ampliado para incluir todos los pares
    # de la tabla, incluso los que no estén en ACTIVE_ASSETS por ahora.
    AVAILABLE_FOREX: List[str] = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD", "AUDUSD",
        "EURGBP", "EURJPY", "EURCHF", "GBPJPY", "CHFJPY", "AUDJPY", "CADJPY",
        "NZDJPY", "AUDNZD", "AUDCHF", "GBPCHF", "CADCHF",
    ]
    AVAILABLE_COMMODITIES: List[str] = [
        "XAUUSD", "XAGUSD", "WTI", "BRENT", "COPPER", "USOIL", "UKOIL"
    ]
    AVAILABLE_INDICES: List[str] = [
        "US30Cash", "US100Cash", "US500Cash", "GER40Cash", "STOXX50Cash",
        "UK100Cash", "JP225Cash", "AU200Cash"
    ]

    # --- Activos de COMPLEMENTO (filtro/confirmación macro, columna final
    # de la tabla) -- normalmente NO se operan directamente, se usan solo
    # como contexto (ej. DXY para dirección del dólar, VIX para sentimiento
    # de riesgo). Disponibilidad real depende de tu proveedor de datos
    # (Twelve Data) y de si tu bróker los ofrece como símbolo operable.
    COMPLEMENTARY_ASSETS: List[str] = [
        "DXY", "US10Y", "JP225", "WTI", "BRENT", "GER40Cash", "STOXX50Cash",
        "EURUSD", "VIX", "XAUUSD", "BUND", "TIPS", "AUDUSD",
    ]


    # --- Señales "Por Confirmar" (estrategia parcial: 1 de 2 confirmó) ---
    # Ver excel_manager.register_pending_signal / pending_signals_monitor.py.
    PENDING_SIGNALS_EXPIRY_MINUTES: int = int(os.getenv("PENDING_SIGNALS_EXPIRY_MINUTES", "60"))
    PENDING_SIGNALS_CHECK_INTERVAL_SECONDS: int = int(os.getenv("PENDING_SIGNALS_CHECK_INTERVAL_SECONDS", "60"))

    # --- Alias de símbolo por bróker (archivos MT4/MT5) ---
    # CAMBIO (fix, 2026-08-07): algunos brokers usan nombres distintos para
    # índices/materias primas (ej. "STOXX50" en vez de "STOXX50Cash", o
    # "USOUSD"/"XTIUSD" en vez de "WTI"). Si tras agregar el símbolo a
    # Market Watch en tu terminal MT5 el archivo `history_<broker>.csv`
    # sigue sin encontrarse con el nombre "limpio" por defecto, agrega
    # aquí el nombre EXACTO que usa tu bróker (tal como aparece en Market
    # Watch) y `market_data.py` lo probará primero.
    # Ejemplo: {"WTI": "USOUSD", "BRENT": "UKOUSD", "COPPER": "XCUUSD",
    #           "STOXX50Cash": "STOXX50"}
    MT_SYMBOL_ALIASES: dict = {}

    # --- Reinicio programado del proceso + keep-alive de MT5 ---
    # CAMBIO (a pedido del usuario, 2026-08-12): reinicio limpio cada N
    # horas (por defecto 12) para evitar degradación acumulada de un
    # proceso de larga duración (fugas de memoria, conexiones colgadas,
    # estado interno desincronizado). Ver scheduler._scheduled_restart.
    #
    # PROCESS_RESTART_MODE:
    #   "self_exec"  (default): el propio proceso se relanza a sí mismo
    #                con os.execv() usando el mismo comando con el que se
    #                inició -- no requiere ningún supervisor externo
    #                (systemd, NSSM, pm2, Task Scheduler, etc.). Es el modo
    #                más simple si corres el backend "a mano" o con un
    #                script batch simple.
    #   "exit_only": el proceso solo hace un shutdown limpio y termina
    #                (sys.exit(0)) -- USA ESTE MODO si ya tienes un
    #                supervisor externo configurado para reiniciar el
    #                proceso automáticamente cuando termina (recomendado
    #                para producción: es más robusto que el auto-relanzado
    #                interno, que puede tener problemas liberando el
    #                puerto/sockets en algunos entornos). Si el proceso
    #                termina y NADA lo reinicia, el backend se queda
    #                apagado hasta que alguien lo note -- confirma que
    #                tienes un supervisor antes de usar este modo.
    PROCESS_RESTART_INTERVAL_HOURS: float = float(os.getenv("PROCESS_RESTART_INTERVAL_HOURS", "12"))
    PROCESS_RESTART_MODE: str = os.getenv("PROCESS_RESTART_MODE", "self_exec")

    # Chequeo de salud de la conexión MT5 (reconecta si se cayó), en minutos.
    MT5_HEALTH_CHECK_INTERVAL_MINUTES: int = int(os.getenv("MT5_HEALTH_CHECK_INTERVAL_MINUTES", "5"))

    # Verificación de persistencia (señales activas en memoria vs Excel), en minutos.
    PERSISTENCE_CHECK_INTERVAL_MINUTES: int = int(os.getenv("PERSISTENCE_CHECK_INTERVAL_MINUTES", "30"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def model_post_init(self, __context):
        """Set derived paths after initialization."""
        if not self.EXCEL_DIR:
            self.EXCEL_DIR = os.path.join(self.BASE_DIR, "excel")
        if not self.LOGS_DIR:
            self.LOGS_DIR = os.path.join(self.BASE_DIR, "logs")
        if not self.REPORTS_DIR:
            self.REPORTS_DIR = os.path.join(self.BASE_DIR, "reports")
        if not self.CONFIG_DIR:
            self.CONFIG_DIR = os.path.join(self.BASE_DIR, "config")


settings = Settings()
