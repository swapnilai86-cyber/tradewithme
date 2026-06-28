import asyncio
import os
import yaml
import logging
from backend.engine.signals.scanner import SignalScanner
from backend.engine.data_ingestion.polling_scanner import PollingScanner
from backend.engine.core import TradingEngineCore

# Force DEBUG logs
os.environ["LOG_LEVEL"] = "DEBUG"

async def main():
    print("=== STARTING SCANNER DEBUG MODE ===")
    
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Initialize Engine just to wire things up
    engine = TradingEngineCore(config)
    
    # Run the offline sync to ensure we have data
    print("Syncing data (this might take a moment)...")
    from backend.engine.data_ingestion.yfinance_sync import sync_offline_data_from_yfinance
    await sync_offline_data_from_yfinance()
    
    print("Running a single offline scan...")
    engine.polling_scanner.offline_mode = True
    await engine.polling_scanner._scan_cycle()
    
    print("\n=== SCAN COMPLETE ===")
    print("Check the DEBUG output above to see exactly which conditions failed for each stock.")

if __name__ == "__main__":
    asyncio.run(main())
