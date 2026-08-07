"""
Auto-diagnóstico de conectividad MT5. Ejecutar directamente en la máquina
donde corre (o debería correr) el backend en modo "online":

    python3 scripts/diagnostico_mt5.py

No requiere el resto del proyecto instalado -- solo el paquete
`MetaTrader5` y, opcionalmente, un archivo `.env` en el mismo directorio.
Ver docs/DIAGNOSTICO_MT5.md para la explicación completa de cada paso.
"""
import os
import sys


def check_step(name):
    print(f"\n{'='*70}\n{name}\n{'='*70}")


def main():
    check_step("1. ¿Se puede importar el paquete MetaTrader5?")
    try:
        import MetaTrader5 as mt5
        print("OK: el paquete se importó correctamente.")
        print(f"    Versión: {getattr(mt5, '__version__', 'desconocida')}")
    except ImportError as e:
        print("FALLÓ: no se pudo importar MetaTrader5.")
        print(f"    Error: {e}")
        print("\n    Esto casi siempre significa que estás en Linux/Mac, o que")
        print("    el paquete no está instalado (`pip install MetaTrader5`).")
        print("    Ver la sección 'Soluciones' en docs/DIAGNOSTICO_MT5.md.")
        sys.exit(1)

    check_step("2. Variables de entorno (.env)")
    live_enabled = os.getenv("MT5_LIVE_TRADING_ENABLED", "false").lower() == "true"
    login = os.getenv("MT5_LOGIN", "")
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    print(f"    MT5_LIVE_TRADING_ENABLED = {live_enabled}  {'<-- FALSO: no se enviará ninguna orden' if not live_enabled else ''}")
    print(f"    MT5_LOGIN  = {'(configurado)' if login else '(VACÍO)'}")
    print(f"    MT5_PASSWORD = {'(configurado)' if password else '(VACÍO)'}")
    print(f"    MT5_SERVER = {server or '(VACÍO)'}")
    if not (login and password and server):
        print("\n    FALTAN credenciales -- complétalas en tu .env antes de seguir.")
        sys.exit(1)

    check_step("3. ¿La terminal MT5 está abierta y se puede inicializar?")
    if not mt5.initialize():
        print(f"FALLÓ: mt5.initialize() -> {mt5.last_error()}")
        print("\n    La terminal MT5 no está abierta, no está instalada en esta")
        print("    máquina, o no se pudo comunicar por IPC. Ábrela manualmente")
        print("    primero y vuelve a correr este script.")
        sys.exit(1)
    print("OK: terminal inicializada.")

    check_step("4. Login contra el servidor del bróker")
    try:
        login_ok = mt5.login(int(login), password=password, server=server)
    except ValueError:
        print("FALLÓ: MT5_LOGIN debe ser un número (el número de cuenta), no texto.")
        mt5.shutdown()
        sys.exit(1)

    if not login_ok:
        print(f"FALLÓ: mt5.login() -> {mt5.last_error()}")
        print("\n    Verifica número de cuenta, contraseña DE TRADING (no la de")
        print("    solo lectura) y el nombre EXACTO del servidor (ej.")
        print("    'ICMarketsSC-Demo', tal como aparece en la terminal).")
        mt5.shutdown()
        sys.exit(1)

    account_info = mt5.account_info()
    print("OK: login exitoso.")
    if account_info:
        print(f"    Cuenta: {account_info.login}  Balance: {account_info.balance} {account_info.currency}")
        print(f"    Servidor: {account_info.server}   Trading permitido: {account_info.trade_allowed}")

    check_step("5. Símbolos de prueba (EURUSD y un par nuevo, ej. CHFJPY)")
    for symbol in ["EURUSD", "CHFJPY", "XAUUSD"]:
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"    {symbol}: NO encontrado tal cual -- prueba con sufijos "
                  f"del bróker (ej. '{symbol}.pro', '{symbol}m') y ajusta "
                  f"_resolve_symbol() en mt5_executor.py si hace falta.")
        else:
            print(f"    {symbol}: encontrado (visible={info.visible}, spread={info.spread})")

    check_step("6. Prueba de envío de orden (MODO SOLO LECTURA -- no se envía nada real)")
    print("    Este script NO envía órdenes reales a propósito.")
    print("    Si los pasos 1-5 salieron OK, el problema NO es de conectividad:")
    print("    revisa MT5_LIVE_TRADING_ENABLED=true y los logs de la app en el")
    print("    momento exacto en que debería haberse enviado una orden.")

    mt5.shutdown()
    print("\nDiagnóstico completo. Ver docs/DIAGNOSTICO_MT5.md para más detalle.")


if __name__ == "__main__":
    main()
