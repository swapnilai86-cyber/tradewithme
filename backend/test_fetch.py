import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from backend.engine.brokers.mstock.adapter import MStockAdapter

async def run():
    with open('/app/config/mstock_session.json', 'r') as f:
        sess = json.load(f)
        
    adapter = MStockAdapter()
    await adapter.auth.auto_login()
    mconnect = adapter.auth.mconnect_obj
    
    # RELIANCE token is 2885 on NSE
    token = "2885"
    interval = "15minute"
    lookback_days = 30
    
    from_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"Fetching candles for token {token} from {from_date} to {to_date}")
    try:
        resp = mconnect.get_historical_chart("NSE", token, interval, from_date, to_date)
        print("Response type:", type(resp))
        if hasattr(resp, "json"):
            data = resp.json()
            print("Response JSON keys:", data.keys() if isinstance(data, dict) else "List")
            if isinstance(data, dict):
                candles = data.get("data") or data.get("candles") or data.get("result")
                print("Extracted candles length:", len(candles) if candles else "None")
                print("Candles object type:", type(candles))
                print("Candles contents:", candles)
            elif isinstance(data, list):
                print("List length:", len(data))
                if len(data) > 0:
                    print("First candle:", data[0])
        else:
            print("Response text:", resp.text if hasattr(resp, "text") else resp)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(run())
