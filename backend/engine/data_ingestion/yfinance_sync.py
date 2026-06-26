import os
import asyncio
import yfinance as yf
import pandas as pd
from backend.logging_config import get_logger
from backend.engine.brokers.mstock.instruments import NiftyInstruments

logger = get_logger(__name__)

CACHE_DIR = "/app/data/historical"

async def sync_offline_data_from_yfinance():
    """
    Downloads historical 15m and Daily data for Nifty 500 stocks from Yahoo Finance.
    Saves them as CSVs to be used by the PollingScanner in offline mode.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    logger.info("Starting Yahoo Finance offline data sync...")
    
    # Get Nifty 500 symbols
    instruments = NiftyInstruments()
    await instruments.sync(mconnect_obj=None)
    symbols = instruments.nifty500_symbols
    
    if not symbols:
        logger.error("No symbols found to sync.")
        return
        
    logger.info(f"Syncing data for {len(symbols)} symbols...")
    
    loop = asyncio.get_running_loop()
    
    def fetch_and_save(sym):
        yf_sym = f"{sym}.NS"
        try:
            ticker = yf.Ticker(yf_sym)
            
            # 15 minute data (max 60 days on YF)
            df_15m = ticker.history(interval="15m", period="60d")
            if not df_15m.empty:
                df_15m = df_15m.reset_index()
                # Rename columns to match scanner expectations
                df_15m = df_15m.rename(columns={
                    "Datetime": "datetime",
                    "Date": "datetime",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume"
                })
                # Ensure datetime column exists
                if "datetime" in df_15m.columns:
                    df_15m = df_15m[["datetime", "open", "high", "low", "close", "volume"]]
                    if df_15m["datetime"].dt.tz is None:
                        df_15m["datetime"] = df_15m["datetime"].dt.tz_localize("UTC")
                    df_15m.to_csv(os.path.join(CACHE_DIR, f"{sym}_15minute.csv"), index=False)
            
            # Daily data (1.5 years for 300+ trading days)
            df_day = ticker.history(interval="1d", period="2y")
            if not df_day.empty:
                df_day = df_day.reset_index()
                df_day = df_day.rename(columns={
                    "Date": "datetime",
                    "Datetime": "datetime",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume"
                })
                if "datetime" in df_day.columns:
                    df_day = df_day[["datetime", "open", "high", "low", "close", "volume"]]
                    if df_day["datetime"].dt.tz is None:
                        df_day["datetime"] = df_day["datetime"].dt.tz_localize("UTC")
                    df_day.to_csv(os.path.join(CACHE_DIR, f"{sym}_day.csv"), index=False)
                
        except Exception as e:
            logger.debug(f"Failed to fetch YF data for {sym}: {e}")

    for i, sym in enumerate(symbols):
        await loop.run_in_executor(None, fetch_and_save, sym)
        if i > 0 and i % 50 == 0:
            logger.info(f"YF Sync Progress: {i}/{len(symbols)}...")
        await asyncio.sleep(0.5) # Be nice to Yahoo Finance API
            
    logger.info("Yahoo Finance offline data sync completed successfully.")
