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
import time
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

    def is_connected_live(self) -> bool:
        """
        CAMBIO (a pedido del usuario, 2026-08-12 -- "que el motor de
        conexión con MT5 siga operable"): antes, `_ensure_connected()`
        solo miraba la bandera interna `self._connected` (un bool en
        memoria) -- si la terminal MT5 se desconectaba por su cuenta (caída
        de red, reinicio de la terminal, sesión expirada del bróker), esa
        bandera se quedaba en `True` para siempre y el sistema asumía que
        todo seguía bien, sin volver a intentar reconectar jamás hasta que
        el proceso de Python se reiniciara por completo. Resultado: las
        señales se seguían generando con normalidad, pero
        `mt5.order_send()` fallaba en silencio (o con errores poco claros)
        indefinidamente.

        Este método SÍ verifica el estado real de la conexión contra la
        terminal (no solo la bandera en memoria), llamando a
        `mt5.terminal_info()` -- que solo devuelve datos válidos si la
        terminal sigue efectivamente conectada al servidor del bróker.
        """
        if not MT5_AVAILABLE or not self._connected:
            return False
        try:
            info = mt5.terminal_info()
            return info is not None and bool(getattr(info, "connected", False))
        except Exception as e:
            logger.warning(f"MT5: error verificando estado de conexión: {e}")
            return False

    def _ensure_connected(self) -> bool:
        # CAMBIO (fix, 2026-08-12): ya no confía ciegamente en
        # `self._connected` -- verifica la conexión real y reconecta si
        # hace falta (ver `is_connected_live`).
        if self.is_connected_live():
            return True
        logger.info("MT5: conexión no activa o perdida, reconectando...")
        self._connected = False
        return self.connect()

    def health_check(self) -> bool:
        """
        CAMBIO (a pedido del usuario, 2026-08-12): chequeo proactivo de
        conectividad, pensado para llamarse periódicamente desde
        `scheduler.py` (cada pocos minutos) en vez de esperar a que una
        señal necesite abrir una operación para descubrir que la conexión
        se había caído. Si `MT5_LIVE_TRADING_ENABLED` es False, no hace
        nada (comportamiento normal en modo "solo señales").
        """
        if not settings.MT5_LIVE_TRADING_ENABLED or not MT5_AVAILABLE:
            return False
        if self.is_connected_live():
            return True
        logger.warning("MT5: chequeo de salud detectó conexión caída -- reconectando...")
        return self.connect()

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
    # Modo de ejecución (filling mode) y distancia mínima de stops
    # ------------------------------------------------------------------
    def _get_filling_mode(self, symbol: str):
        """
        CAMBIO CRÍTICO (fix, 2026-08-19 -- análisis de 6 días de logs
        reales: 84 de 108 rechazos de MT5, el 78%, fueron
        "retcode=10030 Unsupported filling mode"): antes se mandaba
        SIEMPRE `mt5.ORDER_FILLING_IOC` sin importar qué modo soporta
        realmente el símbolo en ESTE bróker -- cada símbolo/cuenta define
        qué modos de ejecución acepta (`symbol_info().filling_mode`, un
        bitmask de FOK / IOC), y IOC no es universal. Esto explica por
        qué solo XAUUSD llegó a registrarse en MT5 (y solo 1 vez de
        varios intentos): fue la única combinación donde, por casualidad,
        el modo del bróker coincidía con IOC.

        Se detecta el modo soportado consultando `symbol_info` en vez de
        asumirlo. Orden de preferencia: FOK, luego IOC, y si el símbolo no
        reporta ninguno de los dos (algunos símbolos exchange-traded solo
        aceptan RETURN), se usa ORDER_FILLING_RETURN como último recurso.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return mt5.ORDER_FILLING_IOC  # fallback si no se pudo consultar

        filling = info.filling_mode
        # SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2 (bitmask)
        if filling & 1:  # SYMBOL_FILLING_FOK
            return mt5.ORDER_FILLING_FOK
        if filling & 2:  # SYMBOL_FILLING_IOC
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def _send_order_with_filling_retry(self, request: dict, symbol: str):
        """
        Envía la orden con el modo de ejecución detectado para el símbolo.
        Si el bróker de todas formas la rechaza por "Unsupported filling
        mode" (puede pasar si `symbol_info` reporta un bitmask que no
        coincide 100% con lo que la cuenta acepta en la práctica -- se vio
        en algunos brokers), se reintenta probando los otros 2 modos en
        orden, en vez de rendirse en el primer intento.
        """
        request["type_filling"] = self._get_filling_mode(symbol)
        result = mt5.order_send(request)

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            return result

        if result is not None and result.retcode == 10030:  # Unsupported filling mode
            tried = {request["type_filling"]}
            for candidate in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
                if candidate in tried:
                    continue
                tried.add(candidate)
                logger.info(f"MT5: reintentando {symbol} con modo de ejecución alterno ({candidate})...")
                request["type_filling"] = candidate
                result = mt5.order_send(request)
                if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return result

        return result

    def _validate_and_adjust_stops(self, symbol: str, direction: str, price: float,
                                    sl: float, tp: float, volume: float):
        """
        CAMBIO (fix, 2026-08-19 -- 19 de 108 rechazos, el 18%, fueron
        "retcode=10016 Invalid stops", concentrados en XAUUSD): cada
        símbolo tiene una distancia MÍNIMA obligatoria entre el precio
        actual y el SL/TP (`symbol_info().trade_stops_level`, en puntos).
        Si nuestro SL/TP calculado internamente (basado en ATR/pips) cae
        más cerca que ese mínimo, el bróker rechaza la orden completa --
        no se abre nada, ni siquiera con el SL "incorrecto".

        Si detecta que el SL queda demasiado cerca, lo ALEJA lo mínimo
        necesario para cumplir el requisito del bróker, y reduce el
        volumen proporcionalmente para mantener el mismo riesgo en dinero
        que se calculó originalmente (una distancia de SL mayor con el
        mismo volumen implicaría arriesgar MÁS dinero del calculado, no
        menos -- por eso el volumen se ajusta hacia abajo, nunca al revés).
        Este ajuste es SOLO para la orden real enviada al bróker; el
        `stop_loss`/`take_profit_3` guardados en la señal (Excel,
        backtesting) no cambian.

        CAMBIO CRÍTICO (fix, 2026-09-05): el fix anterior SOLO validaba el
        SL -- nunca el TP. Con logs reales de la semana del 2-5/09 se
        siguieron viendo 28 rechazos "Invalid stops" en 6 activos
        distintos (NZDUSD, USDJPY, GBPUSD, USDCHF, EURUSD, AUDUSD) --
        varios de ellos con SL de sobra, así que el TP (take_profit_3,
        el nivel que se manda al bróker) era el que realmente violaba el
        mínimo. Ahora se valida y ajusta también el TP -- alejarlo NO
        requiere tocar el volumen (agrandar la ganancia potencial no
        aumenta el riesgo). También se agrega un pequeño margen de
        seguridad extra (2 puntos en vez de 1) para absorber el
        deslizamiento natural entre el precio que consultamos y el precio
        real de ejecución un instante después.

        Retorna (sl_ajustado, tp_ajustado, volumen_ajustado).
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return sl, tp, volume

        min_distance = info.trade_stops_level * info.point
        if min_distance <= 0:
            return sl, tp, volume

        safety_margin = 2 * info.point  # antes 1 punto, ahora 2 por deslizamiento
        adjusted_sl, adjusted_volume = sl, volume
        adjusted_tp = tp

        # --- Validar/ajustar SL ---
        current_sl_distance = abs(price - sl)
        if current_sl_distance < min_distance:
            adjusted_sl_distance = min_distance + safety_margin
            if direction == "BUY":
                adjusted_sl = round(price - adjusted_sl_distance, info.digits)
            else:
                adjusted_sl = round(price + adjusted_sl_distance, info.digits)

            # Reduce el volumen proporcionalmente para mantener el mismo
            # riesgo en dinero ($ = pips_riesgo * pip_value * volumen).
            volume_step = info.volume_step or 0.01
            adjusted_volume = volume * (current_sl_distance / adjusted_sl_distance)
            adjusted_volume = max(info.volume_min, round(adjusted_volume / volume_step) * volume_step)

            logger.warning(
                f"MT5: SL de {symbol} estaba a {current_sl_distance:.5f} del precio, por debajo "
                f"del mínimo del bróker ({min_distance:.5f}). Se alejó a {adjusted_sl_distance:.5f} "
                f"y se redujo el volumen de {volume} a {adjusted_volume} para mantener el mismo "
                f"riesgo en dinero calculado originalmente."
            )

        # --- Validar/ajustar TP (CAMBIO CRÍTICO, 2026-09-05) ---
        current_tp_distance = abs(price - tp)
        if current_tp_distance < min_distance:
            adjusted_tp_distance = min_distance + safety_margin
            if direction == "BUY":
                adjusted_tp = round(price + adjusted_tp_distance, info.digits)
            else:
                adjusted_tp = round(price - adjusted_tp_distance, info.digits)

            logger.warning(
                f"MT5: TP de {symbol} estaba a {current_tp_distance:.5f} del precio, por debajo "
                f"del mínimo del bróker ({min_distance:.5f}). Se alejó a {adjusted_tp_distance:.5f} "
                f"(alejar el TP no cambia el riesgo, no hace falta ajustar el volumen)."
            )

        return adjusted_sl, adjusted_tp, adjusted_volume

    # ------------------------------------------------------------------
    # Apertura de posición
    # ------------------------------------------------------------------
    def _reconcile_possible_ghost_fill(self, symbol: str, expected_comment: str) -> Optional[int]:
        """
        CAMBIO CRÍTICO (fix, 2026-08-29 -- análisis cruzado de
        signals_tracking.xlsx contra el reporte real de MT5,
        ReportHistory-110537430.xlsx): se encontraron 9 señales que
        nuestro propio log marcó como "la orden real NO pudo enviarse al
        bróker" -- pero que en el reporte REAL de MT5 sí aparecen como
        posiciones abiertas y cerradas con normalidad, con el comentario
        exacto `TSPro-{signal.id}` que nosotros mismos les pusimos (ej.
        señal `c99d230c` en EURGBP, ticket real 10141863365, -$37.50).

        Esto es un problema clásico de "ack perdido": `mt5.order_send()`
        puede devolver `None` o un error de timeout/conexión aunque el
        bróker SÍ haya procesado la orden del lado del servidor -- la
        respuesta se pierde en el camino, pero la operación ya existe.
        Antes, cuando esto pasaba, dábamos la señal por perdida (sin
        ticket, sin gestión de cierre parcial/breakeven) mientras en la
        vida real SÍ había una posición real abierta y sin supervisión
        de nuestro lado -- justo el síntoma reportado: "solo algunas
        operaciones se manifiestan en MetaTrader 5" (en realidad SÍ se
        manifestaban casi todas, pero nuestro propio sistema las daba por
        fallidas y dejaba de rastrearlas).

        Antes de rendirse, se busca en las posiciones abiertas actuales
        del símbolo una que tenga EXACTAMENTE el comentario que le
        pusimos a esta señal -- si aparece, es la "ghost fill": se
        recupera su ticket real en vez de perderla.
        """
        try:
            positions = mt5.positions_get(symbol=symbol)
            if positions:
                for p in positions:
                    if p.comment == expected_comment:
                        logger.warning(
                            f"MT5: se recuperó un 'ghost fill' -- la orden para {symbol} había "
                            f"parecido fallar (timeout/sin respuesta), pero SÍ existe una posición "
                            f"real abierta con ticket={p.ticket} y el comentario esperado "
                            f"'{expected_comment}'. Se recupera su seguimiento."
                        )
                        return p.ticket

            # Puede que el fill del bróker todavía no se refleje en el
            # instante exacto del timeout -- un segundo reintento breve
            # tras una pausa corta antes de darse por vencido de verdad.
            time.sleep(1.5)
            positions = mt5.positions_get(symbol=symbol)
            if positions:
                for p in positions:
                    if p.comment == expected_comment:
                        logger.warning(
                            f"MT5: se recuperó un 'ghost fill' (2do intento, tras pausa) para "
                            f"{symbol} -- ticket={p.ticket}, comentario '{expected_comment}'."
                        )
                        return p.ticket
        except Exception as e:
            logger.error(f"MT5: error al verificar 'ghost fill' para {symbol}: {e}")
        return None

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

        # CAMBIO (fix, 2026-08-19, ampliado 2026-09-05): valida y ajusta
        # SL, TP y volumen si hace falta ANTES de armar la orden (ver
        # `_validate_and_adjust_stops` -- causa de los rechazos "Invalid
        # stops" en logs reales). CAMBIO CRÍTICO: antes solo se ajustaba
        # el SL pero se seguía mandando `signal.take_profit_3` SIN ajustar
        # en el campo "tp" de la orden -- si el TP era el que violaba la
        # distancia mínima (visto en 28 rechazos reales de la semana del
        # 2-5/09 en 6 activos distintos), el ajuste del SL no servía de
        # nada porque la orden se rechazaba igual por el TP.
        adjusted_sl, adjusted_tp, adjusted_volume = self._validate_and_adjust_stops(
            symbol, signal.direction.value, price, signal.stop_loss, signal.take_profit_3, signal.lot_size
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": adjusted_volume,
            "type": order_type,
            "price": price,
            "sl": adjusted_sl,
            "tp": adjusted_tp,
            "deviation": settings.MT5_DEVIATION_POINTS,
            "magic": self._magic,
            "comment": f"TSPro-{signal.id}"[:31],  # MT5 limita el comentario a 31 caracteres
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # CAMBIO CRÍTICO (fix, 2026-08-19): antes se mandaba SIEMPRE
        # ORDER_FILLING_IOC hardcodeado -- causa del 78% de los rechazos
        # reales ("Unsupported filling mode"). Ver `_send_order_with_filling_retry`.
        expected_comment = f"TSPro-{signal.id}"[:31]
        result = self._send_order_with_filling_retry(request, symbol)
        if result is None:
            logger.error(f"MT5: order_send devolvió None para {signal.asset}: {mt5.last_error()}")
            recovered = self._reconcile_possible_ghost_fill(symbol, expected_comment)
            if recovered:
                return recovered
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"MT5: orden rechazada para {signal.asset} "
                f"(retcode={result.retcode}, {result.comment})"
            )
            recovered = self._reconcile_possible_ghost_fill(symbol, expected_comment)
            if recovered:
                return recovered
            return None

        logger.info(
            f"MT5: posición ABIERTA {signal.asset} {signal.direction.value} "
            f"ticket={result.order} lote={adjusted_volume} @ {price}"
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
        }
        # CAMBIO (fix, 2026-08-19): mismo fix de filling mode que en
        # open_position -- ver `_send_order_with_filling_retry`.
        result = self._send_order_with_filling_retry(request, symbol)
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
