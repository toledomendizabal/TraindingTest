import asyncio
from loguru import logger
from app.services.market_data import market_data_service
from app.models.asset import ASSET_CATALOG, Asset

logger.remove()
logger.add(lambda msg: print(msg, end=''), level='DEBUG')

async def run_market_data_test():
    print("=== VERIFICACIÓN DE DATOS DE MERCADO ===")
    
    test_assets = ["XAUUSD", "EURUSD", "US30"]
    
    for asset_name in test_assets:
        print(f"\n--- Probando {asset_name} ---")
        
        # Test get_price
        price_data = await market_data_service.get_price(asset_name)
        if price_data:
            print(f"Precio actual para {asset_name}: Bid={price_data.get('bid')}, Ask={price_data.get('ask')}")
            if price_data.get('bid') and price_data.get('ask'):
                spread = abs(price_data['ask'] - price_data['bid'])
                pip_info = Asset.get_pip_info(asset_name)
                pip_size = pip_info["pip_size"]
                spread_pips = round(spread / pip_size, 1)
                print(f"Spread: {spread_pips} pips")
            else:
                print("Bid/Ask no disponibles.")
        else:
            print(f"No se pudo obtener el precio para {asset_name}.")
            
        # Test get_time_series
        df = await market_data_service.get_time_series(asset_name, interval="5m", outputsize=10)
        if df is not None and not df.empty:
            print(f"Datos históricos (OHLCV) para {asset_name} (últimas 10 velas):")
            print(df.tail())
            print(f"Última vela: Open={df['open'].iloc[-1]}, High={df['high'].iloc[-1]}, Low={df['low'].iloc[-1]}, Close={df['close'].iloc[-1]}, Volume={df['volume'].iloc[-1]}")
        else:
            print(f"No se pudieron obtener datos históricos para {asset_name}.")

if __name__ == "__main__":
    asyncio.run(run_market_data_test())
