import asyncio
from loguru import logger
from app.services.signal_engine import SignalEngine
from app.models.asset import ASSET_CATALOG

# Configure logger to show DEBUG messages
logger.remove()
logger.add(lambda msg: print(msg, end=''), level="DEBUG")

async def run_analysis():
    signal_engine = SignalEngine()
    # Choose an asset to test, e.g., XAUUSD
    asset_to_test = "XAUUSD"
    
    # Ensure the asset is in the catalog
    if asset_to_test not in ASSET_CATALOG:
        logger.error(f"Asset {asset_to_test} not found in ASSET_CATALOG.")
        return

    logger.info(f"Running single analysis for {asset_to_test}...")
    signal = await signal_engine.analyze_asset(asset_to_test)

    if signal:
        logger.info(f"Signal generated: {signal.direction} for {signal.asset} at {signal.entry_price}")
    else:
        logger.info(f"No signal generated for {asset_to_test}.")

if __name__ == "__main__":
    asyncio.run(run_analysis())
