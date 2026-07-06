"""Signal engine for technical analysis and signal generation."""
import asyncio
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger

from app.models.signal import Signal, SignalDirection, SignalStatus
from app.services.market_data import market_data_service
from app.services.indicators import indicator_service
from app.services.excel_manager import excel_manager
from app.models.asset import Asset
from app.core.config import settings


class SignalEngine:
    """Engine for generating trading signals based on technical indicators."""

    # Default constants (can be overridden by Excel)
    # CAMBIO (a pedido del usuario, 2026-07-02): bajado de 6 a 5 para más
    # frecuencia de señales, a cambio de un poco menos de selectividad.
    # En el ciclo de referencia (18:20 UTC), esto habría permitido 2 señales
    # adicionales (EURUSD 5/6, USDCAD 5/6) que quedaron a un indicador del
    # umbral anterior.
    MIN_INDICATORS_FOR_SIGNAL = 5
    SIGNAL_TIMEFRAME = "5m"

    def __init__(self):
        self.active_signals: Dict[str, Signal] = {}
        self.min_indicators = self.MIN_INDICATORS_FOR_SIGNAL
        self.signal_timeframe = self.SIGNAL_TIMEFRAME
        self._load_config_from_excel()
        self._load_active_signals()

    def _load_config_from_excel(self):
        """Load configuration from Excel file."""
        try:
            config = excel_manager.get_config()
            params = config.get("parameters", {})
            self.min_indicators = int(params.get("min_indicators", self.MIN_INDICATORS_FOR_SIGNAL))
            self.signal_timeframe = str(params.get("signal_timeframe", self.SIGNAL_TIMEFRAME))
            logger.info(f"Configuration loaded from Excel: Min Indicators={self.min_indicators}, Timeframe={self.signal_timeframe}")
        except Exception as e:
            logger.error(f"Error loading configuration from Excel: {e}")

    def reload_config(self):
        """
        Recarga pública de configuración desde Excel.

        CAMBIO: antes `_load_config_from_excel()` solo se llamaba una vez en
        `__init__`, así que cambiar `min_indicators` (u otro parámetro) vía
        el dashboard/API o editando el Excel directamente NO tenía ningún
        efecto hasta reiniciar el proceso por completo -- una fuente de
        confusión ("ya lo cambié pero sigue igual"). Este método permite que
        el endpoint de configuración fuerce una recarga inmediata sin
        necesidad de reiniciar el servidor.
        """
        self._load_config_from_excel()

    def _load_active_signals(self):
        """Load active signals from Excel into memory."""
        try:
            active_records = excel_manager.get_active_signals()
            for record in active_records:
                signal = Signal.from_dict(record)
                self.active_signals[signal.id] = signal
            logger.info(f"Loaded {len(self.active_signals)} active signals from Excel")
        except Exception as e:
            logger.error(f"Error loading active signals: {e}")

    async def analyze_asset(self, asset: str) -> Optional[Signal]:
        try:
            if self._has_active_signal(asset):
                logger.info(f"[REJECT] {asset}: ya tiene una señal activa o está en cooldown.")
                return None

            df = await market_data_service.get_time_series(
                asset, interval=self.signal_timeframe, outputsize=200
            )

            if df is None or df.empty:
                # CAMBIO (fix visibilidad "sigue sin enviar señales"): este
                # rechazo estaba en nivel DEBUG, invisible en consola (el
                # logger de consola está configurado en INFO). Elevado a INFO
                # para que sea diagnosticable sin tener que abrir los logs en
                # disco.
                logger.info(f"[REJECT] {asset}: sin datos históricos (MT4 no conectado o Twelve Data sin respuesta).")
                return None

            # CAMBIO 16: Filtro de spread máximo
            price_data = await market_data_service.get_price(asset)
            spread = 0.0
            if price_data and "ask" in price_data and "bid" in price_data:
                spread = price_data["ask"] - price_data["bid"]
            
            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]
            current_spread_pips = round(spread / pip_size, 1)

            max_spread_pips = {
                "XAU": 50.0, # Aumentado para evitar bloqueos por spread en Oro
                "US30": 30.0,
                "US100": 30.0,
                "US500": 30.0,
                "DAX": 30.0,
                "GER40": 30.0,
                "DJI": 30.0,
                "NDX": 30.0,
                "SPX": 30.0,
            }.get(asset.upper().split("USD")[0], 10.0) # Default 10.0 for FX pairs

            if current_spread_pips > max_spread_pips:
                logger.info(f"Signal for {asset} rejected: Spread ({current_spread_pips} pips) exceeds max allowed ({max_spread_pips} pips).")
                logger.debug(f"[DEBUG] Skipping {asset}: Spread too high ({current_spread_pips} pips).")
                return None

            indicators = indicator_service.calculate_all(df)
            if not indicators:
                logger.info(f"[REJECT] {asset}: no se pudieron calcular indicadores (datos insuficientes).")
                return None

            direction, indicators_met, details = indicator_service.evaluate_signals(df, indicators)

            # Fix "dejó de mandar señales": Usamos la configuración dinámica de Excel
            if direction == "NEUTRAL" or indicators_met < self.min_indicators:
                logger.info(f"[REJECT] {asset}: dirección NEUTRAL o indicadores insuficientes ({indicators_met}/{self.min_indicators}).")
                return None

            # Session Filter: Londres/Nueva York
            # CAMBIO (fix "sigue sin enviar señales"): esta condición estaba
            # hardcodeada a 07:00-18:00 UTC, IGNORANDO por completo
            # settings.SESSION_FILTER_ENABLED / SESSION_START_HOUR_UTC /
            # SESSION_END_HOUR_UTC (que sí existen en config.py pero nunca se
            # leían aquí). Ahora respeta la configuración real.
            # IMPORTANTE PARA DIAGNÓSTICO: si estás en Mexico City (UTC-6),
            # la ventana 06:00-21:00 UTC equivale a 00:00-15:00 hora de
            # Mexico City. Si pruebas por la tarde/noche (hora de México),
            # este filtro bloqueará TODAS las señales sin importar nada más.
            if settings.SESSION_FILTER_ENABLED:
                current_hour = datetime.utcnow().hour
                if not (settings.SESSION_START_HOUR_UTC <= current_hour < settings.SESSION_END_HOUR_UTC):
                    logger.info(
                        f"[REJECT] {asset}: fuera de la ventana de sesión "
                        f"({settings.SESSION_START_HOUR_UTC}:00-{settings.SESSION_END_HOUR_UTC}:00 UTC). "
                        f"Hora actual UTC: {current_hour}:00."
                    )
                    return None

            # Volatility Filter: Avoid "Flat" markets
            if df is not None and len(df) > 50:
                recent_atr = df["high"].rolling(14).max() - df["low"].rolling(14).min()
                avg_atr = recent_atr.mean()
                current_atr = recent_atr.iloc[-1]
                
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

            # If all checks pass, create the signal
            signal = self._create_signal(asset, direction, df, indicators_met)
            if signal:
                self.active_signals[signal.id] = signal
                await excel_manager.register_signal(signal)
                logger.info(f"NEW SIGNAL: {signal.asset} {signal.direction.value} @ {signal.entry_price}")
                return signal

        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return None

    async def analyze_all_assets(self) -> List[Signal]:
        """Analyze all active assets and return new signals."""
        new_signals = []
        # CAMBIO (fix "sigue sin enviar señales"): resumen visible por ciclo.
        # Antes, si un ciclo completo terminaba en cero señales, no había
        # NINGÚN log agregado que lo confirmara -- solo rechazos individuales
        # dispersos (varios en DEBUG, invisibles en consola). Ahora cada
        # ciclo termina con una línea clara en INFO indicando cuántos activos
        # se analizaron y cuántas señales se generaron, para poder detectar
        # de inmediato si el motor sigue corriendo pero sin producir señales.
        current_hour = datetime.utcnow().hour
        session_ok = (not settings.SESSION_FILTER_ENABLED) or \
            (settings.SESSION_START_HOUR_UTC <= current_hour < settings.SESSION_END_HOUR_UTC)

        for asset in settings.ACTIVE_ASSETS:
            signal = await self.analyze_asset(asset)
            if signal:
                new_signals.append(signal)

        logger.info(
            f"[CICLO] Analizados {len(settings.ACTIVE_ASSETS)} activos -> "
            f"{len(new_signals)} señal(es) nueva(s). "
            f"Sesión activa (UTC {current_hour}:00): {'SÍ' if session_ok else 'NO -- fuera de ventana ' + str(settings.SESSION_START_HOUR_UTC) + '-' + str(settings.SESSION_END_HOUR_UTC) + ' UTC'}."
        )
        return new_signals

    def _assess_smc_confluence(self, direction: str, entry_price: float, df: pd.DataFrame) -> dict:
        """
        Evalúa confluencia SMC (Smart Money Concepts) para la señal:
        - fvg_confluence: el precio de entrada cae dentro de un Fair Value
          Gap a favor de la dirección (zona de valor institucional).
        - liquidity_sweep: hubo un barrido reciente de liquidez (stop hunt) a
          favor de la dirección -- el precio rompió un swing high/low previo
          y cerró de vuelta del lado correcto.

        CAMBIO (restaurado a pedido del usuario, 2026-07-05): esta
        evaluación existía en la implementación original del fix de Win
        Rate pero se perdió en una reescritura posterior de `_create_signal`
        por otra sesión, dejando `fvg_confluence`/`liquidity_sweep` siempre
        en False y `smc_quality` siempre en su default (1.0). No afecta el
        tamaño de lote ni el SL/TP -- es información de calidad para
        análisis/reportes en Excel, no cambia el comportamiento de riesgo.

        Retorna dict con fvg_confluence, liquidity_sweep, smc_quality
        (1.0 base, +0.15 por FVG, +0.10 por barrido de liquidez).
        """
        fvg_confluence = False
        liquidity_sweep = False
        try:
            fvgs = indicator_service.detect_fvg(df)
            liquidity = indicator_service.detect_liquidity(df)

            if direction == "BUY":
                for fvg in fvgs:
                    if fvg["type"] == "BULLISH" and fvg["bottom"] <= entry_price <= fvg["top"] * 1.001:
                        fvg_confluence = True
                        break

                recent_lows = df["low"].tail(6).values
                recent_close = df["close"].iloc[-1]
                for ssl in liquidity.get("SSL", []):
                    if any(low < ssl for low in recent_lows[:-1]) and recent_close > ssl:
                        liquidity_sweep = True
                        break
            else:  # SELL
                for fvg in fvgs:
                    if fvg["type"] == "BEARISH" and fvg["bottom"] * 0.999 <= entry_price <= fvg["top"]:
                        fvg_confluence = True
                        break

                recent_highs = df["high"].tail(6).values
                recent_close = df["close"].iloc[-1]
                for bsl in liquidity.get("BSL", []):
                    if any(high > bsl for high in recent_highs[:-1]) and recent_close < bsl:
                        liquidity_sweep = True
                        break
        except Exception as e:
            logger.error(f"Error assessing SMC confluence: {e}")

        smc_quality = 1.0
        if fvg_confluence:
            smc_quality += 0.15
        if liquidity_sweep:
            smc_quality += 0.10

        return {
            "fvg_confluence": fvg_confluence,
            "liquidity_sweep": liquidity_sweep,
            "smc_quality": round(smc_quality, 2)
        }

    def _create_signal(self, asset: str, direction: str, df: pd.DataFrame, indicators_met: int) -> Optional[Signal]:
        """Create a new signal object with risk management parameters."""
        try:
            current_price = df["close"].iloc[-1]
            atr = indicator_service._calc_atr(df)

            # Risk Management
            risk_amount = settings.INITIAL_CAPITAL * (settings.RISK_PERCENTAGE / 100)

            pip_info = Asset.get_pip_info(asset)
            pip_size = pip_info["pip_size"]

            # Stop Loss base: 1.5 * ATR
            sl_distance = atr * 1.5

            # CAMBIO (fix "sigue sin enviar señales" / regresión de Win Rate):
            # esta función había sido reescrita en un commit posterior y perdió
            # dos cosas clave del fix de Win Rate:
            #   1. El piso de SL mínimo (settings.MIN_SL_PIPS_FX/INDEX_GOLD),
            #      por lo que el SL podía quedar demasiado ajustado frente al
            #      spread real.
            #   2. TP1/TP2/TP3 en múltiplos reales de R (1R/2R/3R). Había
            #      quedado en TP1=3R, TP2=4.5R, TP3=6R -- niveles casi
            #      inalcanzables, PEOR que el problema original que motivó
            #      el fix (TP fijo en 3R). Se restaura el uso de
            #      settings.TP1_R_MULTIPLE / TP2_R_MULTIPLE / TP3_R_MULTIPLE,
            #      que es lo que permite el cierre parcial (TP1 cierra 50% y
            #      mueve el SL a breakeven, TP2 cierra 25% y sube el SL a
            #      TP1) implementado en position_monitor.py -- esa lógica
            #      sigue intacta ahí, solo necesitaba niveles alcanzables.
            is_index_or_gold = any(x in asset.upper() for x in ["XAU", "US30", "US100", "US500", "DAX", "DJI", "NDX", "SPX"])
            is_ger40 = any(x in asset.upper() for x in ["GER40", "DAX"])
            min_sl_pips = settings.MIN_SL_PIPS_INDEX_GOLD if (is_index_or_gold and not is_ger40) else settings.MIN_SL_PIPS_FX
            if (sl_distance / pip_size) < min_sl_pips:
                sl_distance = min_sl_pips * pip_size

            r1 = sl_distance * settings.TP1_R_MULTIPLE
            r2 = sl_distance * settings.TP2_R_MULTIPLE
            r3 = sl_distance * settings.TP3_R_MULTIPLE

            if direction == "BUY":
                stop_loss = current_price - sl_distance
                take_profit_1 = current_price + r1
                take_profit_2 = current_price + r2
                take_profit_3 = current_price + r3
            else:
                stop_loss = current_price + sl_distance
                take_profit_1 = current_price - r1
                take_profit_2 = current_price - r2
                take_profit_3 = current_price - r3

            # Calculate Lot Size
            sl_pips = sl_distance / pip_size

            # Lot size formula: risk_amount / (sl_pips * pip_value_per_lot)
            # Simplification: risk_amount / (sl_distance * contract_size)
            contract_size = pip_info["contract_size"]
            lot_size = risk_amount / (sl_distance * contract_size)
            lot_size = round(max(0.01, lot_size), 2)

            # Evaluación de confluencia SMC (restaurado a pedido del usuario)
            smc_info = self._assess_smc_confluence(direction, float(current_price), df)

            # Create signal
            signal = Signal(
                asset=asset,
                direction=SignalDirection(direction),
                entry_price=float(current_price),
                stop_loss=float(stop_loss),
                take_profit_1=float(take_profit_1),
                take_profit_2=float(take_profit_2),
                take_profit_3=float(take_profit_3),
                sl_pips=round(sl_pips, 1),
                tp1_pips=round(abs(take_profit_1 - current_price) / pip_size, 1),
                tp2_pips=round(abs(take_profit_2 - current_price) / pip_size, 1),
                tp3_pips=round(abs(take_profit_3 - current_price) / pip_size, 1),
                lot_size=lot_size,
                timeframe=self.signal_timeframe,
                indicators_met=indicators_met,
                score=float(indicators_met / 18.0), # Normalized score
                session=market_data_service.get_current_session(),
                # CAMBIO CRÍTICO (causa raíz real de "sigue sin enviar
                # señales"): aquí se pasaba `datetime.utcnow().hour` (un int,
                # ej. 21) directamente a `entry_hour`, pero el modelo `Signal`
                # define `entry_hour: Optional[str]`. Pydantic rechazaba la
                # creación del objeto Signal con un ValidationError en TODOS
                # los casos, sin excepción -- independientemente de si el
                # activo pasaba el filtro de sesión, spread, indicadores o
                # validación estructural. El error quedaba atrapado por el
                # try/except de esta función y solo se veía como
                # "Signal creation error for <asset>: 1 validation error..."
                # en el log, que fácilmente pasa desapercibido. Se corrige
                # formateando la hora como string "HH:MM".
                entry_hour=datetime.utcnow().strftime("%H:%M"),
                entry_spread=0.0, # Will be updated on execution
                entry_atr=float(atr),
                fvg_confluence=smc_info["fvg_confluence"],
                liquidity_sweep=smc_info["liquidity_sweep"],
                smc_quality=smc_info["smc_quality"],
                # Habilita el cierre parcial real (TP1 50% + breakeven,
                # TP2 25% + SL->TP1, TP3 cierra el resto) en position_monitor.py
                initial_lot_size=lot_size,
                remaining_lot_size=lot_size,
                tp1_hit=False,
                tp2_hit=False,
                breakeven_active=False,
                realized_partial_pnl=0.0
            )

            return signal
        except Exception as e:
            logger.error(f"Signal creation error for {asset}: {e}")
            return None

    async def _validate_structural(self, asset: str, direction: str) -> bool:
        """Validate signal with higher timeframes (30m, 1h, 4h)."""
        try:
            confirmations = 0
            timeframes_evaluated = 0
            h4_confirmed = False
            
            for tf in ["30m", "1h", "4h"]:
                df_tf = await market_data_service.get_time_series(asset, interval=tf, outputsize=100)
                if df_tf is not None and not df_tf.empty:
                    timeframes_evaluated += 1
                    ema200 = df_tf["close"].ewm(span=200, adjust=False).mean().iloc[-1]
                    current_price = df_tf["close"].iloc[-1]
                    
                    is_confirmed = (direction == "BUY" and current_price > ema200) or \
                                   (direction == "SELL" and current_price < ema200)
                    
                    if is_confirmed:
                        confirmations += 1
                    
                    if tf == "4h" and is_confirmed:
                        h4_confirmed = True

            # Require at least 2 confirmations (e.g. 30m, 1h or 4h must align)
            if timeframes_evaluated > 0:
                if confirmations < 2:
                    logger.info(f"Structural validation: Insufficient trend confirmation ({confirmations}/2) for {asset}")
                    return False

            # SMC Alignment Check on 30m (Intermediate structure)
            # CAMBIO: Flexibilizamos la búsqueda de FVG y lo hacemos opcional para evitar bloqueos por falta de datos
            df_30m = await market_data_service.get_time_series(asset, interval="30m", outputsize=100)
            if df_30m is not None and not df_30m.empty and len(df_30m) > 10:
                fvgs = indicator_service.detect_fvg(df_30m)
                # Look for a recent FVG (last 30 candles) in the trade direction
                recent_fvgs = fvgs[-30:] if len(fvgs) >= 30 else fvgs
                has_fvg = any(f["type"] == ("BULLISH" if direction == "BUY" else "BEARISH") for f in recent_fvgs)
                
                if not has_fvg:
                    logger.info(f"Signal for {asset} rejected: No {direction.lower()} FVG confirmation on 30m (last 30 candles).")
                    return False
            else:
                # Si no hay datos de 30m, permitimos la señal pero con una advertencia
                logger.warning(f"Structural validation: FVG check skipped for {asset} (Insufficient 30m data). Proceeding with caution.")

            return True
        except Exception as e:
            logger.error(f"Error en validación estructural: {e}")
            return False

    def _has_active_signal(self, asset: str) -> bool:
        """Check if an asset already has an active signal to avoid duplicates."""
        # 1. Check memory for currently ACTIVE signals
        for signal in self.active_signals.values():
            if signal.asset == asset and signal.status == SignalStatus.ACTIVE:
                return True
        
        # 2. Check Excel for currently ACTIVE signals
        if excel_manager.has_active_signal(asset):
            return True
            
        # 3. ANTI-OVERTRADING: Cooldown Filter (5 minutes)
        try:
            df_signals = excel_manager.get_signals_dataframe()
            if not df_signals.empty:
                asset_signals = df_signals[df_signals["asset"] == asset].copy()
                if not asset_signals.empty:
                    asset_signals["closed_at"] = pd.to_datetime(asset_signals["closed_at"], errors="coerce")
                    last_close = asset_signals["closed_at"].max()
                    
                    if pd.notna(last_close):
                        diff_minutes = (datetime.now() - last_close).total_seconds() / 60
                        cooldown = 5 # 5 minutes cooldown
                        if diff_minutes < cooldown:
                            logger.info(f"Signal for {asset} rejected: Cooldown active ({round(cooldown - diff_minutes, 1)}m remaining).")
                            return True
        except Exception as e:
            logger.error(f"Error checking cooldown for {asset}: {e}")
            
        return False

    def get_active_signals(self) -> List[Signal]:
        """Get all active signals from memory."""
        return [s for s in self.active_signals.values() if s.status == SignalStatus.ACTIVE]


# Singleton instance
signal_engine = SignalEngine()
