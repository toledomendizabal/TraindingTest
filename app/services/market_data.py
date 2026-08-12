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
    # CAMBIO (fix, 2026-08-07): se agregaron los 19 activos nuevos de la
    # migración a estrategias (12 cruces + STOXX50Cash + WTI/BRENT/COPPER).
    # Sin esta entrada, `_get_symbol()` devolvía el símbolo tal cual (ej.
    # "EURGBP" en vez de "EUR/GBP"), Twelve Data no lo reconocía, y
    # get_time_series() fallaba en silencio para los 19 -> "sin datos
    # históricos" en el 100% de los ciclos (confirmado con los logs reales
    # del 2026-08-07: 103/103 ciclos fallidos para cada uno de estos 19).
    # OJO: WTI, BRENT, COPPER y los índices dependen del plan de Twelve
    # Data contratado (el plan gratuito no siempre incluye commodities/
    # índices) -- confirma con una llamada de prueba si tu plan los cubre.
    # Si tu bróker ya exporta estos símbolos por archivo MT4/MT5 (ver nota
    # de Market Watch en DIAGNOSTICO_MT5.md), Twelve Data ni se usa para
    # ellos: el archivo MT4/MT5 tiene prioridad y esto solo es un respaldo.
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
        # --- Nuevos: cruces de divisas (fila 3 de la tabla) ---
        "EURGBP": "EUR/GBP",
        "EURJPY": "EUR/JPY",
        "EURCHF": "EUR/CHF",
        "GBPJPY": "GBP/JPY",
        "CHFJPY": "CHF/JPY",
        "AUDJPY": "AUD/JPY",
        "CADJPY": "CAD/JPY",
        "NZDJPY": "NZD/JPY",
        "AUDNZD": "AUD/NZD",
        "AUDCHF": "AUD/CHF",
        "GBPCHF": "GBP/CHF",
        "CADCHF": "CAD/CHF",
        # --- Nuevo: índice (fila 4) -- verificar disponibilidad en tu plan ---
        "STOXX50Cash": "STOXX50E",
        # --- Nuevos: metales/materias primas (fila 5) -- verificar plan ---
        "WTI": "WTI/USD",
        "BRENT": "BRENT/USD",
        "COPPER": "XCU/USD",
    }

    def __init__(self):
        self.api_key = settings.TWELVE_DATA_API_KEY
        self._client: Optional[httpx.AsyncClient] = None
        self._price_cache: Dict[str, Dict] = {}
        self._history_cache: Dict[str, pd.DataFrame] = {} # New history cache
        self._last_update: Dict[str, datetime] = {}
        self._request_times: List[float] = []
        self._max_requests_per_minute = 7
        # CAMBIO (fix, 2026-08-10): control de crédito diario de Twelve
        # Data. Se detectó en logs reales que, con 19 activos sin archivo
        # MT4 disponible, cada ciclo de análisis llamaba a Twelve Data para
        # los 19 -- SIN throttling entre intentos fallidos (el cache de 5
        # min de arriba solo aplica a símbolos que YA tuvieron éxito
        # alguna vez). Resultado real observado: 800 créditos/día del plan
        # agotados a las 08:48 UTC (mismo día, apenas ~40 min después del
        # arranque), dejando sin datos incluso a activos que antes SÍ
        # funcionaban (ej. USDJPY) por el resto del día.
        # `_failed_lookup_at`: cooldown por símbolo tras un intento fallido
        # (no repetir antes de FAILED_LOOKUP_COOLDOWN_SECONDS).
        # `_quota_exhausted_until`: cuando Twelve Data responde "run out of
        # API credits" (HTTP 429), se deja de llamar por completo hasta
        # este instante (por defecto, hasta la medianoche UTC siguiente,
        # cuando el plan gratuito renueva el crédito) en vez de seguir
        # intentando en cada ciclo sin sentido.
        self._failed_lookup_at: Dict[str, datetime] = {}
        self.FAILED_LOOKUP_COOLDOWN_SECONDS = 600  # 10 minutos
        self._quota_exhausted_until: Optional[datetime] = None
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

    def _candidate_mt_symbols(self, asset: str) -> List[str]:
        """
        Lista de nombres candidatos a probar para archivos MT4/MT5, en
        orden de prioridad:
        1. Alias explícito del bróker (settings.MT_SYMBOL_ALIASES).
        2. Nombre "limpio" por defecto (sin '/', sin 'CASH').
        3. El símbolo tal cual, sin limpiar (por si el bróker no usa el
           sufijo "Cash" para índices, ej. archivo "history_STOXX50.csv"
           en vez de "history_STOXX50Cash.csv").
        CAMBIO (fix, 2026-08-07): antes solo se probaba la opción 2, lo que
        rompía cualquier activo cuyo bróker use un nombre distinto (muy
        común en índices/materias primas: WTI/BRENT/COPPER/STOXX50 varían
        bastante entre brokers, a diferencia de los pares de divisas).
        """
        alias = settings.MT_SYMBOL_ALIASES.get(asset) if hasattr(settings, "MT_SYMBOL_ALIASES") else None
        clean = asset.upper().replace("/", "").replace("\\", "").replace("CASH", "")
        candidates = []
        if alias:
            candidates.append(alias.upper().replace("/", "").replace("\\", ""))
        candidates.append(clean)
        if clean != asset.upper():
            candidates.append(asset.upper().replace("/", "").replace("\\", ""))
        # Elimina duplicados preservando el orden
        seen = set()
        result = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    def _find_mt_file_by_prefix(self, prefix: str) -> Optional[str]:
        """
        Última opción: si ningún nombre candidato exacto coincide, busca en
        el directorio de archivos comunes de MT4/MT5 algún archivo
        `history_<algo que empiece con prefix>` -- cubre sufijos de bróker
        que no anticipamos (ej. "WTIUSD", "WTI.a", "WTIcash").
        """
        try:
            if not settings.MT4_FILES_PATH or not os.path.isdir(settings.MT4_FILES_PATH):
                return None
            target = f"HISTORY_{prefix.upper()}"
            for fname in os.listdir(settings.MT4_FILES_PATH):
                if fname.upper().startswith(target):
                    return fname
        except Exception:
            pass
        return None

    def _get_mt4_price(self, asset: str) -> Optional[Dict]:
        """Try to get price from MT4/MT5 common files."""
        try:
            if not settings.MT4_FILES_PATH:
                return None
            prices_file = os.path.join(settings.MT4_FILES_PATH, "mt4_prices.csv")
            if not os.path.exists(prices_file):
                return None

            candidates = self._candidate_mt_symbols(asset)

            with open(prices_file, mode='r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get('Symbol', '').upper().replace("/", "").replace("CASH", "")
                    if symbol in candidates:
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
        """
        Get current price prioritizing MT4 then API.

        CAMBIO CRÍTICO (fix, 2026-08-12 -- "las operaciones no se están
        cerrando"): este método NO tenía el mismo cortacircuito de cuota
        diaria ni el cooldown por símbolo que se agregó a
        `get_time_series()` el 2026-08-10. La diferencia es crítica porque
        `position_monitor._check_positions()` llama a `get_price()` en un
        LOOP DE 1 SEGUNDO para cada señal activa -- si un activo sin
        archivo MT4 (los 19 nuevos, mientras no se agreguen a Market
        Watch) llega aquí, `_wait_for_rate_limit()` puede bloquear hasta
        ~60s esperando un cupo, y lo hace dentro de `self._rate_lock`,
        que es EL MISMO lock que usa `get_time_series()`. Con varias
        señales activas en activos sin MT4, el monitor de posiciones podía
        quedarse minutos enteros esperando turno de rate-limit -- durante
        ese tiempo, NINGUNA posición (ni siquiera las de activos que sí
        tienen datos) se evalúa contra su SL/TP, así que no se cierran a
        tiempo aunque el precio ya lo haya alcanzado hace rato. Y una vez
        agotado el crédito diario (confirmado en logs anteriores: ~800
        créditos consumidos a media mañana), esto se repetía cada segundo
        sin ningún corte, indefinidamente.

        Se aplica aquí el mismo mecanismo que en `get_time_series()`:
        cooldown por símbolo tras un fallo reciente + corte total si ya se
        agotó el crédito diario, ANTES de siquiera intentar el rate
        limiter -- así el monitor de posiciones no se traba esperando un
        precio que muy probablemente no va a llegar.
        """
        mt4_price = self._get_mt4_price(asset)
        if mt4_price:
            self._price_cache[asset] = mt4_price
            self._last_update[asset] = datetime.now()
            return mt4_price

        cached = self.get_cached_price(asset)
        if cached:
            return cached

        price_cache_key = f"{asset}_price"
        now = datetime.now()

        if self._quota_exhausted_until and now < self._quota_exhausted_until:
            logger.debug(f"[TWELVE_DATA] Crédito diario agotado hasta {self._quota_exhausted_until.isoformat()} -- se omite get_price para {asset}.")
            return self._price_cache.get(asset)

        last_failed = self._failed_lookup_at.get(price_cache_key)
        if last_failed and (now - last_failed).total_seconds() < self.FAILED_LOOKUP_COOLDOWN_SECONDS:
            logger.debug(f"[TWELVE_DATA] {asset} (price): en cooldown tras fallo reciente, se omite este ciclo.")
            return self._price_cache.get(asset)

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
                else:
                    logger.warning(f"[TWELVE_DATA] {asset} ({symbol}) price: respuesta sin 'price' -- {data.get('message', data)}")
                    self._failed_lookup_at[price_cache_key] = now
            elif response.status_code == 429:
                body_text = response.text[:300]
                logger.warning(f"[TWELVE_DATA] {asset} ({symbol}) price: HTTP 429 -- {body_text}")
                self._failed_lookup_at[price_cache_key] = now
                if "run out of api credits" in body_text.lower() or "credits for the day" in body_text.lower():
                    tomorrow_utc = (datetime.utcnow() + pd.Timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                    self._quota_exhausted_until = tomorrow_utc
                    logger.error(f"[TWELVE_DATA] Crédito diario agotado -- se suspenden TODAS las llamadas (precio e historial) hasta {tomorrow_utc.isoformat()} UTC.")
            else:
                logger.warning(f"[TWELVE_DATA] {asset} ({symbol}) price: HTTP {response.status_code} -- {response.text[:200]}")
                self._failed_lookup_at[price_cache_key] = now

            return self._price_cache.get(asset)
        except Exception as e:
            logger.error(f"API price failed for {asset}: {e}")
            self._failed_lookup_at[price_cache_key] = now
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
                # CAMBIO (fix, 2026-08-07): antes solo se probaba UN nombre
                # "limpio" (asset sin '/', sin 'CASH'). Se amplía a una
                # lista de candidatos (alias de bróker configurado + nombre
                # limpio + símbolo tal cual) y, si ninguno coincide
                # exactamente, se busca por prefijo en el directorio -- ver
                # `_candidate_mt_symbols` / `_find_mt_file_by_prefix`.
                history_file = None
                for clean_symbol in self._candidate_mt_symbols(asset):
                    candidate = os.path.join(settings.MT4_FILES_PATH, f"history_{clean_symbol}_{interval}.csv")
                    if os.path.exists(candidate):
                        history_file = candidate
                        break
                    candidate = os.path.join(settings.MT4_FILES_PATH, f"history_{clean_symbol}.csv")
                    if os.path.exists(candidate):
                        history_file = candidate
                        break
                if history_file is None:
                    by_prefix = self._find_mt_file_by_prefix(self._candidate_mt_symbols(asset)[0])
                    if by_prefix:
                        history_file = os.path.join(settings.MT4_FILES_PATH, by_prefix)
                        logger.info(f"[MT_SYMBOL_MATCH] {asset}: no hubo coincidencia exacta, se usó '{by_prefix}' por prefijo.")

                if history_file and os.path.exists(history_file):
                    try:
                        df = pd.read_csv(history_file)
                    except pd.errors.EmptyDataError:
                        # CAMBIO (fix, 2026-08-10): el EA (PriceExporter.mq5)
                        # reescribe este archivo periódicamente; si Python lo
                        # lee justo en ese instante puede encontrarlo vacío
                        # por una fracción de segundo. Esto NO es un error
                        # real (el archivo se repuebla en el próximo ciclo
                        # del EA) -- se registra como DEBUG y se sigue a
                        # Twelve Data solo para ESTE ciclo, en vez de un
                        # WARNING que aparenta ser un problema permanente.
                        # Confirmado en log real: "Failed to read MT4
                        # history for USDJPY: No columns to parse from file"
                        # justo en un activo que normalmente sí funciona.
                        logger.debug(f"[MT_DEBUG] {asset}: archivo de historial encontrado pero vacío en este instante (el EA probablemente lo está reescribiendo) -- se reintentará en el siguiente ciclo.")
                        df = None
                    if df is not None:
                        df["datetime"] = pd.to_datetime(df["datetime"])
                        df = df.sort_values("datetime").reset_index(drop=True)
                        for col in ["open", "high", "low", "close", "volume"]:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                        return df
                else:
                    logger.debug(
                        f"[MT_DEBUG] Ningún archivo de historial encontrado para {asset} "
                        f"(candidatos probados: {self._candidate_mt_symbols(asset)}). "
                        f"Verifica que el símbolo esté agregado en Market Watch de tu terminal, "
                        f"o configura un alias en settings.MT_SYMBOL_ALIASES si tu bróker usa "
                        f"otro nombre. Se intentará Twelve Data como respaldo."
                    )
            except Exception as e:
                logger.warning(f"Failed to read MT4 history for {asset}: {e}")

        # 2. Backup: Twelve Data API with simple cache
        if cache_key in self._history_cache:
            last_upd = self._last_update.get(cache_key)
            if last_upd and (datetime.now() - last_upd).seconds < 300: # 5 min cache
                return self._history_cache[cache_key]

        now = datetime.now()

        # CAMBIO (fix, 2026-08-10): si ya sabemos que se agotó el crédito
        # diario, ni siquiera se intenta -- evita cientos de llamadas 429
        # inútiles por el resto del día (ver __init__ para el contexto).
        if self._quota_exhausted_until and now < self._quota_exhausted_until:
            logger.debug(f"[TWELVE_DATA] Crédito diario agotado hasta {self._quota_exhausted_until.isoformat()} -- se omite la llamada para {asset}.")
            return self._history_cache.get(cache_key)

        # CAMBIO (fix, 2026-08-10): cooldown por símbolo tras un fallo
        # reciente, para no repetir un intento que muy probablemente vuelva
        # a fallar (símbolo no soportado en el plan, etc.) y así conservar
        # crédito para los símbolos que sí puedan resolverse.
        last_failed = self._failed_lookup_at.get(cache_key)
        if last_failed and (now - last_failed).total_seconds() < self.FAILED_LOOKUP_COOLDOWN_SECONDS:
            logger.debug(f"[TWELVE_DATA] {asset}: en cooldown tras fallo reciente ({int((now - last_failed).total_seconds())}s), se omite este ciclo.")
            return self._history_cache.get(cache_key)

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
                else:
                    # CAMBIO (fix, 2026-08-07): antes esto fallaba en
                    # silencio (sin log) cuando Twelve Data respondía 200
                    # pero sin "values" (símbolo no soportado en el plan,
                    # límite de crédito, etc.) -- se agrega log explícito
                    # para poder diagnosticar por qué un activo nunca tiene
                    # datos, en vez de adivinar.
                    logger.warning(f"[TWELVE_DATA] {asset} ({symbol}): respuesta sin 'values' -- {data.get('message', data)}")
                    self._failed_lookup_at[cache_key] = now
            elif response.status_code == 429:
                # CAMBIO (fix, 2026-08-10): distingue "crédito diario
                # agotado" (activa el short-circuit global hasta medianoche
                # UTC) de un simple rate-limit momentáneo (solo cooldown
                # por símbolo). Confirmado con log real: "You have run out
                # of API credits for the day... limit being 800".
                body_text = response.text[:300]
                logger.warning(f"[TWELVE_DATA] {asset} ({symbol}): HTTP 429 -- {body_text}")
                self._failed_lookup_at[cache_key] = now
                if "run out of api credits" in body_text.lower() or "credits for the day" in body_text.lower():
                    tomorrow_utc = (datetime.utcnow() + pd.Timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                    self._quota_exhausted_until = tomorrow_utc
                    logger.error(
                        f"[TWELVE_DATA] Crédito diario agotado -- se suspenden TODAS las llamadas a "
                        f"Twelve Data hasta {tomorrow_utc.isoformat()} UTC. Los activos sin archivo "
                        f"MT4/MT5 no tendrán datos hasta entonces. Considera un plan de pago o revisa "
                        f"cuántos activos realmente necesitan este respaldo (ver DIAGNOSTICO_MT5.md)."
                    )
            else:
                logger.warning(f"[TWELVE_DATA] {asset} ({symbol}): HTTP {response.status_code} -- {response.text[:200]}")
                self._failed_lookup_at[cache_key] = now

            return self._history_cache.get(cache_key)
        except Exception as e:
            logger.error(f"API history failed for {asset}: {e}")
            self._failed_lookup_at[cache_key] = now
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
