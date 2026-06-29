import asyncio
from datetime import datetime, timezone
from backend.logging_config import get_logger
from backend.database.database import AsyncSessionLocal
from backend.database import crud
from sqlalchemy.future import select
from backend.database.models import PaperTrade, User

logger = get_logger(__name__)

class DBTradeRecorder:
    """
    Subscribes to trading events and persists them to the paper_trades database table
    so they are visible in the frontend Trades tab.
    """
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.event_bus.subscribe("on_trade_executed", self.handle_entry)
        self.event_bus.subscribe("on_trade_exited", self.handle_exit)

    async def _get_admin_user_id(self, db) -> int:
        """Find the first admin user to assign these automated trades to."""
        stmt = select(User).where(User.role == "admin").limit(1)
        res = await db.execute(stmt)
        user = res.scalars().first()
        return user.id if user else 1

    async def handle_entry(self, data: dict) -> None:
        try:
            async with AsyncSessionLocal() as db:
                user_id = await self._get_admin_user_id(db)
                await crud.create_paper_trade(
                    db=db,
                    user_id=user_id,
                    symbol=data["symbol"],
                    entry_price=data["entry_price"],
                    sl=data["sl"],
                    target=data["target"],
                    qty=data["qty"],
                    entry_time=datetime.now(timezone.utc)
                )
        except Exception as e:
            logger.error(f"Failed to record trade entry to DB: {e}")

    async def handle_exit(self, data: dict) -> None:
        try:
            async with AsyncSessionLocal() as db:
                user_id = await self._get_admin_user_id(db)
                # Find the open trade for this symbol
                stmt = select(PaperTrade).where(
                    PaperTrade.symbol == data["symbol"],
                    PaperTrade.status == "OPEN"
                )
                result = await db.execute(stmt)
                trade = result.scalars().first()
                if trade:
                    await crud.close_trade(
                        db=db,
                        user_id=user_id,
                        trade_id=trade.id,
                        exit_price=data["exit_price"],
                        exit_time=datetime.now(timezone.utc),
                        exit_reason=data["exit_reason"]
                    )
        except Exception as e:
            logger.error(f"Failed to record trade exit to DB: {e}")
