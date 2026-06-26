from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class WatchlistBase(BaseModel):
    symbol: str

class WatchlistCreate(WatchlistBase):
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None

class WatchlistOut(WatchlistBase):
    id: int
    user_id: int
    added_at: datetime
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    current_price: float = 0.0 # Augmented dynamically
    gross_pnl: float = 0.0 # Augmented dynamically
    
    class Config:
        from_attributes = True
