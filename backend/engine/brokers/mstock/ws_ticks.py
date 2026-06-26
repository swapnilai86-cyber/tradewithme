import asyncio
import os
import json
from backend.logging_config import get_logger

logger = get_logger(__name__)

class MStockTickStream:
    def __init__(self, auth, instrument_manager, aggregator):
        self.auth = auth
        self.im = instrument_manager
        self.aggregator = aggregator
        self.ws_url = os.getenv("MSTOCK_WS_URL", "wss://ws.mstock.example.com")
        self.connected = False

    async def connect(self):
        logger.info("Connecting to m.Stock tick stream...")
        self.connected = True
        # In real life, use websockets or aiohttp.ClientSession().ws_connect
        # Here we just stub it and simulate incoming ticks
        asyncio.create_task(self._simulate_ticks())

    async def _simulate_ticks(self):
        while self.connected:
            await asyncio.sleep(1) # simulate 1 tick per second
            tick = {
                "token": "1001",
                "ltp": 100.5,
                "timestamp": 1234567890
            }
            await self._on_tick(tick)

    async def _on_tick(self, tick_data):
        symbol = self.im.get_symbol(tick_data.get("token"))
        if not symbol:
            return
        
        await self.aggregator.on_tick(
            symbol=symbol,
            price=tick_data.get("ltp"),
            volume=tick_data.get("volume", 0),
            timestamp=tick_data.get("timestamp")
        )

    async def subscribe(self, tokens: list):
        logger.info(f"Subscribing to {len(tokens)} tokens")

    async def disconnect(self):
        self.connected = False
        logger.info("Disconnected tick stream")
