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

    # CAMBIO (fix "dejó de mandar señales"): bajado de 7 a 6. Con conteo de
    # indicadores corregido (ya no inflado por el bug de substrings), un
    # umbral de 7 dejaba pasar ~1% de los escenarios simulados de mercado,
    # contra ~15% con umbral 6 (ver validación en el PR). 6 sigue siendo
    # selectivo (exige más de un tercio de los 18 indicadores confirmando en
    # la misma dirección con score ponderado suficiente) pero ya no bloquea
    # prácticamente todas las señales. Es además el valor que ya estaba
    # configurado en trading_config.xlsx.
    MIN_INDICATORS_FOR_SIGNAL = 6
    ANALYSIS_TIMEFRAMES = ["30m", "1h", "4h"]
    SIGNAL_TIMEFRAME = "5m"
    ATR_SL_MULTIPLIER = 2.0 # CAMBIO 17: Centralized ATR SL multiplier

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self._load_config_from_excel()
        self._load_active_signals()

    def _load_config_from_excel(self):
        """Load trading parameters and indicator settings from Excel."""
        try:
            config = excel_manager.get_config()
            params = config.get("parameters", {})
            
            # Load core parameters
            self.min_indicators = int(params.get("min_indicators", self.MIN_INDICATORS_FOR_SIGNAL))
            self.signal_timeframe = str(params.get("signal_timeframe", self.SIGNAL_TIMEFRAME))
            
            # Update settings for other services if needed
            if "initial_capital" in params:
                settings.INITIAL_CAPITAL = float(params["initial_capital"])
            if "risk_percentage" in params:
                settings.RISK_PERCENTAGE = float(params["risk_percentage"])
                
            # Indicators are handled by indicator_service.update_from_config
            if config.get("indicators"):
                indicator_service.update_from_config(config["indicators"])
                
            logger.info(f"Configuration loaded from Excel: Min Indicators={self.min_indicators}, Timeframe={self.signal_timeframe}")
        except Exception as e:
            logger.error(f"Error loading config from Excel: {e}")
            self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL
            self.signal_timeframe = self.SIGNAL_TIMEFRAME

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

            # CAMBIO (fix win-rate): spread máximo configurable y más estricto
            # para FX (antes 10.0 pips fijo). Un spread amplio respecto a un SL
            # ajustado distorsiona el R:R real y aumenta la probabilidad de
            # ser barrido por el spread cerca de la entrada.
            asset_key = asset.upper().split("USD")[0]
            if "XAU" in asset.upper():
                max_spread_pips = settings.MAX_SPREAD_PIPS_XAU
            elif any(x in asset.upper() for x in ["US30", "US100", "US500", "DAX", "GER40", "DJI", "NDX", "SPX"]):
                max_spread_pips = settings.MAX_SPREAD_PIPS_INDEX_GOLD
            else:
                max_spread_pips = settings.MAX_SPREAD_PIPS_FX

            if current_spread_pips > max_spread_pips:
                logger.info(f"Signal for {asset} rejected: Spread ({current_spread_pips} pips) exceeds max allowed ({max_spread_pips} pips).")
                logger.debug(f"[DEBUG] Skipping {asset}: Spread too high ({current_spread_pips} pips).")
                return None

            indicators = indicator_service.calculate_all(df)
            if not indicators:
                logger.debug(f"[DEBUG] No indicators calculated for {asset}. Skipping signal evaluation.")
                return None

            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)
            # CAMBIO (fix "dejó de mandar señales"): antes esta condición usaba
            # el constante de clase MIN_INDICATORS_FOR_SIGNAL=7, hardcodeado e
            # INDEPENDIENTE del self.min_indicators (por defecto 6) que ya usa
            # evaluate_signals() internamente para decidir BUY/SELL vs NEUTRAL.
            # Esa inconsistencia (6 adentro, 7 afuera) ya existía antes de esta
            # revisión, pero quedaba enmascarada porque el bug de conteo por
            # substrings inflaba artificialmente indicators_met, así que casi
            # siempre superaba el 7 igual. Al corregir el conteo (ahora fiel a
            # los indicadores realmente confirmados), casi ninguna señal volvía
            # a alcanzar el umbral de 7, y el sistema dejó de emitir señales.
            # Ahora se usa una única fuente de verdad (self.min_indicators) en
            # ambos puntos.
            if direction == "NEUTRAL" or indicators_met < self.min_indicators:
                logger.debug(f"[DEBUG] Skipping {asset}: Indicator evaluation NEUTRAL or insufficient indicators met ({indicators_met}/{self.min_indicators}).")
                return None

            # CAMBIO (fix win-rate): Session Filter reactivado.
            # Antes el rango era 0-23h (siempre verdadero = sin filtro real),
            # lo que permitía operar en sesión asiática de baja liquidez y en
            # horarios de noticias de alta volatilidad, empeorando el ratio
            # señal/ruido. Ahora se restringe (por defecto) a la ventana
            # Londres/Nueva York, configurable vía settings.
            if settings.SESSION_FILTER_ENABLED:
                current_hour = datetime.utcnow().hour
                if not (settings.SESSION_START_HOUR_UTC <= current_hour < settings.SESSION_END_HOUR_UTC):
                    logger.info(
                        f"Signal for {asset} rejected: Outside trading session "
                        f"({settings.SESSION_START_HOUR_UTC}:00-{settings.SESSION_END_HOUR_UTC}:00 UTC)."
                    )
                    return None

            # Volatility Filter: Avoid "Flat" markets
            # If ATR is too low compared to recent average, the market lacks movement
            if df is not None and len(df) > 50:
                recent_atr = df["high"].rolling(14).max() - df["low"].rolling(14).min()
                avg_atr = recent_atr.mean()
                current_atr = recent_atr.iloc[-1]
                # Filter for low volatility (flat markets)
                if current_atr < (avg_atr * 0.5):
                    logger.info(f"Signal for {asset} rejected: Low volatility (Current ATR {round(current_atr/pip_size, 1)} < 50% of Avg {round(avg_atr/pip_size, 1)}).")
                    return None

                # Filter for high volatility (erratic markets) - Flexibilizado a 2.5x
                if current_atr > (avg_atr * 2.5): 
                    logger.info(f"Signal for {asset} rejected: High volatility (Current ATR {round(current_atr/pip_size, 1)} > 250% of Avg {round(avg_atr/pip_size, 1)}).")
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

            # 1. Calculate Stop Loss using ATR (ATR_SL_MULTIPLIER x ATR) as a baseline,
            # refinado opcionalmente con estructuras SMC (FVG / liquidez).
            # CAMBIO (fix CRÍTICO marcado en el código como "CAMBIO 18: BUG en
            # lógica de Stop Loss con SMC"): la lógica duplicada y confusa que
            # existía para BUY/SELL se reemplaza por un único helper testeado
            # `_refine_sl_with_smc`, con el mismo criterio para ambas direcciones.
            sl_distance_atr = atr * self.ATR_SL_MULTIPLIER
            sl_distance = sl_distance_atr
            if df is not None:
                sl_distance = self._refine_sl_with_smc(
                    direction=direction,
                    entry_price=entry_price,
                    sl_distance_atr=sl_distance_atr,
                    atr=atr,
                    pip_size=pip_size,
                    df=df,
                )

            # --- Apply Minimum Stop Loss Limits ---
            # CAMBIO (fix win-rate): SL mínimo subido para FX (6 -> configurable,
            # default 10 pips) para que el spread no represente una fracción
            # excesiva del riesgo. Ver settings.MIN_SL_PIPS_FX / MIN_SL_PIPS_INDEX_GOLD.
            is_index_or_gold = any(x in asset.upper() for x in ["XAU", "US30", "US100", "US500", "DAX", "DJI", "NDX", "SPX"])
            is_ger40 = any(x in asset.upper() for x in ["GER40", "DAX"])

            min_sl_pips = settings.MIN_SL_PIPS_INDEX_GOLD if (is_index_or_gold and not is_ger40) else settings.MIN_SL_PIPS_FX
            current_sl_pips = sl_distance / pip_size

            if current_sl_pips < min_sl_pips:
                sl_distance = min_sl_pips * pip_size

            if direction == SignalDirection.BUY:
                stop_loss = entry_price - sl_distance
            else:
                stop_loss = entry_price + sl_distance

            # 2. CAMBIO (fix win-rate): TP1/TP2/TP3 escalonados y REALES.
            # Antes TP1 = TP2 = TP3 = entry +/- 3*SL (un único objetivo "todo o
            # nada" que exigía ~75% de win rate solo para ser rentable).
            # Ahora:
            #   TP1 = 1R -> se cierra TP1_CLOSE_PCT% y se mueve el SL a breakeven
            #   TP2 = 2R -> se cierra TP2_CLOSE_PCT% y se sube el SL a TP1
            #   TP3 = 3R -> se cierra el resto (TP3_CLOSE_PCT%)
            # Esto convierte operaciones que antes eran pérdida total (precio
            # llega a 1R-2R y luego revierte) en ganancias parciales o, en el
            # peor caso, breakeven -- sube el win rate real sin "inventar" datos.
            r1 = sl_distance * settings.TP1_R_MULTIPLE
            r2 = sl_distance * settings.TP2_R_MULTIPLE
            r3 = sl_distance * settings.TP3_R_MULTIPLE

            if direction == SignalDirection.BUY:
                tp1 = entry_price + r1
                tp2 = entry_price + r2
                tp3 = entry_price + r3
            else:  # SELL
                tp1 = entry_price - r1
                tp2 = entry_price - r2
                tp3 = entry_price - r3

            # 3. Fixed Risk Management: 0.3% of $10,000 ($30)
            # Use runtime settings if available, otherwise defaults
            fixed_capital = getattr(settings, "INITIAL_CAPITAL", 10000.0)
            fixed_risk_percent = getattr(settings, "RISK_PERCENTAGE", 0.003)
            risk_amount_usd = fixed_capital * fixed_risk_percent # Exactly $30 with defaults
            
            # Quality adjustment tracking (for logs/Excel, but doesn't change risk_amount anymore)
            quality_multiplier = 1.0
            fvg_confluence = False
            fvgs = indicator_service.detect_fvg(df) if df is not None else []
            entry_fvgs = [f for f in fvgs if abs(f["price"] - entry_price) / entry_price < 0.001]
            if entry_fvgs:
                quality_multiplier += 0.25
                fvg_confluence = True

            liquidity_sweep = False
            if df is not None:
                try:
                    liquidity = indicator_service.detect_liquidity(df)
                    if direction == SignalDirection.BUY:
                        recent_lows = df["low"].iloc[-10:].min()
                        if any(ssl < recent_lows for ssl in liquidity["SSL"]):
                            quality_multiplier += 0.25
                            liquidity_sweep = True
                    else:
                        recent_highs = df["high"].iloc[-10:].max()
                        if any(bsl > recent_highs for bsl in liquidity["BSL"]):
                            quality_multiplier += 0.25
                            liquidity_sweep = True
                except Exception as e:
                    logger.error(f"Error checking liquidity sweep: {e}")

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
            lot_size = round(max(0.01, min(lot_size, 10.0)), 2)

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
                indicators_detail=details,
                # CAMBIO (fix win-rate): tracking de cierre parcial / breakeven
                initial_lot_size=lot_size,
                remaining_lot_size=lot_size,
                tp1_hit=False,
                tp2_hit=False,
                breakeven_active=False,
                realized_partial_pnl=0.0
            )
        except Exception as e:
            logger.error(f"Signal creation error for {asset}: {e}")
            return None

    def _refine_sl_with_smc(
        self,
        direction: SignalDirection,
        entry_price: float,
        sl_distance_atr: float,
        atr: float,
        pip_size: float,
        df: pd.DataFrame,
    ) -> float:
        """
        Refina la distancia de Stop Loss basada en ATR usando estructuras SMC
        (Fair Value Gaps y zonas de liquidez), eligiendo el nivel protector
        más cercano disponible sin dejarlo demasiado ajustado.

        CAMBIO (fix del bug crítico documentado previamente en el código como
        "CAMBIO 18: BUG en lógica de Stop Loss con SMC"): se unifica la lógica
        para BUY y SELL en un solo método, con límites claros:
          - El SL basado en SMC solo se usa si es MÁS AJUSTADO que el SL por
            ATR (protege capital) pero no menor a la mitad del SL por ATR
            (para evitar SL demasiado ajustados que se activan por ruido).
          - Si no hay zona SMC válida dentro de ese rango, se usa el SL por
            ATR como fallback (comportamiento seguro y predecible).
        """
        try:
            fvgs = indicator_service.detect_fvg(df)
            liquidity = indicator_service.detect_liquidity(df)
            buffer = pip_size * 5  # 5 pips de colchón sobre la zona SMC

            candidate_distances: List[float] = []

            if direction == SignalDirection.BUY:
                for fvg in fvgs:
                    if fvg["type"] == "BULLISH" and fvg["price"] < entry_price:
                        candidate_distances.append(entry_price - (fvg["price"] - buffer))
                for ssl_zone in liquidity["SSL"]:
                    if ssl_zone < entry_price:
                        candidate_distances.append(entry_price - (ssl_zone - buffer))
            else:  # SELL
                for fvg in fvgs:
                    if fvg["type"] == "BEARISH" and fvg["price"] > entry_price:
                        candidate_distances.append((fvg["price"] + buffer) - entry_price)
                for bsl_zone in liquidity["BSL"]:
                    if bsl_zone > entry_price:
                        candidate_distances.append((bsl_zone + buffer) - entry_price)

            # Solo distancias positivas y válidas
            candidate_distances = [d for d in candidate_distances if d > 0]
            if not candidate_distances:
                return sl_distance_atr

            min_allowed = sl_distance_atr / 2  # No permitir SL menor a la mitad del ATR SL
            valid_candidates = [d for d in candidate_distances if min_allowed < d < sl_distance_atr]

            if valid_candidates:
                # El más ajustado dentro del rango permitido (mejor relación riesgo/recompensa)
                return min(valid_candidates)

            return sl_distance_atr
        except Exception as e:
            logger.error(f"Error refining SL with SMC structures: {e}")
            return sl_distance_atr

    async def analyze_all_assets(self) -> List[Signal]:
        signals = []
        for asset in settings.ACTIVE_ASSETS:
            signal = await self.analyze_asset(asset)
            if signal:
                signals.append(signal)
        return signals

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        """Validate signal with higher timeframe trend and SMC alignment."""
        try:
            # General structural validation: Trend Filter with at least 1 of 3 higher timeframes confirming.
            # This ensures we are not trading against the dominant trend while allowing for minor pullbacks.
            confirmations = 0
            timeframes_evaluated = 0

            h4_confirmed = False
            for tf in self.ANALYSIS_TIMEFRAMES:
                df_tf = await market_data_service.get_time_series(asset, interval=tf, outputsize=200)
                if df_tf is None or df_tf.empty:
                    continue

                timeframes_evaluated += 1
                ema200 = df_tf["close"].ewm(span=200, adjust=False).mean()
                
                if len(ema200) > 0:
                    current_price = df_tf["close"].iloc[-1]
                    is_confirmed = False
                    if direction == "BUY" and current_price > ema200.iloc[-1]:
                        confirmations += 1
                        is_confirmed = True
                    elif direction == "SELL" and current_price < ema200.iloc[-1]:
                        confirmations += 1
                        is_confirmed = True
                    
                    if tf == "4h" and is_confirmed:
                        h4_confirmed = True

            # Require at least 2 confirmations (e.g. 30m, 1h or 4h must align)
            # El filtro de 4h ya no es obligatorio si los otros dos confirman, pero suma puntos.
            if timeframes_evaluated > 0:
                if confirmations < 2:
                    logger.info(f"Structural validation: Insufficient trend confirmation ({confirmations}/2) for {asset}")
                    return False

            # SMC Alignment Check on 30m (Intermediate structure)
            # We want to see a recent FVG in the direction of the trade as "Smart Money" confirmation.
            df_30m = await market_data_service.get_time_series(asset, interval="30m", outputsize=100)
            if df_30m is not None and not df_30m.empty:
                fvgs = indicator_service.detect_fvg(df_30m)
                # Check within last 10 candles for better flexibility in high volatility
                recent_fvgs = fvgs[-10:] if len(fvgs) >= 10 else fvgs
                
                if direction == "BUY":
                    has_bullish_fvg = any(f["type"] == "BULLISH" for f in recent_fvgs)
                    if not has_bullish_fvg:
                        logger.info(f"Signal for {asset} rejected: No bullish FVG confirmation on 30m (last 10 candles).")
                        return False
                elif direction == "SELL":
                    has_bearish_fvg = any(f["type"] == "BEARISH" for f in recent_fvgs)
                    if not has_bearish_fvg:
                        logger.info(f"Signal for {asset} rejected: No bearish FVG confirmation on 30m (last 10 candles).")
                        return False

            return True
        except Exception as e:
            logger.error(f"Error en validación estructural: {e}")
            return False

    def _has_active_signal(self, asset: str) -> bool:
        # 1. Check memory for currently ACTIVE signals
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True
        
        # 2. Check Excel for currently ACTIVE signals
        if excel_manager.has_active_signal(asset):
            return True
            
        # 3. ANTI-OVERTRADING: Cooldown Filter (15 minutes)
        # Check if a signal for this asset was closed very recently
        try:
            df_signals = excel_manager.get_signals_dataframe()
            if not df_signals.empty:
                asset_signals = df_signals[df_signals["asset"] == asset].copy()
                if not asset_signals.empty:
                    # Convert closed_at to datetime
                    asset_signals["closed_at"] = pd.to_datetime(asset_signals["closed_at"], errors="coerce")
                    last_close = asset_signals["closed_at"].max()
                    
                    if pd.notna(last_close):
                        diff_minutes = (datetime.now() - last_close).total_seconds() / 60
                        cooldown = 15 # 15 minutes cooldown
                        if diff_minutes < cooldown:
                            logger.info(f"Signal for {asset} rejected: Cooldown active ({round(cooldown - diff_minutes, 1)}m remaining).")
                            return True
        except Exception as e:
            logger.error(f"Error checking cooldown for {asset}: {e}")
            
        return False

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals from memory."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]


signal_engine = SignalEngine()
