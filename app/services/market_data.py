"""Market data service prioritizing MetaTrader local files with Twelve Data as backup."""
import asyncio
import time
import httpx
import pandas as pd
import os
import csv
from datetime import datetime
from typing import Optional, Dict, List
from loguru import logger
from app.core.config import settings


class MarketDataService:
    """Service to fetch market data prioritizing MT4/MT5 local files."""

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

    def __init__(self):
        self.api_key = settings.TWELVE_DATA_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
        self._price_cache: Dict[str, Dict] = {}
        self._history_cache: Dict[str, pd.DataFrame] = {} # New history cache
        self._last_update: Dict[str, datetime] = {}
        self._request_times: List[float] = []
        self._max_requests_per_minute = 7
        self._rate_lock = asyncio.Lock()
        self._max_cache_size = 100 

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_symbol(self, asset: str) -> str:
        return self.SYMBOL_MAP.get(asset, asset)

    def _get_mt4_price(self, asset: str) -> Optional[Dict]:
        """Try to get price from MT4/MT5 common files."""
        try:
            if not settings.MT4_FILES_PATH:
                return None
            prices_file = os.path.join(settings.MT4_FILES_PATH, "mt4_prices.csv")
            if not os.path.exists(prices_file):
                return None
            
            clean_asset = asset.upper().replace("/", "").replace("CASH", "")
            
            with open(prices_file, mode='r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get('Symbol', '').upper().replace("/", "").replace("CASH", "")
                    if symbol == clean_asset:
                        bid = float(row.get('Bid', 0))
                        ask = float(row.get('Ask', 0))
                        price = (bid + ask) / 2 if ask > 0 else bid
                        
                        return {
                            "symbol": asset,
                            "price": price,
                            "bid": bid,
                            "ask": ask,
                            "timestamp": datetime.now().isoformat(),
                            "source": "MT4"
                        }
        except Exception as e:
            logger.debug(f"MT4 price read failed for {asset}: {e}")
        return None

    async def get_price(self, asset: str) -> Optional[Dict]:
        """Get current price prioritizing MT4 then API."""
        mt4_price = self._get_mt4_price(asset)
        if mt4_price:
            self._price_cache[asset] = mt4_price
            self._last_update[asset] = datetime.now()
            return mt4_price

        cached = self.get_cached_price(asset)
        if cached:
            return cached

        try:
            await self._wait_for_rate_limit()
            client = await self.get_client()
            symbol = self._get_symbol(asset)

            response = await client.get(
                f"{self.BASE_URL}/price",
                params={"symbol": symbol, "apikey": self.api_key}
            )
            
            if response.status_code == 200:
                data = response.json()
                if "price" in data:
                    price_data = {
                        "symbol": asset,
                        "price": float(data["price"]),
                        "timestamp": datetime.now().isoformat(),
                        "source": "API"
                    }
                    self._price_cache[asset] = price_data
                    self._last_update[asset] = datetime.now()
                    return price_data
            
            return self._price_cache.get(asset)
        except Exception as e:
            logger.error(f"API price failed for {asset}: {e}")
            return self._price_cache.get(asset)

    async def get_time_series(
        self,
        asset: str,
        interval: str = "5m",
        outputsize: int = 200
    ) -> Optional[pd.DataFrame]:
        """Get historical data prioritizing MT4 history files."""
        cache_key = f"{asset}_{interval}"
        
        # 1. Try MT4 History File
        if settings.MT4_FILES_PATH:
            try:
                clean_symbol = asset.upper().replace("/", "").replace("\\", "")
                # Handle index naming variations (e.g. US30Cash vs US30)
                if "CASH" in clean_symbol:
                    clean_symbol = clean_symbol.replace("CASH", "")
                
                # Try to find interval-specific file first
                history_file = os.path.join(settings.MT4_FILES_PATH, f"history_{clean_symbol}_{interval}.csv")
                if not os.path.exists(history_file):
                    history_file = os.path.join(settings.MT4_FILES_PATH, f"history_{clean_symbol}.csv")
                
                if os.path.exists(history_file):
                    df = pd.read_csv(history_file)
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    df = df.sort_values("datetime").reset_index(drop=True)
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    return df
                else:
                    logger.debug(f"[MT5_DEBUG] MT4 history file NOT FOUND: {history_file}")
            except Exception as e:
                logger.warning(f"Failed to read MT4 history for {asset}: {e}")

        # 2. Backup: Twelve Data API with simple cache
        if cache_key in self._history_cache:
            last_upd = self._last_update.get(cache_key)
            if last_upd and (datetime.now() - last_upd).seconds < 300: # 5 min cache
                return self._history_cache[cache_key]

        try:
            await self._wait_for_rate_limit()
            client = await self.get_client()
            symbol = self._get_symbol(asset)
            
            td_map = {
                "1m": "1min", 
                "5m": "5min", 
                "15m": "15min", 
                "30m": "30min", 
                "1h": "1h", 
                "4h": "4h", 
                "1d": "1day"
            }
            td_interval = td_map.get(interval, "5min")

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
                    for col in ["open", "high", "low", "close"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    df["volume"] = pd.to_numeric(df.get("volume", 0), errors="coerce")
                    
                    self._history_cache[cache_key] = df
                    self._last_update[cache_key] = datetime.now()
                    return df
            
            return self._history_cache.get(cache_key)
        except Exception as e:
            logger.error(f"API history failed for {asset}: {e}")
            return self._history_cache.get(cache_key)

    async def _wait_for_rate_limit(self):
        async with self._rate_lock:
            now = time.time()
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= self._max_requests_per_minute:
                wait_time = 60 - (now - self._request_times[0]) + 1
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            self._request_times.append(time.time())

    def get_cached_price(self, asset: str) -> Optional[Dict]:
        if asset in self._price_cache:
            last_update = self._last_update.get(asset)
            if last_update and (datetime.now() - last_update).seconds < 30:
                return self._price_cache[asset]
        return None

    def get_current_session(self) -> str:
        """Determine current trading session based on UTC time."""
        now = datetime.utcnow()
        hour = now.hour
        if 0 <= hour < 8: return "Tokyo"
        elif 8 <= hour < 13: return "London"
        elif 13 <= hour < 22: return "NewYork"
        else: return "Tokyo"

market_data_service = MarketDataService()
