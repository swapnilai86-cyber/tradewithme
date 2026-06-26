from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BrokerInterface(ABC):
    @abstractmethod
    async def login(self) -> bool:
        pass

    @abstractmethod
    async def place_order(self, symbol: str, side: str, qty: int, order_type: str, price: float = 0.0) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        pass
