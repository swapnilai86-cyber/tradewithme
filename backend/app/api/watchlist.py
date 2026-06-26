from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from backend.database import crud
from backend.database.database import get_db
from backend.app.dependencies import get_current_user
from backend.app.schemas.watchlist import WatchlistOut, WatchlistCreate

router = APIRouter()

@router.get("/", response_model=List[WatchlistOut])
async def get_watchlist(current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wl = await crud.get_user_watchlist(db, user_id=current_user.id)
    
    # Lazy import to avoid circular dependency
    import backend.app.main as main_app
    
    # Compute CMP and PnL
    for item in wl:
        # Defaults
        item.current_price = 0.0
        item.gross_pnl = 0.0
        
        # Try to fetch LTP if engine is running
        if main_app.trading_engine and main_app.trading_engine.is_running:
            token = main_app.trading_engine.instruments.get_token(item.symbol)
            if token:
                try:
                    ltp = await main_app.trading_engine.broker.get_ltp("NSE", token)
                    if ltp:
                        item.current_price = float(ltp)
                except Exception:
                    pass
                    
        # Calculate PnL based on Entry / Exit / CMP
        if item.entry_price:
            calc_price = item.exit_price if item.exit_price else item.current_price
            if calc_price:
                item.gross_pnl = round(calc_price - item.entry_price, 2)
                
    return wl

@router.post("/", response_model=WatchlistOut)
async def add_to_watchlist(item: WatchlistCreate, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wl = await crud.add_symbol_to_watchlist(
        db, 
        user_id=current_user.id, 
        symbol=item.symbol, 
        entry_price=item.entry_price, 
        exit_price=item.exit_price
    )
    return wl

@router.delete("/{symbol}")
async def remove_from_watchlist(symbol: str, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    success = await crud.remove_symbol_from_watchlist(db, user_id=current_user.id, symbol=symbol)
    if not success:
        raise HTTPException(status_code=404, detail="Symbol not found in watchlist")
    return {"message": "Symbol removed from watchlist"}
