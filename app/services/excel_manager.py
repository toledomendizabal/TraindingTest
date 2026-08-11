"""Excel manager for signal tracking and configuration."""
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict
from loguru import logger
from app.core.config import settings


def _sanitize_value(val):
    """Convert numpy/pandas types to native Python types for JSON serialization."""
    # Handle None
    if val is None:
        return None
    # Handle pandas NaT (Not a Time)
    if isinstance(val, type(pd.NaT)):
        return None
    # Handle numpy NaN and Inf (must check before isinstance float)
    if isinstance(val, (float, np.floating)):
        import math
        if math.isnan(float(val)) or math.isinf(float(val)):
            return None
        if isinstance(val, np.floating):
            return float(val)
        return val
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, (np.ndarray,)):
        return val.tolist()
    if isinstance(val, pd.Timestamp):
        return val.isoformat()
    if isinstance(val, (np.str_,)):
        return str(val)
    # Handle any other pandas types that might sneak through
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _sanitize_dict(d: dict) -> dict:
    """Recursively sanitize all values in a dictionary."""
    return {k: _sanitize_value(v) for k, v in d.items()}


def _sanitize_list(lst: list) -> list:
    """Sanitize all dicts in a list."""
    return [_sanitize_dict(d) if isinstance(d, dict) else _sanitize_value(d) for d in lst]


class ExcelManager:
    """Manages Excel files for signal tracking and configuration."""

    def __init__(self):
        self.excel_dir = settings.EXCEL_DIR
        self.signals_file = os.path.join(self.excel_dir, "signals_tracking.xlsx")
        self.config_file = os.path.join(self.excel_dir, "trading_config.xlsx")
        # Reporte diario de KPIs (win rate, P/L neto, etc. por día), para
        # el calendario del dashboard y como archivo de referencia externo.
        self.daily_kpis_file = os.path.join(self.excel_dir, "daily_kpis.xlsx")
        # CAMBIO (motor de estrategias): nuevo archivo, monitoreado por
        # pending_signals_monitor.py, para señales donde solo 1 de las 2
        # estrategias asignadas al activo confirmó. Cuando la segunda
        # estrategia confirma la MISMA dirección dentro de la ventana de
        # vigencia (settings.PENDING_SIGNALS_EXPIRY_MINUTES), la fila pasa
        # a estado CONFIRMADA y se activa la señal real (Excel principal +
        # MT5 si está habilitado). Si expira sin la segunda confirmación,
        # pasa a EXPIRADA y no se activa.
        self.pending_signals_file = os.path.join(self.excel_dir, "senales_por_confirmar.xlsx")
        self._ensure_files()

    def _ensure_files(self):
        """Ensure Excel files exist with proper structure."""
        os.makedirs(self.excel_dir, exist_ok=True)

        # Create signals tracking file
        if not os.path.exists(self.signals_file):
            self._create_signals_file()

        # Create config file
        if not os.path.exists(self.config_file):
            self._create_config_file()

        # Create pending-confirmation signals file
        if not os.path.exists(self.pending_signals_file):
            self._create_pending_signals_file()

    def _create_pending_signals_file(self):
        """Crea el Excel de 'Señales por Confirmar' (estrategia parcial)."""
        columns = [
            "id", "asset", "direction",
            "strategy_ids", "confirmed_ids", "pending_strategy_ids",
            "entry_price_ref", "details",
            "status",  # PENDIENTE | CONFIRMADA | EXPIRADA
            "created_at", "expires_at", "resolved_at",
        ]
        df = pd.DataFrame(columns=columns)
        df.to_excel(self.pending_signals_file, index=False, sheet_name="PorConfirmar")
        logger.info(f"Created pending-confirmation signals file: {self.pending_signals_file}")

    def _create_signals_file(self):
        """Create the signals tracking Excel file."""
        columns = [
            "id", "asset", "direction", "entry_price", "stop_loss",
            "take_profit_1", "take_profit_2", "take_profit_3",
            "sl_pips", "tp1_pips", "tp2_pips", "tp3_pips",
            "lot_size", "timeframe", "indicators_met", "score",
            "status", "session", "created_at", "closed_at",
            "close_price", "profit_loss", "result",
            "max_drawdown", "risk_reward_ratio", "duration_minutes",
            "entry_hour", "exit_hour", "entry_spread", "entry_atr",
            "smc_quality", "fvg_confluence", "liquidity_sweep",
            # CAMBIO (fix win-rate): columnas para cierre parcial escalonado
            "initial_lot_size", "remaining_lot_size",
            "tp1_hit", "tp2_hit", "breakeven_active", "realized_partial_pnl",
            "mt5_ticket",
            # CAMBIO (a pedido del usuario, 2026-08-11 -- prueba comparativa
            # por estrategia hasta el viernes): qué estrategia individual
            # originó cada señal, para poder filtrar/agrupar y comparar win
            # rate real por estrategia (ej. tabla dinámica en Excel por
            # `strategy_id`).
            "strategy_id", "strategy_name",
        ]
        df = pd.DataFrame(columns=columns)
        df.to_excel(self.signals_file, index=False, sheet_name="Signals")
        logger.info(f"Created signals tracking file: {self.signals_file}")

    def _create_config_file(self):
        """Create the trading configuration Excel file."""
        # Assets configuration
        assets_data = {
            "symbol": settings.ACTIVE_ASSETS,
            "active": [True] * len(settings.ACTIVE_ASSETS),
            "pip_size": [],
            "contract_size": []
        }

        from app.models.asset import Asset
        for symbol in settings.ACTIVE_ASSETS:
            info = Asset.get_pip_info(symbol)
            assets_data["pip_size"].append(info["pip_size"])
            assets_data["contract_size"].append(info["contract_size"])

        assets_df = pd.DataFrame(assets_data)

        # Trading parameters
        params_data = {
            "parameter": ["initial_capital", "risk_percentage", "min_indicators", "signal_timeframe"],
            "value": [settings.INITIAL_CAPITAL, settings.RISK_PERCENTAGE, 2, "5m"]  # CAMBIO: min_indicators ahora representa min_strategies (máx. 2 por activo, ver strategy_engine.MAX_STRATEGIES_PER_ASSET)
        }
        params_df = pd.DataFrame(params_data)

        # Indicator settings
        from app.models.indicator import get_default_indicators
        indicators = get_default_indicators()
        ind_data = {
            "name": [i.name for i in indicators],
            "category": [i.category for i in indicators],
            "enabled": [i.enabled for i in indicators],
            "weight": [i.weight for i in indicators]
        }
        ind_df = pd.DataFrame(ind_data)

        with pd.ExcelWriter(self.config_file, engine="openpyxl") as writer:
            assets_df.to_excel(writer, sheet_name="Assets", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)
            ind_df.to_excel(writer, sheet_name="Indicators", index=False)

        logger.info(f"Created config file: {self.config_file}")

    async def register_signal(self, signal) -> bool:
        """Register a new signal in the Excel file."""
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")

            new_row = {
                "id": signal.id,
                "asset": signal.asset,
                "direction": signal.direction.value,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit_1": signal.take_profit_1,
                "take_profit_2": signal.take_profit_2,
                "take_profit_3": signal.take_profit_3,
                "sl_pips": signal.sl_pips,
                "tp1_pips": signal.tp1_pips,
                "tp2_pips": signal.tp2_pips,
                "tp3_pips": signal.tp3_pips,
                "lot_size": signal.lot_size,
                "timeframe": signal.timeframe,
                "indicators_met": signal.indicators_met,
                "score": signal.score,
                "status": signal.status.value,
                "session": signal.session,
                "created_at": signal.created_at.isoformat() if signal.created_at else "",
                "closed_at": "",
                "close_price": "",
                "profit_loss": 0,
                "result": "",
                "max_drawdown": 0.0,
                "risk_reward_ratio": 0.0,
                "duration_minutes": 0.0,
                "entry_hour": signal.entry_hour,
                "exit_hour": "",
                "entry_spread": signal.entry_spread,
                "entry_atr": signal.entry_atr,
                "smc_quality": getattr(signal, "smc_quality", 1.0),
                "fvg_confluence": getattr(signal, "fvg_confluence", False),
                "liquidity_sweep": getattr(signal, "liquidity_sweep", False),
                "initial_lot_size": getattr(signal, "initial_lot_size", signal.lot_size),
                "remaining_lot_size": getattr(signal, "remaining_lot_size", signal.lot_size),
                "tp1_hit": getattr(signal, "tp1_hit", False),
                "tp2_hit": getattr(signal, "tp2_hit", False),
                "breakeven_active": getattr(signal, "breakeven_active", False),
                "realized_partial_pnl": getattr(signal, "realized_partial_pnl", 0.0),
                "mt5_ticket": getattr(signal, "mt5_ticket", None),
                "strategy_id": getattr(signal, "strategy_id", None),
                "strategy_name": getattr(signal, "strategy_name", ""),
            }

            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(self.signals_file, index=False, sheet_name="Signals")
            logger.bind(module="signals").info(f"Signal {signal.id} registered in Excel")
            return True

        except Exception as e:
            logger.error(f"Error registering signal in Excel: {e}")
            return False

    # ------------------------------------------------------------------
    # Señales "Por Confirmar" (motor de estrategias: 1 de 2 confirmó)
    # ------------------------------------------------------------------
    async def register_pending_signal(self, asset: str, direction: str, details: List[str],
                                       strategy_ids: List[int], confirmed_ids: List[int],
                                       entry_price_ref: float) -> bool:
        """
        Registra (o refresca) una señal 'por confirmar' en
        senales_por_confirmar.xlsx. Si ya existe una fila PENDIENTE para el
        mismo activo+dirección, se actualiza en lugar de duplicarse.
        """
        try:
            import uuid as _uuid
            from datetime import timedelta

            df = pd.read_excel(self.pending_signals_file, sheet_name="PorConfirmar")

            pending_ids = [sid for sid in strategy_ids if sid not in confirmed_ids]
            now = datetime.now()
            expires_at = now + timedelta(minutes=settings.PENDING_SIGNALS_EXPIRY_MINUTES)

            existing_mask = (df["asset"] == asset) & (df["direction"] == direction) & (df["status"] == "PENDIENTE") if not df.empty else pd.Series([], dtype=bool)
            if not df.empty and existing_mask.any():
                idx = df[existing_mask].index[0]
                df.at[idx, "confirmed_ids"] = str(confirmed_ids)
                df.at[idx, "pending_strategy_ids"] = str(pending_ids)
                df.at[idx, "details"] = " | ".join(details)
                df.at[idx, "entry_price_ref"] = entry_price_ref
            else:
                new_row = {
                    "id": str(_uuid.uuid4())[:8],
                    "asset": asset,
                    "direction": direction,
                    "strategy_ids": str(strategy_ids),
                    "confirmed_ids": str(confirmed_ids),
                    "pending_strategy_ids": str(pending_ids),
                    "entry_price_ref": entry_price_ref,
                    "details": " | ".join(details),
                    "status": "PENDIENTE",
                    "created_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "resolved_at": "",
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            df.to_excel(self.pending_signals_file, index=False, sheet_name="PorConfirmar")
            return True
        except Exception as e:
            logger.error(f"Error registering pending signal in Excel: {e}")
            return False

    def get_open_pending_signals(self) -> List[Dict]:
        """Devuelve las filas con status == PENDIENTE (no expiradas todavía)."""
        try:
            df = pd.read_excel(self.pending_signals_file, sheet_name="PorConfirmar")
            if df.empty:
                return []
            open_df = df[df["status"] == "PENDIENTE"]
            return _sanitize_list(open_df.to_dict("records"))
        except Exception as e:
            logger.error(f"Error reading pending signals from Excel: {e}")
            return []

    def resolve_pending_signal(self, pending_id: str, new_status: str) -> bool:
        """new_status: 'CONFIRMADA' o 'EXPIRADA'."""
        try:
            df = pd.read_excel(self.pending_signals_file, sheet_name="PorConfirmar")
            mask = df["id"] == pending_id
            if not mask.any():
                return False
            # CAMBIO: si la hoja estaba vacía, pandas infiere dtype float64
            # para columnas de texto (todo NaN) -- asignar un string ahí
            # lanza ValueError. Se fuerza dtype 'object' antes de escribir.
            df["status"] = df["status"].astype("object")
            df["resolved_at"] = df["resolved_at"].astype("object")
            df.loc[mask, "status"] = new_status
            df.loc[mask, "resolved_at"] = datetime.now().isoformat()
            df.to_excel(self.pending_signals_file, index=False, sheet_name="PorConfirmar")
            return True
        except Exception as e:
            logger.error(f"Error resolving pending signal in Excel: {e}")
            return False

    async def update_signal_status(self, signal_id: str, status: str,
                                    close_price: float = 0, profit_loss: float = 0) -> bool:
        """Update signal status in Excel."""
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            
            # FORCE ALL COLUMN TYPES to avoid dtype conflicts
            # Strings
            for col in ["id", "asset", "direction", "timeframe", "status", "session", "created_at", "closed_at", "result", "entry_hour", "exit_hour"]:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace("nan", "")
            
            # Floats
            float_cols = [
                "entry_price", "stop_loss", "take_profit_1", "take_profit_2", "take_profit_3",
                "sl_pips", "tp1_pips", "tp2_pips", "tp3_pips", "lot_size", "score",
                "close_price", "profit_loss", "max_drawdown", "risk_reward_ratio", "duration_minutes",
                "entry_spread", "entry_atr"
            ]
            for col in float_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

            mask = df["id"] == str(signal_id)
            if mask.any():
                idx = df.index[mask][0]
                from app.services.signal_engine import signal_engine
                sig_obj = signal_engine.active_signals.get(signal_id)
                
                df.at[idx, "status"] = str(status)
                df.at[idx, "closed_at"] = datetime.now().isoformat()
                df.at[idx, "close_price"] = float(close_price)
                df.at[idx, "profit_loss"] = float(profit_loss)
                df.at[idx, "result"] = "WIN" if profit_loss > 0 else ("BREAKEVEN" if profit_loss == 0 else "LOSS")
                
                if sig_obj:
                    df.at[idx, "max_drawdown"] = float(sig_obj.max_drawdown)
                    df.at[idx, "risk_reward_ratio"] = float(sig_obj.risk_reward_ratio)
                    df.at[idx, "duration_minutes"] = float(sig_obj.duration_minutes)
                    df.at[idx, "exit_hour"] = str(sig_obj.exit_hour)
                    if "remaining_lot_size" in df.columns:
                        df.at[idx, "remaining_lot_size"] = float(getattr(sig_obj, "remaining_lot_size", 0.0))
                    if "tp1_hit" in df.columns:
                        df.at[idx, "tp1_hit"] = bool(getattr(sig_obj, "tp1_hit", False))
                    if "tp2_hit" in df.columns:
                        df.at[idx, "tp2_hit"] = bool(getattr(sig_obj, "tp2_hit", False))
                    if "breakeven_active" in df.columns:
                        df.at[idx, "breakeven_active"] = bool(getattr(sig_obj, "breakeven_active", False))
                    if "realized_partial_pnl" in df.columns:
                        df.at[idx, "realized_partial_pnl"] = float(getattr(sig_obj, "realized_partial_pnl", 0.0))

                df.to_excel(self.signals_file, index=False, sheet_name="Signals")
                logger.bind(module="monitoring").info(
                    f"Signal {signal_id} updated: {status} P/L: {profit_loss}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating signal in Excel: {e}")
            return False

    async def register_partial_close(
        self, signal_id: str, level: str, exit_price: float,
        closed_lot: float, leg_profit_loss: float, remaining_lot_size: float
    ) -> bool:
        """
        Registra un cierre PARCIAL (TP1/TP2) en Excel sin marcar la señal
        como cerrada del todo. La señal sigue ACTIVE hasta que se cierre el
        remanente (TP3, SL/breakeven).

        CAMBIO (fix win-rate): antes no existía el concepto de cierre
        parcial; cada señal sólo tenía un evento de cierre único y total.
        """
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")

            for col in ["lot_size", "remaining_lot_size", "realized_partial_pnl", "profit_loss"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
            for col in ["tp1_hit", "tp2_hit", "breakeven_active"]:
                if col in df.columns:
                    df[col] = df[col].fillna(False)

            mask = df["id"] == str(signal_id)
            if mask.any():
                idx = df.index[mask][0]
                if "remaining_lot_size" in df.columns:
                    df.at[idx, "remaining_lot_size"] = float(remaining_lot_size)
                if "lot_size" in df.columns:
                    df.at[idx, "lot_size"] = float(remaining_lot_size)
                if level == "TP1" and "tp1_hit" in df.columns:
                    df.at[idx, "tp1_hit"] = True
                    df.at[idx, "breakeven_active"] = True
                if level == "TP2" and "tp2_hit" in df.columns:
                    df.at[idx, "tp2_hit"] = True

                if "realized_partial_pnl" in df.columns:
                    prev = df.at[idx, "realized_partial_pnl"]
                    prev = float(prev) if pd.notna(prev) else 0.0
                    df.at[idx, "realized_partial_pnl"] = round(prev + leg_profit_loss, 2)

                df.to_excel(self.signals_file, index=False, sheet_name="Signals")
                logger.bind(module="signals").info(
                    f"Partial close registered for {signal_id} at {level}: "
                    f"closed {closed_lot} lots, P/L ${leg_profit_loss:.2f}, remaining {remaining_lot_size} lots"
                )
                return True

            return False
        except Exception as e:
            logger.error(f"Error registering partial close in Excel: {e}")
            return False

    def has_active_signal(self, asset: str, strategy_id: Optional[int] = None) -> bool:
        """
        Check if an asset has an active signal in Excel.

        CAMBIO (a pedido del usuario, 2026-08-11): parámetro opcional
        `strategy_id` para permitir que distintas estrategias operen el
        mismo activo de forma independiente durante la prueba comparativa
        (ver signal_engine._has_active_signal).
        """
        try:
            if not os.path.exists(self.signals_file):
                return False

            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            active = df[(df["asset"] == asset) & (df["status"] == "ACTIVE")]
            if strategy_id is not None and "strategy_id" in df.columns:
                active = active[active["strategy_id"] == strategy_id]
            return len(active) > 0

        except Exception:
            return False

    def get_signals_dataframe(self) -> pd.DataFrame:
        """Get all signals as DataFrame."""
        try:
            return pd.read_excel(self.signals_file, sheet_name="Signals")
        except Exception:
            return pd.DataFrame()

    def get_active_signals(self) -> List[Dict]:
        """Get active signals from Excel."""
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            active = df[df["status"] == "ACTIVE"]
            records = active.to_dict("records")
            return _sanitize_list(records)
        except Exception:
            return []

    def get_closed_signals(self, start_date: Optional[str] = None) -> List[Dict]:
        """Get closed signals, optionally filtered by date."""
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            closed = df[df["status"] != "ACTIVE"]

            if start_date:
                closed = closed[closed["closed_at"] >= start_date]

            records = closed.to_dict("records")
            return _sanitize_list(records)
        except Exception:
            return []

    def get_config(self) -> Dict:
        """Get current trading configuration."""
        try:
            # Read all available sheets
            result = {"assets": [], "parameters": {}, "indicators": []}

            # Get sheet names available in the file
            xl = pd.ExcelFile(self.config_file)
            available_sheets = xl.sheet_names

            if "Assets" in available_sheets:
                assets_df = pd.read_excel(xl, sheet_name="Assets")
                result["assets"] = _sanitize_list(assets_df.to_dict("records"))

            if "Parameters" in available_sheets:
                params_df = pd.read_excel(xl, sheet_name="Parameters")
                params_dict = {}
                for _, row in params_df.iterrows():
                    params_dict[str(row["parameter"])] = _sanitize_value(row["value"])
                result["parameters"] = params_dict
            else:
                # Return default parameters if sheet doesn't exist
                result["parameters"] = {
                    "initial_capital": settings.INITIAL_CAPITAL,
                    "risk_percentage": settings.RISK_PERCENTAGE,
                    "min_indicators": 2,  # CAMBIO: min_strategies (máx. 2 por activo)
                    "signal_timeframe": "5m"
                }

            if "Indicators" in available_sheets:
                indicators_df = pd.read_excel(xl, sheet_name="Indicators")
                result["indicators"] = _sanitize_list(indicators_df.to_dict("records"))
            else:
                # Return default indicators if sheet doesn't exist
                from app.models.indicator import get_default_indicators
                indicators = get_default_indicators()
                result["indicators"] = [
                    {"name": i.name, "category": i.category, "enabled": i.enabled, "weight": i.weight}
                    for i in indicators
                ]

            xl.close()
            return result

        except Exception as e:
            logger.error(f"Error reading config: {e}")
            # Return defaults on any error
            return {
                "assets": [{"symbol": s, "active": True} for s in settings.ACTIVE_ASSETS],
                "parameters": {
                    "initial_capital": settings.INITIAL_CAPITAL,
                    "risk_percentage": settings.RISK_PERCENTAGE,
                    "min_indicators": 2,  # CAMBIO: min_strategies (máx. 2 por activo)
                    "signal_timeframe": "5m"
                },
                "indicators": []
            }

    def update_config(self, config: Dict) -> bool:
        """Update trading configuration in Excel, preserving existing sheets."""
        try:
            # First, read existing data to preserve sheets not being updated
            existing = {}
            if os.path.exists(self.config_file):
                try:
                    xl = pd.ExcelFile(self.config_file)
                    for sheet in xl.sheet_names:
                        existing[sheet] = pd.read_excel(xl, sheet_name=sheet)
                    xl.close()
                except Exception:
                    pass

            # Prepare data to write
            sheets_to_write = {}

            # Assets sheet
            if "assets" in config:
                sheets_to_write["Assets"] = pd.DataFrame(config["assets"])
            elif "Assets" in existing:
                sheets_to_write["Assets"] = existing["Assets"]

            # Parameters sheet
            if "parameters" in config:
                params = [{"parameter": k, "value": v} for k, v in config["parameters"].items()]
                sheets_to_write["Parameters"] = pd.DataFrame(params)
            elif "Parameters" in existing:
                sheets_to_write["Parameters"] = existing["Parameters"]
            else:
                # Create default parameters if none exist
                params = [
                    {"parameter": "initial_capital", "value": settings.INITIAL_CAPITAL},
                    {"parameter": "risk_percentage", "value": settings.RISK_PERCENTAGE},
                    {"parameter": "min_indicators", "value": 2},  # CAMBIO: min_strategies (máx. 2 por activo)
                    {"parameter": "signal_timeframe", "value": "5m"}
                ]
                sheets_to_write["Parameters"] = pd.DataFrame(params)

            # Indicators sheet
            if "indicators" in config:
                sheets_to_write["Indicators"] = pd.DataFrame(config["indicators"])
            elif "Indicators" in existing:
                sheets_to_write["Indicators"] = existing["Indicators"]
            else:
                # Create default indicators if none exist
                from app.models.indicator import get_default_indicators
                indicators = get_default_indicators()
                ind_data = {
                    "name": [i.name for i in indicators],
                    "category": [i.category for i in indicators],
                    "enabled": [i.enabled for i in indicators],
                    "weight": [i.weight for i in indicators]
                }
                sheets_to_write["Indicators"] = pd.DataFrame(ind_data)

            # Write all sheets at once
            with pd.ExcelWriter(self.config_file, engine="openpyxl") as writer:
                for sheet_name, df in sheets_to_write.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            logger.info("Configuration updated in Excel")
            return True

        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return False

    def get_statistics(self) -> Dict:
        """Calculate trading statistics from Excel data."""
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")

            total = int(len(df))
            active = int(len(df[df["status"] == "ACTIVE"]))
            closed = df[df["status"] != "ACTIVE"]

            wins = int(len(closed[closed["profit_loss"] > 0]))
            losses = int(len(closed[closed["profit_loss"] < 0]))
            total_closed = int(len(closed))

            win_rate = float((wins / total_closed * 100) if total_closed > 0 else 0)
            total_profit = float(closed[closed["profit_loss"] > 0]["profit_loss"].sum())
            total_loss = float(abs(closed[closed["profit_loss"] < 0]["profit_loss"].sum()))
            profit_factor = float((total_profit / total_loss) if total_loss > 0 else 0)
            net_profit = float(total_profit - total_loss)

            return {
                "total_signals": total,
                "active_signals": active,
                "closed_signals": total_closed,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2),
                "total_profit": round(total_profit, 2),
                "total_loss": round(total_loss, 2),
                "net_profit": round(net_profit, 2),
                "profit_factor": round(profit_factor, 2)
            }

        except Exception:
            return {
                "total_signals": 0, "active_signals": 0, "closed_signals": 0,
                "wins": 0, "losses": 0, "win_rate": 0.0, "total_profit": 0.0,
                "total_loss": 0.0, "net_profit": 0.0, "profit_factor": 0.0
            }

    def get_daily_kpis(self) -> List[Dict]:
        """
        Calcula los KPIs (win rate, P/L neto, profit factor, etc.) agrupados
        por día de cierre ("corte diario"), a partir de las señales
        cerradas en signals_tracking.xlsx.

        Se usa tanto para poblar el calendario del dashboard como para
        generar el archivo daily_kpis.xlsx (ver `update_daily_kpis_file`).

        Retorna una lista de dicts, uno por día, ordenados por fecha
        ascendente. Cada dict incluye: date (YYYY-MM-DD), total_trades,
        wins, losses, win_rate, total_profit, total_loss, net_profit,
        profit_factor.
        """
        try:
            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            closed = df[df["status"] != "ACTIVE"].copy()
            if closed.empty:
                return []

            # closed_at se guarda como string ISO (datetime.isoformat()).
            # errors="coerce" descarta filas con fecha inválida/vacía en vez
            # de romper todo el cálculo.
            closed["closed_date"] = pd.to_datetime(closed["closed_at"], errors="coerce").dt.date
            closed = closed.dropna(subset=["closed_date"])
            if closed.empty:
                return []

            daily_records = []
            for day, group in closed.groupby("closed_date"):
                wins = int(len(group[group["profit_loss"] > 0]))
                losses = int(len(group[group["profit_loss"] < 0]))
                total_trades = int(len(group))
                total_profit = float(group[group["profit_loss"] > 0]["profit_loss"].sum())
                total_loss = float(abs(group[group["profit_loss"] < 0]["profit_loss"].sum()))
                net_profit = float(total_profit - total_loss)
                win_rate = float((wins / total_trades * 100) if total_trades > 0 else 0)
                profit_factor = float((total_profit / total_loss) if total_loss > 0 else 0)

                daily_records.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "total_trades": total_trades,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 2),
                    "total_profit": round(total_profit, 2),
                    "total_loss": round(total_loss, 2),
                    "net_profit": round(net_profit, 2),
                    "profit_factor": round(profit_factor, 2)
                })

            daily_records.sort(key=lambda r: r["date"])
            return daily_records

        except Exception as e:
            logger.error(f"Error calculando KPIs diarios: {e}")
            return []

    async def update_daily_kpis_file(self) -> bool:
        """
        Regenera por completo daily_kpis.xlsx a partir de los KPIs diarios
        actuales (ver `get_daily_kpis`). Se recalcula desde cero cada vez
        (no se va acumulando/parcheando) para que nunca quede desalineado
        con signals_tracking.xlsx -- el costo de recalcular es bajo incluso
        con varios cientos de días de historial.

        Se llama automáticamente desde el scheduler (cada 15 minutos y al
        cierre del día), y también puede llamarse manualmente vía el
        endpoint de la API para refrescar bajo demanda.
        """
        try:
            daily_records = self.get_daily_kpis()
            df = pd.DataFrame(daily_records) if daily_records else pd.DataFrame(
                columns=["date", "total_trades", "wins", "losses", "win_rate",
                         "total_profit", "total_loss", "net_profit", "profit_factor"]
            )
            df.to_excel(self.daily_kpis_file, index=False, sheet_name="DailyKPIs")
            logger.info(f"daily_kpis.xlsx actualizado: {len(df)} día(s) registrados.")
            return True
        except Exception as e:
            logger.error(f"Error actualizando daily_kpis.xlsx: {e}")
            return False


# Singleton instance
excel_manager = ExcelManager()
