from datetime import datetime
import pandas as pd
from typing import Dict, List
from backend.logging_config import get_logger

logger = get_logger(__name__)

class TickAggregator:
    def __init__(self, signal_engine):
        self.signal_engine = signal_engine
        self.candles_1m: Dict[str, List[Dict]] = {}
        self.candles_15m: Dict[str, List[Dict]] = {}
        
    async def on_tick(self, symbol: str, price: float, volume: int, timestamp: int):
        # Stub: just append directly or assume tick is already a 1m close
        pass

    async def publish_15m_candle(self, symbol: str, open_p: float, high: float, low: float, close: float, volume: int, dt: datetime):
        candle = {
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "datetime": dt
        }
        if symbol not in self.candles_15m:
            self.candles_15m[symbol] = []
            
        self.candles_15m[symbol].append(candle)
        
        # Convert to DataFrame for indicator engine
        df = pd.DataFrame(self.candles_15m[symbol])
        await self.signal_engine.process_new_candle(symbol, df)
