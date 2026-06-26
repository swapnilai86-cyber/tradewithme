from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from backend.database import crud
from backend.database.database import get_db
from backend.app.dependencies import get_current_user, get_admin_user
from backend.app.schemas.trade import TradeOut, TradeCreate, TradeUpdate

router = APIRouter()

import os
import pandas as pd

def _get_cmp_from_cache(symbol: str) -> Optional[float]:
    filepath = f"/app/data/historical/{symbol}_15minute.csv"
    if os.path.exists(filepath):
        try:
            # Read only the last row to be extremely fast
            df = pd.read_csv(filepath)
            if not df.empty:
                return float(df['close'].iloc[-1])
        except Exception:
            pass
    return None

@router.get("/", response_model=List[TradeOut])
async def get_trades(status: Optional[str] = None, current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    trades = await crud.get_user_paper_trades(db, user_id=current_user.id, status=status)
    
    cumulative_pnl = 0.0
    result = []
    
    for trade in trades:
        trade_dict = trade.__dict__.copy()
        
        # Calculate CMP if OPEN
        if trade.status == 'OPEN':
            trade_dict['cmp'] = _get_cmp_from_cache(trade.symbol)
            if trade_dict['cmp']:
                # Calculate current PnL based on CMP
                direction = 1 if trade.qty > 0 else -1
                trade_dict['pnl'] = (trade_dict['cmp'] - trade.entry_price) * abs(trade.qty) * direction
                trade_dict['pnl_pct'] = ((trade_dict['cmp'] - trade.entry_price) / trade.entry_price) * 100 * direction
        
        # Add to cumulative
        cumulative_pnl += (trade_dict.get('pnl') or 0.0)
        trade_dict['cumulative_pnl'] = cumulative_pnl
        
        result.append(trade_dict)
        
    return result

@router.get("/summary")
async def get_trade_summary(current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    stats = await crud.get_summary_stats(db, user_id=current_user.id)
    return stats

@router.post("/", response_model=TradeOut)
async def create_trade_manual(trade: TradeCreate, current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    new_trade = await crud.create_paper_trade(
        db=db,
        user_id=current_user.id,
        symbol=trade.symbol,
        entry_price=trade.entry_price,
        sl=trade.sl,
        target=trade.target,
        qty=trade.qty,
        entry_time=trade.entry_time
    )
    return new_trade
