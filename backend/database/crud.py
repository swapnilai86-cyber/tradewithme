from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func

from . import models

# --- User CRUD ---

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalars().first()

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.username == username))
    return result.scalars().first()

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[models.User]:
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    return result.scalars().first()

async def create_user(db: AsyncSession, email: str, username: str, password_hash: str, role: str = "viewer") -> models.User:
    new_user = models.User(email=email, username=username, password_hash=password_hash, role=role)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

async def update_user_role(db: AsyncSession, user_id: int, new_role: str) -> Optional[models.User]:
    user = await get_user_by_id(db, user_id)
    if user:
        user.role = new_role
        await db.commit()
        await db.refresh(user)
    return user

async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if user:
        await db.delete(user)
        await db.commit()
        return True
    return False

# --- Watchlist CRUD ---

async def get_user_watchlist(db: AsyncSession, user_id: int) -> List[models.Watchlist]:
    result = await db.execute(select(models.Watchlist).where(models.Watchlist.user_id == user_id))
    return result.scalars().all()

async def add_symbol_to_watchlist(db: AsyncSession, user_id: int, symbol: str, entry_price: Optional[float] = None, exit_price: Optional[float] = None) -> models.Watchlist:
    # check if already exists
    result = await db.execute(
        select(models.Watchlist)
        .where(models.Watchlist.user_id == user_id)
        .where(models.Watchlist.symbol == symbol)
    )
    existing = result.scalars().first()
    if existing:
        if entry_price is not None: existing.entry_price = entry_price
        if exit_price is not None: existing.exit_price = exit_price
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing
        
    wl = models.Watchlist(user_id=user_id, symbol=symbol, entry_price=entry_price, exit_price=exit_price)
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return wl

async def remove_symbol_from_watchlist(db: AsyncSession, user_id: int, symbol: str) -> bool:
    result = await db.execute(
        select(models.Watchlist)
        .where(models.Watchlist.user_id == user_id)
        .where(models.Watchlist.symbol == symbol)
    )
    wl = result.scalars().first()
    if wl:
        await db.delete(wl)
        await db.commit()
        return True
    return False

# --- Paper Trades CRUD ---

async def create_paper_trade(
    db: AsyncSession, 
    user_id: int, 
    symbol: str, 
    entry_price: float, 
    sl: float, 
    target: float, 
    qty: int, 
    entry_time: datetime
) -> models.PaperTrade:
    trade = models.PaperTrade(
        user_id=user_id,
        symbol=symbol,
        entry_price=entry_price,
        sl=sl,
        target=target,
        qty=qty,
        entry_time=entry_time,
        status="OPEN"
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    
    # Log history
    history = models.TradeHistory(
        user_id=user_id,
        paper_trades_id=trade.id,
        action="CREATE",
        details={"entry_price": entry_price, "qty": qty, "sl": sl, "target": target}
    )
    db.add(history)
    await db.commit()
    
    return trade

async def get_paper_trade_by_id(db: AsyncSession, trade_id: int) -> Optional[models.PaperTrade]:
    result = await db.execute(select(models.PaperTrade).where(models.PaperTrade.id == trade_id))
    return result.scalars().first()

async def get_user_paper_trades(db: AsyncSession, user_id: int, status: Optional[str] = None) -> List[models.PaperTrade]:
    stmt = select(models.PaperTrade).where(models.PaperTrade.user_id == user_id)
    if status:
        stmt = stmt.where(models.PaperTrade.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_visible_trades(db: AsyncSession, user_id: int) -> List[models.PaperTrade]:
    # Trades where the user_id is in the visible_to JSONB array
    # Note: asyncpg / JSONB specific query might vary, assuming simple extraction or we handle it via python filter for now if it gets complex.
    # We will use sqlalchemy func.jsonb_array_elements or contains for proper query.
    stmt = select(models.PaperTrade).where(
        models.PaperTrade.visible_to.contains([user_id])
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_trade_status(db: AsyncSession, user_id: int, trade_id: int, status: str, details: Dict[str, Any] = None) -> Optional[models.PaperTrade]:
    trade = await get_paper_trade_by_id(db, trade_id)
    if trade:
        trade.status = status
        db.add(trade)
        
        history = models.TradeHistory(
            user_id=user_id,
            paper_trades_id=trade.id,
            action="UPDATE_STATUS",
            details=details or {"new_status": status}
        )
        db.add(history)
        await db.commit()
        await db.refresh(trade)
    return trade

async def close_trade(
    db: AsyncSession, 
    user_id: int, 
    trade_id: int, 
    exit_price: float, 
    exit_time: datetime, 
    exit_reason: str
) -> Optional[models.PaperTrade]:
    trade = await get_paper_trade_by_id(db, trade_id)
    if trade and trade.status == "OPEN":
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.exit_reason = exit_reason
        trade.status = "CLOSED"
        
        # calculate pnl
        trade.pnl = (exit_price - trade.entry_price) * trade.qty
        trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        
        duration = exit_time - trade.entry_time
        trade.hold_duration_mins = int(duration.total_seconds() / 60)
        
        db.add(trade)
        
        history = models.TradeHistory(
            user_id=user_id,
            paper_trades_id=trade.id,
            action="CLOSE",
            details={
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct
            }
        )
        db.add(history)
        await db.commit()
        await db.refresh(trade)
    return trade

async def get_summary_stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    trades = await get_user_paper_trades(db, user_id, status="CLOSED")
    if not trades:
        return {"total_pnl": 0, "win_rate": 0, "total_trades": 0}
        
    wins = [t for t in trades if t.pnl and t.pnl > 0]
    total_pnl = sum(t.pnl for t in trades if t.pnl)
    win_rate = (len(wins) / len(trades)) * 100
    
    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": len(trades)
    }

# --- Audit Log CRUD ---

async def log_audit_action(
    db: AsyncSession, 
    user_id: Optional[int], 
    action: str, 
    resource_type: str = None, 
    resource_id: str = None, 
    details: Dict[str, Any] = None
) -> models.AuditLog:
    log = models.AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log

async def get_audit_logs_by_user(db: AsyncSession, user_id: int, limit: int = 100) -> List[models.AuditLog]:
    stmt = select(models.AuditLog).where(models.AuditLog.user_id == user_id).order_by(models.AuditLog.timestamp.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_all_audit_logs(db: AsyncSession, limit: int = 100) -> List[models.AuditLog]:
    stmt = select(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

# --- Alerts Preferences CRUD ---

async def get_alerts_preferences(db: AsyncSession, user_id: int) -> List[models.AlertsPreference]:
    stmt = select(models.AlertsPreference).where(models.AlertsPreference.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_alert_preference(db: AsyncSession, user_id: int, alert_type: str, enabled: bool) -> models.AlertsPreference:
    stmt = select(models.AlertsPreference).where(
        models.AlertsPreference.user_id == user_id
    ).where(models.AlertsPreference.alert_type == alert_type)
    
    result = await db.execute(stmt)
    pref = result.scalars().first()
    
    if pref:
        pref.enabled = enabled
    else:
        pref = models.AlertsPreference(user_id=user_id, alert_type=alert_type, enabled=enabled)
        db.add(pref)
        
    await db.commit()
    await db.refresh(pref)
    return pref
