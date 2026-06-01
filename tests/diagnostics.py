"""System diagnostics and health check."""
import os
import sys
import asyncio
import importlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_environment():
    """Check Python environment and dependencies."""
    print("\n[1/6] Verificando entorno Python...")
    print(f"  Python version: {sys.version}")

    required_packages = [
        "fastapi", "uvicorn", "pandas", "numpy", "openpyxl",
        "httpx", "loguru", "apscheduler", "pydantic", "dotenv"
    ]

    missing = []
    for pkg in required_packages:
        try:
            if pkg == "dotenv":
                importlib.import_module("dotenv")
            else:
                importlib.import_module(pkg)
            print(f"  ✓ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"  ✗ {pkg} - NO INSTALADO")

    return len(missing) == 0


def check_env_file():
    """Check .env file configuration."""
    print("\n[2/6] Verificando archivo .env...")

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

    if not os.path.exists(env_path):
        print("  ✗ .env no encontrado")
        return False

    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TWELVE_DATA_API_KEY"
    ]

    from dotenv import dotenv_values
    config = dotenv_values(env_path)

    all_present = True
    for var in required_vars:
        if var in config and config[var]:
            print(f"  ✓ {var} = {'*' * min(len(config[var]), 10)}...")
        else:
            print(f"  ✗ {var} - NO CONFIGURADO")
            all_present = False

    return all_present


def check_directories():
    """Check required directories."""
    print("\n[3/6] Verificando directorios...")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    required_dirs = ["logs", "excel", "reports", "config", "app", "tests"]

    all_exist = True
    for d in required_dirs:
        path = os.path.join(base_dir, d)
        exists = os.path.exists(path)
        print(f"  {'✓' if exists else '✗'} {d}/")
        if not exists:
            all_exist = False
            os.makedirs(path, exist_ok=True)
            print(f"    → Creado automáticamente")

    return all_exist


def check_modules():
    """Check all application modules load correctly."""
    print("\n[4/6] Verificando módulos de la aplicación...")

    modules = [
        ("app.core.config", "Configuración"),
        ("app.models.signal", "Modelo Signal"),
        ("app.models.asset", "Modelo Asset"),
        ("app.models.indicator", "Modelo Indicator"),
        ("app.services.indicators", "Servicio Indicadores"),
        ("app.services.market_data", "Servicio Market Data"),
        ("app.services.excel_manager", "Servicio Excel"),
        ("app.services.telegram_service", "Servicio Telegram"),
        ("app.services.backtesting", "Servicio Backtesting"),
        ("app.services.scheduler", "Servicio Scheduler"),
        ("app.services.signal_engine", "Motor de Señales"),
        ("app.services.position_monitor", "Monitor de Posiciones"),
        ("app.api.router", "API Router"),
        ("app.main", "Aplicación Principal"),
    ]

    all_ok = True
    for module_path, name in modules:
        try:
            importlib.import_module(module_path)
            print(f"  ✓ {name} ({module_path})")
        except Exception as e:
            print(f"  ✗ {name} ({module_path}): {str(e)[:60]}")
            all_ok = False

    return all_ok


def check_excel_files():
    """Check Excel file integrity."""
    print("\n[5/6] Verificando archivos Excel...")

    try:
        from app.services.excel_manager import excel_manager

        # Check signals file
        if os.path.exists(excel_manager.signals_file):
            df = pd.read_excel(excel_manager.signals_file)
            print(f"  ✓ signals_tracking.xlsx ({len(df)} registros)")
        else:
            print("  ⚠ signals_tracking.xlsx - será creado al iniciar")

        # Check config file
        if os.path.exists(excel_manager.config_file):
            config = excel_manager.get_config()
            print(f"  ✓ trading_config.xlsx")
            print(f"    - Activos: {len(config.get('assets', []))}")
            print(f"    - Indicadores: {len(config.get('indicators', []))}")
        else:
            print("  ⚠ trading_config.xlsx - será creado al iniciar")

        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


async def check_api_connectivity():
    """Check external API connectivity."""
    print("\n[6/6] Verificando conectividad API...")

    try:
        import httpx
        from app.core.config import settings

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check Twelve Data
            response = await client.get(
                "https://api.twelvedata.com/price",
                params={"symbol": "EUR/USD", "apikey": settings.TWELVE_DATA_API_KEY}
            )
            if response.status_code == 200:
                data = response.json()
                if "price" in data:
                    print(f"  ✓ Twelve Data API - EUR/USD: {data['price']}")
                else:
                    print(f"  ⚠ Twelve Data API - Respuesta inesperada: {data}")
            else:
                print(f"  ✗ Twelve Data API - Status: {response.status_code}")

            # Check Telegram
            response = await client.get(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe"
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    bot_name = data["result"]["username"]
                    print(f"  ✓ Telegram Bot - @{bot_name}")
                else:
                    print(f"  ✗ Telegram Bot - Error: {data}")
            else:
                print(f"  ✗ Telegram Bot - Status: {response.status_code}")

        return True

    except Exception as e:
        print(f"  ✗ Error de conectividad: {e}")
        return False


def main():
    """Run all diagnostics."""
    import pandas as pd

    print("=" * 60)
    print("TradingSignal Pro - Diagnóstico del Sistema")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    results.append(("Entorno Python", check_environment()))
    results.append(("Archivo .env", check_env_file()))
    results.append(("Directorios", check_directories()))
    results.append(("Módulos", check_modules()))
    results.append(("Archivos Excel", check_excel_files()))

    # Run async checks
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results.append(("Conectividad API", loop.run_until_complete(check_api_connectivity())))
    loop.close()

    # Summary
    print("\n" + "=" * 60)
    print("RESUMEN DE DIAGNÓSTICO")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status} - {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ SISTEMA LISTO PARA EJECUCIÓN")
    else:
        print("⚠ SISTEMA REQUIERE ATENCIÓN")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
