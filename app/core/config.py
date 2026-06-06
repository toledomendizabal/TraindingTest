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
    TWELVE_DATA_API_KEY: str = ""

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
    MT4_FILES_PATH: str = "C:\\Users\\USUARIO\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files"
    MT4_SYNC_ENABLED: bool = True

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
