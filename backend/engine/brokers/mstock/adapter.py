import asyncio
from typing import Dict, Any, List, Optional
from backend.engine.brokers.base import BrokerInterface
from backend.engine.brokers.mstock.auth import MStockAuth
from backend.logging_config import get_logger

logger = get_logger(__name__)

class MStockAdapter(BrokerInterface):
    def __init__(self):
        self.auth = MStockAuth()

    async def login(self, totp_code: str) -> bool:
        return await self.auth.login(totp_code)

    async def auto_login(self) -> bool:
        return await self.auth.auto_login()

    async def place_order(self, symbol: str, side: str, qty: int, order_type: str, price: float = 0.0) -> Dict[str, Any]:
        if not self.auth.mconnect_obj:
            return {"status": "error", "message": "SDK not initialized"}
            
        loop = asyncio.get_event_loop()
        try:
            product = "CNC" 
            mstock_order_type = "MARKET" if order_type.upper() == "MARKET" else "LIMIT"
            
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.place_order,
                "regular",
                symbol,
                "NSE",
                side.upper(),
                mstock_order_type,
                str(qty),
                product,
                "DAY",
                str(price),
                "0"
            )
            data = resp.json() if hasattr(resp, "json") else resp
            logger.info(f"Placed order for {symbol}", extra={"response": data})
            return data
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def cancel_order(self, order_id: str) -> bool:
        if not self.auth.mconnect_obj:
            return False
            
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.cancel_order,
                order_id
            )
            logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    async def get_positions(self) -> List[Dict[str, Any]]:
        if not self.auth.mconnect_obj:
            return []
            
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.get_net_position
            )
            data = resp.json() if hasattr(resp, "json") else resp
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if not self.auth.mconnect_obj:
            return {"status": "error"}
            
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.get_order_details,
                order_id
            )
            data = resp.json() if hasattr(resp, "json") else resp
            return data
        except Exception as e:
            logger.error(f"Error fetching order status {order_id}: {e}")
            return {"status": "error", "message": str(e)}

    async def get_holdings(self) -> List[Dict[str, Any]]:
        if not self.auth.mconnect_obj:
            return []
            
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.get_holdings
            )
            data = resp.json() if hasattr(resp, "json") else resp
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.error(f"Error fetching holdings: {e}")
            return []

    async def get_historical_data(
        self,
        exchange: str,
        token: str,
        interval: str,
        from_date: str,
        to_date: str,
    ):
        """Fetch historical OHLCV candles via m.Stock get_historical_chart."""
        if not self.auth.mconnect_obj:
            return None
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.get_historical_chart,
                exchange,
                token,
                interval,
                from_date,
                to_date,
            )
            return resp
        except Exception as e:
            logger.error(f"Error fetching historical data for {token}: {e}")
            return None

    async def get_ltp(self, exchange: str, token: str) -> Optional[float]:
        """Get Last Traded Price for a symbol."""
        if not self.auth.mconnect_obj:
            return None
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self.auth.mconnect_obj.get_ltp,
                exchange,
                token,
            )
            data = resp.json() if hasattr(resp, "json") else resp
            if isinstance(data, dict):
                ltp = (
                    data.get("data", {}).get("ltp")
                    or data.get("ltp")
                    or data.get("last_price")
                )
                return float(ltp) if ltp else None
            return None
        except Exception as e:
            logger.error(f"Error fetching LTP for {token}: {e}")
            return None

