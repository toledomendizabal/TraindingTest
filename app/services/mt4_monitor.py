"""MetaTrader 4/5 Offline Monitor Service."""
import os
import csv
import asyncio
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from app.core.config import settings


class MT4MonitorService:
    """Service to monitor prices exported by MetaTrader to a CSV file."""

    def __init__(self):
        self.files_path = settings.MT4_FILES_PATH
        self.prices_file = os.path.join(self.files_path, "mt4_prices.csv")
        self._last_prices: Dict[str, float] = {}
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the MT4 monitoring loop."""
        if self._is_running:
            return
        
        self._is_running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"MT4 Offline Monitor started. Watching: {self.prices_file}")

    async def stop(self):
        """Stop the MT4 monitoring loop."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MT4 Offline Monitor stopped")

    async def _monitor_loop(self):
        """Loop to read the MT4 price file every second."""
        while self._is_running:
            try:
                if os.path.exists(self.prices_file):
                    # Use non-blocking file read
                    await self._read_prices()
                else:
                    # Optional: log once that file is missing
                    pass
            except Exception as e:
                logger.error(f"Error reading MT4 prices: {e}")
            
            await asyncio.sleep(1)  # Monitor every second as requested

    async def _read_prices(self):
        """Read prices from CSV file (format: Symbol,Bid,Ask)."""
        try:
            # Refresh path from settings
            self.prices_file = os.path.join(settings.MT4_FILES_PATH, "mt4_prices.csv")
            
            # We use encoding='utf-16' or 'utf-8' depending on how MT4 exports it. 
            # Usually MT4 uses 'utf-16' for Unicode strings in MQL4.
            with open(self.prices_file, mode='r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                new_prices = {}
                for row in reader:
                    symbol = row.get('Symbol', '').replace('/', '')
                    bid = row.get('Bid')
                    if symbol and bid:
                        new_prices[symbol] = float(bid)
                
                if new_prices:
                    self._last_prices.update(new_prices)
                    # Update MarketDataService cache as well
                    from app.services.market_data import market_data_service
                    for symbol, price in new_prices.items():
                        market_data_service._price_cache[symbol] = {
                            "symbol": symbol,
                            "price": price,
                            "timestamp": datetime.now().isoformat(),
                            "source": "MT4_OFFLINE"
                        }
                        market_data_service._last_update[symbol] = datetime.now()
        except Exception as e:
            # Silent fail if file is being written by MT4
            pass

    def get_price(self, asset: str) -> Optional[float]:
        """Get the last read price for an asset."""
        return self._last_prices.get(asset)


# Singleton instance
mt4_monitor = MT4MonitorService()
