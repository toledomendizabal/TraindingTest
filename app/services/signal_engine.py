"""Signal generation engine with advanced risk management and Fibonacci levels."""
import uuid
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from loguru import logger
from app.core.config import settings
from app.models.signal import Signal, SignalDirection, SignalStatus
from app.models.asset import Asset, ASSET_CATALOG
from app.services.market_data import market_data_service
from app.services.indicators import indicator_service
from app.services.excel_manager import excel_manager


class SignalEngine:
    """Engine for generating trading signals based on 18 indicators confluence."""

    MIN_INDICATORS_FOR_SIGNAL = 6
    ANALYSIS_TIMEFRAMES = ["30m", "1h"]
    SIGNAL_TIMEFRAME = "5m"
    ATR_SL_MULTIPLIER = 2.0 # CAMBIO 17: Centralized ATR SL multiplier

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL
        self._load_active_signals()

    def _load_active_signals(self):
        """Load active signals from Excel on startup."""
        try:
            active_list = excel_manager.get_active_signals()
            for s_data in active_list:
                try:
                    # Convert dict to Signal model
                    signal = Signal(
                        id=s_data["id"],
                        asset=s_data["asset"],
                        direction=SignalDirection(s_data["direction"]),
                        entry_price=float(s_data["entry_price"]),
                        stop_loss=float(s_data["stop_loss"]),
                        take_profit_1=float(s_data["take_profit_1"]),
                        take_profit_2=float(s_data["take_profit_2"]),
                        take_profit_3=float(s_data["take_profit_3"]),
                        sl_pips=float(s_data["sl_pips"]),
                        tp1_pips=float(s_data["tp1_pips"]),
                        tp2_pips=float(s_data["tp2_pips"]),
                        tp3_pips=float(s_data["tp3_pips"]),
                        lot_size=float(s_data["lot_size"]),
                        timeframe=s_data["timeframe"],
                        indicators_met=int(s_data["indicators_met"]),
                        total_indicators=18,
                        score=float(s_data["score"]),
                        status=SignalStatus.ACTIVE,
                        session=s_data["session"],
                        created_at=datetime.fromisoformat(s_data["created_at"]) if s_data["created_at"] else datetime.now(),
                        indicators_detail=[]
                    )
                    self.active_signals[signal.id] = signal
                except Exception as e:
                    logger.error(f"Error parsing signal {s_data.get('id')}: {e}")
            
            if self.active_signals:
                logger.info(f"Loaded {len(self.active_signals)} active signals from Excel")
        except Exception as e:
            logger.error(f"Error loading active signals: {e}")

    async def analyze_asset(self, asset: str) -> Optional[Signal]:
        try:
            if self._has_active_signal(asset):
                logger.debug(f"[DEBUG] Active signal found for {asset}. Skipping new signal generation.")
                return None

            df = await market_data_service.get_time_series(
                asset, interval=self.SIGNAL_TIMEFRAME, outputsize=200
            )

            if df is None or df.empty:
                logger.debug(f"[DEBUG] No historical data (df) for {asset}. Skipping signal evaluation.")
                return None

            # CAMBIO 16: Filtro de spread máximo
            price_data = await market_data_service.get_price(asset)
            spread = 0.0
            if price_data and "ask" in price_data and "bid" in price_data:
                spread = abs(price_data["ask"] - price_data["bid"])
            else:
                # If ask/bid not available, assume spread is 0 to avoid blocking signals unnecessarily
                # unless it's a critical error, in which case spread remains 0.0
                spread = 0.0

            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            current_spread_pips = round(spread / pip_size, 1)

            max_spread_pips = {
                "XAU": 25.0, # Aumentado significativamente para evitar bloqueos por spread en Oro
                "US30": 15.0,
                "US100": 15.0,
                "US500": 15.0,
                "DAX": 15.0,
                "GER40": 15.0,
                "DJI": 15.0,
                "NDX": 15.0,
                "SPX": 15.0,
            }.get(asset.upper().split("USD")[0], 5.0) # Default 5.0 for FX pairs

            if current_spread_pips > max_spread_pips:
                logger.info(f"Signal for {asset} rejected: Spread ({current_spread_pips} pips) exceeds max allowed ({max_spread_pips} pips).")
                logger.debug(f"[DEBUG] Skipping {asset}: Spread too high ({current_spread_pips} pips).")
                return None

            indicators = indicator_service.calculate_all(df)
            if not indicators:
                logger.debug(f"[DEBUG] No indicators calculated for {asset}. Skipping signal evaluation.")
                return None

            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)
            if direction == "NEUTRAL" or indicators_met < self.MIN_INDICATORS_FOR_SIGNAL:
                logger.debug(f"[DEBUG] Skipping {asset}: Indicator evaluation NEUTRAL or insufficient indicators met ({indicators_met}/{self.MIN_INDICATORS_FOR_SIGNAL}).")
                return None

            # Session Filter: Only trade during London or NY sessions (approx 07:00 - 17:00 UTC)
            # This reduces false breakouts during Asian session consolidation
            current_hour = datetime.utcnow().hour
            # CAMBIO 14: Filtro de sesión - Ventana temporal 07:00-12:00 y 13:00-17:00 UTC
            # CAMBIO 15: Filtro de sesión - Fallo silencioso (hardcodeado)
            # Flexibilizar el filtro de sesión: 06:00 - 18:00 UTC
            if not (6 <= current_hour < 18):
                logger.info(f"Signal for {asset} rejected: Outside institutional sessions (London/NY). Current hour: {current_hour} UTC")
                logger.debug(f"[DEBUG] Skipping {asset}: Outside trading session.")
                return None

            # Validate with structural timeframe
            structural_confirmed = await self._validate_structural(asset, direction)
            if not structural_confirmed:
                logger.info(f"Signal for {asset} rejected: Failed structural validation.")
                logger.debug(f"[DEBUG] Skipping {asset}: Structural validation failed.")
                return None

            # Generate signal
            current_price = df["close"].iloc[-1]
            atr_value = indicators.get("ATR", 0)
            


            signal = await self._create_signal(
                asset=asset,
                direction=SignalDirection(direction),
                entry_price=current_price,
                atr=atr_value if atr_value else current_price * 0.001,
                indicators_met=indicators_met,
                details=details,
                spread=spread, # Pass the calculated spread
                df=df
            )

            if signal:
                self.active_signals[signal.id] = signal
                await excel_manager.register_signal(signal)
                logger.debug(f"[DEBUG] Signal successfully generated and registered for {asset}. ID: {signal.id}")
                try:
                    from app.services.telegram_service import telegram_service
                    await telegram_service.send_signal_notification(signal)
                except Exception as e:
                    logger.error(f"Telegram error: {e}")

            return signal
            logger.debug(f"[DEBUG] Signal evaluation for {asset} completed.")
        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            return None

    async def _create_signal(
        self,
        asset: str,
        direction: SignalDirection,
        entry_price: float,
        atr: float,
        indicators_met: int,
        details: List[str],
        spread: float = 0.0,
        df: Optional[pd.DataFrame] = None
    ) -> Optional[Signal]:
        try:
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            contract_size = pip_info["contract_size"]
            quote_currency = pip_info["quote_currency"]

            # 1. Calculate Stop Loss using ATR (ATR_SL_MULTIPLIER x ATR) as a baseline
            sl_distance = atr * self.ATR_SL_MULTIPLIER

            # Advanced SL adjustment based on SMC structures
            # Look for recent swing high/low or FVG that offers better protection
            if df is not None:
                last_candle_close = df["close"].iloc[-1]
                last_candle_low = df["low"].iloc[-1]
                last_candle_high = df["high"].iloc[-1]

                # Get FVG and Liquidity from indicator_service (already calculated in analyze_asset)
                fvgs = indicator_service.detect_fvg(df)
                liquidity = indicator_service.detect_liquidity(df)

                if direction == SignalDirection.BUY:
                    # For BUY, look for nearest bullish FVG below entry or recent swing low
                    potential_sls = []
                    # Add ATR-based SL
                    potential_sls.append(entry_price - sl_distance)

                    # Add bullish FVG lower bounds below entry
                    for fvg in fvgs:
                        if fvg["type"] == "BULLISH" and fvg["price"] < entry_price:
                            potential_sls.append(fvg["price"] - (pip_size * 5)) # 5 pips below FVG for buffer
                    
                    # Add recent swing lows (SSL zones) below entry
                    for ssl_zone in liquidity["SSL"]:
                        if ssl_zone < entry_price:
                            potential_sls.append(ssl_zone - (pip_size * 5)) # 5 pips below SSL for buffer

                    # CAMBIO 18: BUG en lógica de Stop Loss con SMC (CRÍTICO)
                    # Elegir el SL más cercano al precio de entrada (el más alto para BUY)
                    if potential_sls:
                        # Convertir los precios de SL a distancias desde el entry_price
                        sl_distances_from_smc = [entry_price - sl for sl in potential_sls if sl < entry_price]
                        if sl_distances_from_smc:
                            # Elegir la menor distancia (SL más cercano al entry) para que sea el más alto en precio
                            sl_distance_smc = min(sl_distances_from_smc)
                            # Asegurar que el SL SMC sea al menos 1.5x ATR (o el ATR_SL_MULTIPLIER actual)
                            if sl_distance_smc > (atr * self.ATR_SL_MULTIPLIER): # Usar ATR_SL_MULTIPLIER como mínimo para SMC SL
                                sl_distance = sl_distance_smc
                            else:
                                sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si SMC SL es muy pequeño
                        else:
                            sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si no hay SMC SL válidos
                    else:
                        sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si no hay SMC SL
                    stop_loss = entry_price - sl_distance

                else: # SELL direction
                    # For SELL, look for nearest bearish FVG above entry or recent swing high
                    potential_sls = []
                    # Add ATR-based SL
                    potential_sls.append(entry_price + sl_distance)

                    # Add bearish FVG upper bounds above entry
                    for fvg in fvgs:
                        if fvg["type"] == "BEARISH" and fvg["price"] > entry_price:
                            potential_sls.append(fvg["price"] + (pip_size * 5)) # 5 pips above FVG for buffer

                    # Add recent swing highs (BSL zones) above entry
                    for bsl_zone in liquidity["BSL"]:
                        if bsl_zone > entry_price:
                            potential_sls.append(bsl_zone + (pip_size * 5)) # 5 pips above BSL for buffer

                    # CAMBIO 18: BUG en lógica de Stop Loss con SMC (CRÍTICO)
                    # Elegir el SL más cercano al precio de entrada (el más bajo para SELL)
                    if potential_sls:
                        # Convertir los precios de SL a distancias desde el entry_price
                        sl_distances_from_smc = [sl - entry_price for sl in potential_sls if sl > entry_price]
                        if sl_distances_from_smc:
                            # Elegir la menor distancia (SL más cercano al entry) para que sea el más bajo en precio
                            sl_distance_smc = min(sl_distances_from_smc)
                            # Asegurar que el SL SMC sea al menos 1.5x ATR (o el ATR_SL_MULTIPLIER actual)
                            if sl_distance_smc > (atr * self.ATR_SL_MULTIPLIER): # Usar ATR_SL_MULTIPLIER como mínimo para SMC SL
                                sl_distance = sl_distance_smc
                            else:
                                sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si SMC SL es muy pequeño
                        else:
                            sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si no hay SMC SL válidos
                    else:
                        sl_distance = atr * self.ATR_SL_MULTIPLIER # Fallback a ATR si no hay SMC SL
                    stop_loss = entry_price + sl_distance



            # --- Apply Minimum Stop Loss Limits ---
            
            # --- Apply Minimum Stop Loss Limits ---
            is_index_or_gold = any(x in asset.upper() for x in ["XAU", "US30", "US100", "US500", "DAX", "DJI", "NDX", "SPX"])
            is_ger40 = any(x in asset.upper() for x in ["GER40", "DAX"])
            is_gold = "XAU" in asset.upper()
            
            min_sl_pips = 300 if (is_index_or_gold and not is_ger40) else 6
            current_sl_pips = sl_distance / pip_size
            
            if current_sl_pips < min_sl_pips:
                sl_distance = min_sl_pips * pip_size

            # 2. Advanced SMC Targets: Fibonacci + FVG + Liquidity
            fvgs = indicator_service.detect_fvg(df)
            liquidity = indicator_service.detect_liquidity(df)
            
            if direction == SignalDirection.BUY:
                stop_loss = entry_price - sl_distance
                
                # Default Fibonacci targets (CAMBIO 19 y 20)
                tp1 = entry_price + (sl_distance * 1.8)
                tp2 = entry_price + (sl_distance * 3.5)
                tp3 = entry_price + (sl_distance * 6.0) # Reduced TP3 as well for realism
                
                # Adjust TP with Bearish FVGs (Resistance) and BSL (Liquidity)
                bearish_fvgs = [f["price"] for f in fvgs if f["type"] == "BEARISH" and f["price"] > entry_price]
                bsl_zones = [p for p in liquidity["BSL"] if p > entry_price]
                
                if bearish_fvgs:
                    tp1 = min(tp1, min(bearish_fvgs))
                if bsl_zones:
                    tp3 = max(tp3, max(bsl_zones))
            else:
                stop_loss = entry_price + sl_distance
                
                # Default Fibonacci targets (CAMBIO 19 y 20)
                tp1 = entry_price - (sl_distance * 1.8)
                tp2 = entry_price - (sl_distance * 3.5)
                tp3 = entry_price - (sl_distance * 6.0) # Reduced TP3 as well for realism
                
                # Adjust TP with Bullish FVGs (Support) and SSL (Liquidity)
                bullish_fvgs = [f["price"] for f in fvgs if f["type"] == "BULLISH" and f["price"] < entry_price]
                ssl_zones = [p for p in liquidity["SSL"] if p < entry_price]
                
                if bullish_fvgs:
                    tp1 = max(tp1, max(bullish_fvgs))
                if ssl_zones:
                    tp3 = min(tp3, min(ssl_zones))

            # 3. Dynamic SMC Risk Management
            capital = settings.INITIAL_CAPITAL
            
            # Base risk: 0.75% for Gold, 0.3% for others (using settings)
            base_risk_pct = 0.75 if is_gold else settings.RISK_PERCENTAGE
            
            # Quality adjustment: Boost risk if signal is high quality (Confluence with FVG/Liquidity)
            quality_multiplier = 1.0
            
            # Check for FVG Confluence near entry (within 0.1% of entry price)
            entry_fvgs = [f for f in fvgs if abs(f["price"] - entry_price) / entry_price < 0.001]
            fvg_confluence = False
            if entry_fvgs:
                quality_multiplier += 0.25 # +25% confidence
                fvg_confluence = True
                
            # Check for Liquidity Sweep (Signal occurring after a sweep in the last 10 candles)
            liquidity_sweep = False
            if df is not None:
                try:
                    if direction == SignalDirection.BUY:
                        recent_lows = df["low"].iloc[-10:].min()
                        if any(ssl < recent_lows for ssl in liquidity["SSL"]):
                            quality_multiplier += 0.25 # +25% confidence
                            liquidity_sweep = True
                    else:
                        recent_highs = df["high"].iloc[-10:].max()
                        if any(bsl > recent_highs for bsl in liquidity["BSL"]):
                            quality_multiplier += 0.25 # +25% confidence
                            liquidity_sweep = True
                except Exception as e:
                    logger.error(f"Error checking liquidity sweep: {e}")

            final_risk_pct = (base_risk_pct / 100) * quality_multiplier
            risk_amount_usd = capital * final_risk_pct

            # Currency Conversion (Quote to USD)
            quote_to_usd_rate = 1.0
            if quote_currency == "EUR":
                eurusd_data = await market_data_service.get_price("EURUSD")
                if eurusd_data:
                    quote_to_usd_rate = eurusd_data["price"]
            elif quote_currency == "JPY":
                usdjpy_data = await market_data_service.get_price("USDJPY")
                if usdjpy_data:
                    quote_to_usd_rate = 1.0 / usdjpy_data["price"]

            # Pip value in USD
            pip_value_usd = pip_info["pip_value"] * quote_to_usd_rate
            pip_value_per_lot = pip_value_usd * contract_size
            
            sl_pips = sl_distance / pip_size
            
            if pip_value_per_lot > 0 and sl_pips > 0:
                lot_size = risk_amount_usd / (sl_pips * pip_value_per_lot)
            else:
                lot_size = 0.01

            # Round lot size to 2 decimals
            lot_size = round(max(0.01, min(lot_size, 100.0)), 2)

            score = (indicators_met / 18) * 100

            return Signal(
                id=str(uuid.uuid4())[:8],
                asset=asset,
                direction=direction,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),
                take_profit_1=round(tp1, 5),
                take_profit_2=round(tp2, 5),
                take_profit_3=round(tp3, 5),
                sl_pips=round(sl_pips, 1),
                tp1_pips=round(abs(tp1 - entry_price) / pip_size, 1),
                tp2_pips=round(abs(tp2 - entry_price) / pip_size, 1),
                tp3_pips=round(abs(tp3 - entry_price) / pip_size, 1),
                lot_size=lot_size,
                timeframe=self.SIGNAL_TIMEFRAME,
                indicators_met=indicators_met,
                total_indicators=18,
                score=round(score, 1),
                status=SignalStatus.ACTIVE,
                session=market_data_service.get_current_session(),
                created_at=datetime.now(),
                entry_hour=datetime.now().strftime("%H:%M"),
                entry_spread=round(spread / pip_size, 1),
                entry_atr=round(atr / pip_size, 1),
                smc_quality=round(quality_multiplier, 2),
                fvg_confluence=fvg_confluence,
                liquidity_sweep=liquidity_sweep,
                indicators_detail=details
            )
        except Exception as e:
            logger.error(f"Signal creation error for {asset}: {e}")
            return None

    async def analyze_all_assets(self) -> List[Signal]:
        signals = []
        for asset in settings.ACTIVE_ASSETS:
            signal = await self.analyze_asset(asset)
            if signal:
                signals.append(signal)
        return signals

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        try:
            # Special Strategy for XAUUSD
            if "XAU" in asset.upper():
                df_5m = await market_data_service.get_time_series(asset, interval="5m", outputsize=300)
                if df_5m is not None and not df_5m.empty:
                    # 1. EMA 50 > EMA 200
                    ema50 = df_5m["close"].ewm(span=50, adjust=False).mean()
                    ema200 = df_5m["close"].ewm(span=200, adjust=False).mean()
                    
                    # Flexibilizar EMA para XAUUSD: solo precio por encima/debajo de EMA200
                    if direction == "BUY" and not (df_5m["close"].iloc[-1] > ema200.iloc[-1]):
                        return False
                    # Flexibilizar EMA para XAUUSD: solo precio por encima/debajo de EMA200
                    if direction == "SELL" and not (df_5m["close"].iloc[-1] < ema200.iloc[-1]):
                        return False
                    
                    # 2. ADX > 25 (Trend strength)
                    # Simple ADX calculation or from indicators service
                    from app.services.indicators import indicator_service
                    ind = indicator_service.calculate_all(df_5m)
                    adx_data = ind.get("ADX_DMI") or {}
                    # Flexibilizar ADX para XAUUSD
                    if adx_data.get("adx", 0) <= 20: # Reducir umbral de ADX
                        return False

                    # 3. MACD aligned
                    macd_data = ind.get("MACD") or {}
                    macd = macd_data.get("macd", 0)
                    signal_macd = macd_data.get("signal", 0)
                    # Flexibilizar MACD para XAUUSD
                    if direction == "BUY" and not (macd > signal_macd):
                        return False
                    # Flexibilizar MACD para XAUUSD
                    if direction == "SELL" and not (macd < signal_macd):
                        return False
                    
                    # 4. ATR increasing (Volatilidad creciente)
                    atr = df_5m["high"] - df_5m["low"] # simplified
                    atr_sma = atr.rolling(window=14).mean()
                    # Eliminar filtro de ATR creciente para XAUUSD (demasiado restrictivo)
                    # if atr_sma.iloc[-1] <= atr_sma.iloc[-2]:
                    #     return False
                    pass # No return, allow to pass

            # General structural validation (Trend Filter con al menos
            # 1 de 2 timeframes mayores confirmando, no ambos obligatorios)
            confirmations = 0
            timeframes_evaluated = 0

            for tf in self.ANALYSIS_TIMEFRAMES:
                df = await market_data_service.get_time_series(asset, interval=tf, outputsize=100)
                if df is None or df.empty:
                    continue

                timeframes_evaluated += 1

                ema200 = df["close"].ewm(span=200, adjust=False).mean()
                ema50 = df["close"].ewm(span=50, adjust=False).mean()

                if len(ema200) > 0 and len(ema50) > 0:
                    current_price = df["close"].iloc[-1]

                    if direction == "BUY":
                        if current_price > ema200.iloc[-1]:
                            confirmations += 1
                    if direction == "SELL":
                        if current_price < ema200.iloc[-1]:
                            confirmations += 1

            if timeframes_evaluated == 0:
                return False  # sin datos, no se puede confirmar: descartar

            return confirmations >= 1
        except Exception as e:
            logger.error(f"Error en validación estructural: {e}")
            return False

    def _has_active_signal(self, asset: str) -> bool:
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True
        return excel_manager.has_active_signal(asset)

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals from memory."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]


signal_engine = SignalEngine()
