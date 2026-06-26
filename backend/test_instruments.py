import asyncio
import os
import sys

# Need to load env vars manually if not using docker? The docker-compose exec will have them.
from backend.engine.brokers.mstock.adapter import MStockAdapter
from backend.logging_config import get_logger
import json

async def run():
    with open('/app/config/mstock_session.json', 'r') as f:
        sess = json.load(f)
        
    adapter = MStockAdapter()
    # MConnect SDK doesn't expose a clean load-session method other than what we wrote in auth.
    await adapter.auth.auto_login()
    mconnect = adapter.auth.mconnect_obj
    
    res = mconnect.get_instruments()
    print("Response type:", type(res))
    if isinstance(res, bytes):
        print("First 100 bytes:", res[:100])
        try:
            text = res.decode('utf-8')
            print("Decoded as string, first 100 chars:", text[:100])
            data = json.loads(text)
            print("Parsed as JSON successfully. Type:", type(data))
        except Exception as e:
            print("Error parsing:", e)

if __name__ == "__main__":
    asyncio.run(run())
