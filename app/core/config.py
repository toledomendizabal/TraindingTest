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

    # CAMBIO (fix de raíz, 2026-07-22): fuente única de verdad para el
    # número mínimo de indicadores. Antes este valor estaba duplicado y
    # desincronizado en varios lugares (la constante de clase
    # `SignalEngine.MIN_INDICATORS_FOR_SIGNAL` y varios valores
    # hardcodeados dentro de excel_manager.py). Ahora todos referencian
    # este único valor.
    #
    # CAMBIO (a pedido explícito del usuario, 2026-07-22): bajado a 4.
    # "Los indicadores podrían ser menos pero que sean más contundentes":
    # se reduce la cantidad exigida, mientras que en indicators.py se
    # reintrodujo un umbral de score ponderado (MIN_SCORE_RATIO) que
    # exige que los indicadores confirmando aporten peso real (ej. el
    # bloque de tendencia EMA200/50 o MACD), no cualquier combinación de
    # osciladores débiles.
    MIN_INDICATORS_FOR_SIGNAL: int = 4

    # Umbral de score ponderado mínimo, como fracción del score máximo
    # posible (19.0 con los 18 indicadores habilitados por defecto).
    # Calibrado con simulación de mercado (600 escenarios sintéticos)
    # para que, junto con MIN_INDICATORS_FOR_SIGNAL=4, produzca una tasa
    # de señales razonable (~10-15%). Ver indicators.py::evaluate_signals.
    MIN_SCORE_RATIO: float = 0.35

    # CAMBIO (implementación del documento "4 Estrategias de Trading
    # Multi-Timeframe", 2026-07-23): interruptor para activar la
    # generación de señales vía las 4 estrategias del documento
    # (TREND_MTF, BREAKOUT_VOLUME, REVERSAL_ZONES, SCALPING_TRIPLE),
    # ADEMÁS del motor genérico de 18 indicadores ya existente. Por
    # defecto deshabilitado -- probar primero las recomendaciones vía
    # /api/strategies/recommendations antes de activar señales en vivo.
    STRATEGY_MODE_ENABLED: bool = os.getenv("STRATEGY_MODE_ENABLED", "false").lower() == "true"

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
    # CAMBIO (a pedido explícito del usuario, 2026-07-22): "operaciones
    # 1:3" -- se vuelve a la estructura clásica de riesgo:recompensa
    # completa (arriesgar 1R para buscar 3R en el objetivo final), después
    # de que el experimento con TP1 más cercano (0.7R, luego 0.85R)
    # confirmó en datos reales que la ganancia asegurada en breakeven
    # quedaba muy por debajo de una pérdida por SL (ver análisis
    # 2026-07-22 anterior). TP1 vuelve a 1.0R: tocar el primer objetivo
    # ahora vale, como mínimo, lo mismo en R que una pérdida por SL sobre
    # esa misma fracción del lote.
    TP1_R_MULTIPLE: float = 1.0
    TP2_R_MULTIPLE: float = 2.0
    TP3_R_MULTIPLE: float = 3.0

    # Percentage of the position closed at each take-profit level.
    # Debe sumar 100.
    # CAMBIO (mismo pedido, 2026-07-22): se reduce el cierre en TP1 de 60%
    # a 35% -- deja más lotaje corriendo hacia TP2/TP3 (los objetivos de
    # mayor recompensa), buscando que el profit factor agregado supere
    # 1.5 aun con un win rate moderado (~46%). TP3 (remanente) sube de 20%
    # a 40%.
    TP1_CLOSE_PCT: float = 35.0
    TP2_CLOSE_PCT: float = 25.0
    TP3_CLOSE_PCT: float = 40.0

    # Active Assets
    # CAMBIO (análisis de win rate, datos reales 2026-07-07): USDJPY excluido
    # temporalmente. Fue el peor activo en las 3 sesiones sin excepción
    # (25% WR Londres, 10% NY, 20% Tokyo, sobre 27 señales), con evidencia de
    # que el sistema generó señales SELL contra una tendencia real de
    # fortalecimiento del USD (contexto: demanda de refugio por conflicto en
    # Medio Oriente, USDJPY cerca de máximos de 40 años esa semana). Ver
    # también el nuevo filtro de tendencia macro (_validate_macro_trend) que
    # apunta a la causa de fondo; si ese filtro demuestra ser efectivo en
    # producción, USDJPY puede reincorporarse.
    #
    # CAMBIO (análisis de win rate, datos reales 2026-07-22): USDCHF y
    # USDCAD también excluidos. Con 375 trades reales (2026-07-16 al 21,
    # ya con el filtro de tendencia macro activo), ambos siguen en números
    # rojos de forma consistente:
    #   USDCHF: n=47, 42.6% WR, P/L -$225.30
    #   USDCAD: n=43, 37.2% WR, P/L -$176.40
    # Mientras que los pares donde USD es la divisa COTIZADA (no la base)
    # rinden mejor en el mismo período: EURUSD +$265, AUDUSD +$97, GBPUSD
    # +$67. Con USDJPY, USDCHF y USDCAD ahora fuera, el patrón es
    # consistente: los 3 pares donde USD es la divisa BASE han rendido mal
    # en distintas ventanas de datos, sugiriendo que el filtro de tendencia
    # macro actual no está corrigiendo del todo el problema para ese tipo
    # de par específicamente. Si se investiga y corrige la causa de fondo,
    # ambos pueden reincorporarse.
    ACTIVE_ASSETS: List[str] = [
        "EURUSD", "GBPUSD",
        "NZDUSD", "AUDUSD", "XAUUSD",
        "US30Cash", "US100Cash", "US500Cash", "GER40Cash"
    ]

    # Available Assets (full list)
    AVAILABLE_FOREX: List[str] = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
        "USDCAD", "NZDUSD", "AUDUSD", "EURGBP",
        "EURJPY", "GBPJPY", "AUDCAD", "AUDNZD"
    ]
    AVAILABLE_COMMODITIES: List[str] = [
        "XAUUSD", "XAGUSD", "USOIL", "UKOIL"
    ]
    AVAILABLE_INDICES: List[str] = [
        "US30Cash", "US100Cash", "US500Cash", "GER40Cash",
        "UK100Cash", "JP225Cash", "AU200Cash"
    ]

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
