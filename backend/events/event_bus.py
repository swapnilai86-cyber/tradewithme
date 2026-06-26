import asyncio
from typing import Callable, Dict, List
from backend.logging_config import get_logger

logger = get_logger(__name__)

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        logger.info(f"Subscribed to event: {event_type}")

    async def publish(self, event_type: str, data: dict):
        if event_type in self.subscribers:
            logger.debug(f"Publishing event: {event_type}")
            tasks = [asyncio.create_task(cb(data)) for cb in self.subscribers[event_type]]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
