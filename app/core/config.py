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
    SESSION_START_HOUR_UTC: int = 6   # Antes de apertura de Londres
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
    TP1_R_MULTIPLE: float = 1.0
    TP2_R_MULTIPLE: float = 2.0
    TP3_R_MULTIPLE: float = 3.0

    # Percentage of the position closed at each take-profit level.
    # Debe sumar 100.
    TP1_CLOSE_PCT: float = 50.0
    TP2_CLOSE_PCT: float = 25.0
    TP3_CLOSE_PCT: float = 25.0

    # Active Assets
    ACTIVE_ASSETS: List[str] = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
        "USDCAD", "NZDUSD", "AUDUSD", "XAUUSD",
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
