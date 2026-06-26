from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import crud
from backend.database.database import get_db
from backend.app.dependencies import get_current_user

router = APIRouter()

@router.get("/")
async def get_dashboard_summary(current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wl = await crud.get_user_watchlist(db, user_id=current_user.id)
    stats = await crud.get_summary_stats(db, user_id=current_user.id)
    open_trades = await crud.get_user_paper_trades(db, user_id=current_user.id, status="OPEN")
    
    return {
        "watchlist_count": len(wl),
        "open_trades_count": len(open_trades),
        "total_pnl": stats["total_pnl"],
        "win_rate": stats["win_rate"]
    }
