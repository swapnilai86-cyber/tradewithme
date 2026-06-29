from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, time
from typing import List, Optional
from backend.app.dependencies import get_db, get_current_user
from backend.database.models import User, SystemAlert

router = APIRouter()

from sqlalchemy.future import select
from sqlalchemy import func
import os
import pandas as pd

def _get_cmp_from_cache(symbol: str) -> Optional[float]:
    filepath = f"/app/data/historical/{symbol}_15minute.csv"
    if os.path.exists(filepath):
        try:
            df = pd.read_csv(filepath)
            if not df.empty:
                return float(df['close'].iloc[-1])
        except Exception:
            pass
    return None

@router.get("/")
async def get_alerts(
    date: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch system alerts with pagination and optional date filter."""
    stmt = select(SystemAlert)
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            stmt = stmt.filter(SystemAlert.timestamp >= datetime.combine(target_date, time.min))
            stmt = stmt.filter(SystemAlert.timestamp <= datetime.combine(target_date, time.max))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Count total for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.order_by(SystemAlert.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    # Calculate CMP, PnL
    enriched_data = []
    total_invested = 0.0
    current_value = 0.0

    for a in alerts:
        cmp_val = _get_cmp_from_cache(a.symbol)
        gross_pnl = None
        
        # We only calculate PnL if it's an actionable signal or trade with a price
        if cmp_val and a.price and a.price > 0:
            qty = a.data.get("qty") if isinstance(a.data, dict) and "qty" in a.data else 1
            gross_pnl = (cmp_val - a.price) * qty
            
            total_invested += (a.price * qty)
            current_value += (cmp_val * qty)

        enriched_data.append({
            "id": a.id,
            "symbol": a.symbol,
            "alert_type": a.alert_type,
            "price": a.price,
            "cmp": cmp_val,
            "gross_pnl": gross_pnl,
            "message": a.message,
            "data": a.data,
            "timestamp": a.timestamp.isoformat() if a.timestamp else None
        })

    return {
        "data": enriched_data,
        "summary": {
            "total_invested": total_invested,
            "current_value": current_value
        },
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    }
