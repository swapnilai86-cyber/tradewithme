from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TradeCreate(BaseModel):
    symbol: str
    entry_price: float
    sl: float
    target: float
    qty: int
    entry_time: datetime

class TradeUpdate(BaseModel):
    status: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    visible_to: Optional[List[int]] = None

class TradeOut(TradeCreate):
    id: int
    user_id: int
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    cmp: Optional[float] = None
    cumulative_pnl: Optional[float] = None
    status: str
    hold_duration_mins: Optional[int] = None
    exit_reason: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
