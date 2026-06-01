"""Market data service using Twelve Data API."""
import asyncio
import httpx
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from loguru import logger
from app.core.config import settings


class MarketDataService:
    """Service to fetch market data from Twelve Data API."""

    BASE_URL = "https://api.twelvedata.com"

    # Symbol mapping for Twelve Data
    SYMBOL_MAP = {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "USDCHF": "USD/CHF",
        "USDCAD": "USD/CAD",
        "NZDUSD": "NZD/USD",
        "AUDUSD": "AUD/USD",
        "XAUUSD": "XAU/USD",
        "US30Cash": "DJI",
        "US100Cash": "NDX",
        "US500Cash": "SPX",
        "GER40Cash": "DAX",
    }

    TIMEFRAME_MAP = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1day",
    }

    def __init__(self):
        self.api_key = settings.TWELVE_DATA_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
        self._price_cache: Dict[str, Dict] = {}
        self._last_update: Dict[str, datetime] = {}

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_symbol(self, asset: str) -> str:
        """Convert internal symbol to Twelve Data format."""
        return self.SYMBOL_MAP.get(asset, asset)

    async def get_price(self, asset: str) -> Optional[Dict]:
        """Get current price for an asset."""
        try:
            client = await self.get_client()
            symbol = self._get_symbol(asset)

            response = await client.get(
                f"{self.BASE_URL}/price",
                params={
                    "symbol": symbol,
                    "apikey": self.api_key
                }
            )

            if response.status_code == 200:
                data = response.json()
                if "price" in data:
                    price_data = {
                        "symbol": asset,
                        "price": float(data["price"]),
                        "timestamp": datetime.now().isoformat()
                    }
                    self._price_cache[asset] = price_data
                    self._last_update[asset] = datetime.now()
                    return price_data

            logger.warning(f"Failed to get price for {asset}: {response.text}")
            return self._price_cache.get(asset)

        except Exception as e:
            logger.error(f"Error fetching price for {asset}: {e}")
            return self._price_cache.get(asset)

    async def get_time_series(
        self,
        asset: str,
        interval: str = "5m",
        outputsize: int = 200
    ) -> Optional[pd.DataFrame]:
        """Get historical time series data."""
        try:
            client = await self.get_client()
            symbol = self._get_symbol(asset)
            td_interval = self.TIMEFRAME_MAP.get(interval, "5min")

            response = await client.get(
                f"{self.BASE_URL}/time_series",
                params={
                    "symbol": symbol,
                    "interval": td_interval,
                    "outputsize": outputsize,
                    "apikey": self.api_key
                }
            )

            if response.status_code == 200:
                data = response.json()
                if "values" in data:
                    df = pd.DataFrame(data["values"])
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    df = df.sort_values("datetime").reset_index(drop=True)

                    # Convert numeric columns
                    for col in ["open", "high", "low", "close"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                    if "volume" in df.columns:
                        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
                    else:
                        df["volume"] = 0

                    return df

            logger.warning(f"Failed to get time series for {asset}: {response.text}")
            return None

        except Exception as e:
            logger.error(f"Error fetching time series for {asset}: {e}")
            return None

    async def get_multiple_prices(self, assets: List[str]) -> Dict[str, Dict]:
        """Get prices for multiple assets."""
        results = {}
        tasks = [self.get_price(asset) for asset in assets]
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        for asset, price in zip(assets, prices):
            if isinstance(price, dict):
                results[asset] = price
            elif isinstance(price, Exception):
                logger.error(f"Error getting price for {asset}: {price}")

        return results

    def get_current_session(self) -> str:
        """Determine current trading session based on UTC time."""
        now = datetime.utcnow()
        hour = now.hour

        if 0 <= hour < 8:
            return "Tokyo"
        elif 8 <= hour < 13:
            return "London"
        elif 13 <= hour < 22:
            return "NewYork"
        else:
            return "Tokyo"

    def get_cached_price(self, asset: str) -> Optional[Dict]:
        """Get cached price if available and recent."""
        if asset in self._price_cache:
            last_update = self._last_update.get(asset)
            if last_update and (datetime.now() - last_update).seconds < 30:
                return self._price_cache[asset]
        return None


# Singleton instance
market_data_service = MarketDataService()
