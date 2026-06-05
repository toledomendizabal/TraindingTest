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

    def _create_signals_file(self):
        """Create the signals tracking Excel file."""
        columns = [
            "id", "asset", "direction", "entry_price", "stop_loss",
            "take_profit_1", "take_profit_2", "take_profit_3",
            "sl_pips", "tp1_pips", "tp2_pips", "tp3_pips",
            "lot_size", "timeframe", "indicators_met", "score",
            "status", "session", "created_at", "closed_at",
            "close_price", "profit_loss", "result"
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
            "value": [settings.INITIAL_CAPITAL, settings.RISK_PERCENTAGE, 6, "5m"]
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
                "result": ""
            }

            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(self.signals_file, index=False, sheet_name="Signals")
            logger.bind(module="signals").info(f"Signal {signal.id} registered in Excel")
            return True

        except Exception as e:
            logger.error(f"Error registering signal in Excel: {e}")
            return False

    async def update_signal_status(self, signal_id: str, status: str,
                                    close_price: float = 0, profit_loss: float = 0) -> bool:
        """Update signal status in Excel."""
        try:
            # Force string type for ID and status columns to avoid dtype conflicts
            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            
            # Ensure these columns are treated as objects (strings)
            for col in ["id", "status", "closed_at", "result"]:
                if col in df.columns:
                    df[col] = df[col].astype(object)

            mask = df["id"] == signal_id
            if mask.any():
                # Use .at or .loc with explicit conversion to avoid SettingWithCopyWarning or dtype issues
                idx = df.index[mask][0]
                df.at[idx, "status"] = str(status)
                df.at[idx, "closed_at"] = datetime.now().isoformat()
                df.at[idx, "close_price"] = float(close_price)
                df.at[idx, "profit_loss"] = float(profit_loss)
                df.at[idx, "result"] = "WIN" if profit_loss > 0 else "LOSS"

                df.to_excel(self.signals_file, index=False, sheet_name="Signals")
                logger.bind(module="monitoring").info(
                    f"Signal {signal_id} updated: {status} P/L: {profit_loss}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating signal in Excel: {e}")
            return False

    def has_active_signal(self, asset: str) -> bool:
        """Check if an asset has an active signal in Excel."""
        try:
            if not os.path.exists(self.signals_file):
                return False

            df = pd.read_excel(self.signals_file, sheet_name="Signals")
            active = df[(df["asset"] == asset) & (df["status"] == "ACTIVE")]
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
                    "min_indicators": 6,
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
                    "min_indicators": 6,
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
                    {"parameter": "min_indicators", "value": 6},
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


# Singleton instance
excel_manager = ExcelManager()
