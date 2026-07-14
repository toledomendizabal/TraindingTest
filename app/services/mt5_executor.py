"""
Servicio de ejecución en vivo contra un terminal MetaTrader 5 local.

======================================================================
ADVERTENCIA IMPORTANTE -- ESTE MÓDULO ENVÍA ÓRDENES REALES A MERCADO
======================================================================
Si `settings.MT5_LIVE_TRADING_ENABLED` es True y las credenciales en
.env corresponden a una cuenta REAL (no demo), las funciones de este
archivo abren, modifican y cierran posiciones con dinero real, sin
confirmación manual adicional.

Recomendaciones antes de habilitarlo:
1. Prueba primero contra una cuenta DEMO (mismo flujo, mismo código,
   servidor demo del bróker) durante al menos varios días.
2. Revisa que `lot_size`, `stop_loss` y `take_profit_*` en las señales
   generadas sean razonables para el tamaño real de tu cuenta -- el
   position sizing en signal_engine.py usa settings.INITIAL_CAPITAL /
   RISK_PERCENTAGE, que debes ajustar a tu capital REAL antes de
   operar en vivo (si esos valores no coinciden con tu cuenta real, el
   riesgo por operación calculado será incorrecto).
3. Verifica el símbolo exacto que usa tu bróker para cada activo (
   algunos brokers agregan sufijos como "EURUSD.pro" o "EURUSDm"). Este
   servicio intenta resolverlo automáticamente (`_resolve_symbol`),
   pero conviene confirmarlo manualmente la primera vez.

======================================================================
REQUISITO DE PLATAFORMA
======================================================================
El paquete oficial `MetaTrader5` de Python se conecta a una instancia
LOCAL de la terminal MT5 vía IPC -- no es una API remota / basada en
red. Esto requiere que la terminal MT5 esté instalada y abierta en la
MISMA máquina donde corre este backend. En la práctica, esto significa
Windows (el paquete no funciona de forma nativa en Linux/Mac; para
esos sistemas se necesita correr MT5 bajo Wine o usar un servidor/VM
Windows dedicado donde sí corra este backend).
"""
from typing import Optional
from loguru import logger

from app.core.config import settings
from app.models.signal import Signal, SignalDirection

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    # El paquete `MetaTrader5` no está instalado o no es compatible con
    # este sistema operativo (ej. Linux). El servicio queda deshabilitado
    # de forma segura -- todas las llamadas devuelven None/False sin
    # lanzar excepciones, para no romper el resto del sistema (que sigue
    # funcionando en modo "solo señales").
    mt5 = None
    MT5_AVAILABLE = False


class MT5ExecutorService:
    """Ejecuta señales como órdenes reales en MetaTrader 5."""

    def __init__(self):
        self._connected = False
        self._magic = settings.MT5_MAGIC_NUMBER

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Inicializa la terminal MT5 y hace login con las credenciales de .env."""
        if not settings.MT5_LIVE_TRADING_ENABLED:
            logger.info("MT5 live trading deshabilitado (MT5_LIVE_TRADING_ENABLED=false). No se conecta.")
            return False

        if not MT5_AVAILABLE:
            logger.error(
                "El paquete 'MetaTrader5' no está disponible en este sistema "
                "(¿estás en Linux/Mac sin Wine? ¿falta 'pip install MetaTrader5'?). "
                "La ejecución en vivo queda deshabilitada; el sistema sigue "
                "generando señales normalmente."
            )
            return False

        if not all([settings.MT5_LOGIN, settings.MT5_PASSWORD, settings.MT5_SERVER]):
            logger.error(
                "Faltan credenciales de MT5 en .env. Revisa MT5_LOGIN, "
                "MT5_PASSWORD y MT5_SERVER."
            )
            return False

        init_kwargs = {}
        if settings.MT5_TERMINAL_PATH:
            init_kwargs["path"] = settings.MT5_TERMINAL_PATH

        if not mt5.initialize(**init_kwargs):
            logger.error(f"mt5.initialize() falló: {mt5.last_error()}")
            return False

        try:
            login_int = int(settings.MT5_LOGIN)
        except ValueError:
            logger.error(f"MT5_LOGIN debe ser numérico, se recibió: {settings.MT5_LOGIN!r}")
            mt5.shutdown()
            return False

        authorized = mt5.login(
            login=login_int,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER,
        )
        if not authorized:
            logger.error(f"mt5.login() falló para cuenta {login_int} en {settings.MT5_SERVER}: {mt5.last_error()}")
            mt5.shutdown()
            return False

        self._connected = True
        account_info = mt5.account_info()
        if account_info is not None:
            logger.info(
                f"MT5 conectado: cuenta {account_info.login} en {settings.MT5_SERVER} "
                f"(balance ${account_info.balance:.2f}, apalancamiento 1:{account_info.leverage})"
            )
        return True

    def disconnect(self):
        """Cierra la conexión con la terminal MT5."""
        if self._connected and MT5_AVAILABLE:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 desconectado.")

    def _ensure_connected(self) -> bool:
        if not self._connected:
            return self.connect()
        return True

    # ------------------------------------------------------------------
    # Resolución de símbolo
    # ------------------------------------------------------------------
    def _resolve_symbol(self, asset: str) -> Optional[str]:
        """
        Resuelve el símbolo real usado por el bróker. Algunos brokers
        agregan sufijos (ej. 'EURUSD.pro', 'EURUSDm', 'XAUUSDc'). Se busca
        primero el símbolo exacto tal como está en `asset`, y si no existe,
        se busca uno que empiece igual entre todos los símbolos disponibles.
        """
        info = mt5.symbol_info(asset)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(asset, True)
            return asset

        all_symbols = mt5.symbols_get()
        for s in all_symbols or []:
            if s.name.upper().startswith(asset.upper()):
                mt5.symbol_select(s.name, True)
                logger.info(f"MT5: símbolo '{asset}' resuelto como '{s.name}' (sufijo del bróker)")
                return s.name

        logger.error(f"MT5: no se encontró ningún símbolo que coincida con '{asset}' en este bróker.")
        return None

    def _find_position(self, ticket: int):
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return None
        return positions[0]

    # ------------------------------------------------------------------
    # Apertura de posición
    # ------------------------------------------------------------------
    def open_position(self, signal: Signal) -> Optional[int]:
        """
        Abre una posición de mercado replicando la señal generada.

        SL se coloca en `signal.stop_loss`. TP se coloca en
        `signal.take_profit_3` (el nivel final) -- los cierres parciales en
        TP1/TP2 los ejecuta este mismo servicio cuando position_monitor
        detecta que se tocaron (ver `close_partial`), no el bróker
        directamente, para mantener el mismo comportamiento de cierre
        escalonado ya implementado internamente.

        Retorna el ticket de la posición si se ejecutó correctamente, o
        None si falló, si MT5_LIVE_TRADING_ENABLED es False, o si el
        paquete MetaTrader5 no está disponible en este sistema.
        """
        if not settings.MT5_LIVE_TRADING_ENABLED:
            return None
        if not self._ensure_connected():
            return None

        symbol = self._resolve_symbol(signal.asset)
        if symbol is None:
            return None

        order_type = mt5.ORDER_TYPE_BUY if signal.direction == SignalDirection.BUY else mt5.ORDER_TYPE_SELL

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"MT5: no se pudo obtener el precio actual de {symbol}.")
            return None
        price = tick.ask if signal.direction == SignalDirection.BUY else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": signal.lot_size,
            "type": order_type,
            "price": price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit_3,
            "deviation": settings.MT5_DEVIATION_POINTS,
            "magic": self._magic,
            "comment": f"TSPro-{signal.id}"[:31],  # MT5 limita el comentario a 31 caracteres
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"MT5: order_send devolvió None para {signal.asset}: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"MT5: orden rechazada para {signal.asset} "
                f"(retcode={result.retcode}, {result.comment})"
            )
            return None

        logger.info(
            f"MT5: posición ABIERTA {signal.asset} {signal.direction.value} "
            f"ticket={result.order} lote={signal.lot_size} @ {price}"
        )
        return result.order

    # ------------------------------------------------------------------
    # Cierre parcial (TP1 / TP2)
    # ------------------------------------------------------------------
    def close_partial(self, ticket: int, asset: str, direction: str, volume: float) -> bool:
        """Cierra parcialmente una posición abierta (usado en TP1/TP2)."""
        if not settings.MT5_LIVE_TRADING_ENABLED or not self._ensure_connected():
            return False

        symbol = self._resolve_symbol(asset)
        if symbol is None:
            return False

        position = self._find_position(ticket)
        if position is None:
            logger.error(f"MT5: no se encontró la posición {ticket} para cierre parcial.")
            return False

        close_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"MT5: no se pudo obtener el precio actual de {symbol}.")
            return False
        price = tick.bid if direction == "BUY" else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": round(min(volume, position.volume), 2),
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": settings.MT5_DEVIATION_POINTS,
            "magic": self._magic,
            "comment": "TSPro-partial",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5: cierre parcial falló para ticket {ticket}: {result}")
            return False

        logger.info(f"MT5: cierre parcial ejecutado, ticket={ticket}, volumen={volume}")
        return True

    # ------------------------------------------------------------------
    # Cierre total (SL / TP3 / breakeven)
    # ------------------------------------------------------------------
    def close_full(self, ticket: int, asset: str, direction: str, volume: float) -> bool:
        """Cierra por completo el remanente de una posición (SL, TP3, o breakeven)."""
        return self.close_partial(ticket, asset, direction, volume)

    # ------------------------------------------------------------------
    # Modificar Stop Loss (breakeven tras TP1, subir a TP1 tras TP2)
    # ------------------------------------------------------------------
    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modifica el Stop Loss de una posición abierta."""
        if not settings.MT5_LIVE_TRADING_ENABLED or not self._ensure_connected():
            return False

        position = self._find_position(ticket)
        if position is None:
            logger.error(f"MT5: no se encontró la posición {ticket} para modificar SL.")
            return False

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": new_sl,
            "tp": position.tp,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5: modificar SL falló para ticket {ticket}: {result}")
            return False

        logger.info(f"MT5: SL modificado a {new_sl} para ticket {ticket}")
        return True


mt5_executor = MT5ExecutorService()
