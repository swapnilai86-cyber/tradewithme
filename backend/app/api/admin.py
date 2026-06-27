from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from datetime import datetime
from backend.app.dependencies import get_admin_user, get_trader_user
from backend.database.database import get_db
from backend.database.models import User
from backend.database import crud
from backend.app.schemas.user import UserCreate
from backend.app.security import get_password_hash
import backend.app.main as main_app
import asyncio
from backend.engine.data_ingestion.yfinance_sync import sync_offline_data_from_yfinance

router = APIRouter()

class ExpiryUpdate(BaseModel):
    expiry_date: datetime

class CMPFilterUpdate(BaseModel):
    mode: str
    min_val: float
    max_val: float

@router.get("/status")
async def get_status(current_user = Depends(get_trader_user)):
    if not main_app.trading_engine:
        return {"status": "starting"}
    return main_app.trading_engine.get_status()

@router.post("/totp")
async def submit_totp(totp_code: str = Body(..., embed=True), current_user = Depends(get_trader_user)):
    if not main_app.trading_engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    success = await main_app.trading_engine.connect_broker(totp_code)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid TOTP or broker error")
    return {"status": "success"}

@router.get("/users")
async def get_all_users(current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "expiry_date": u.expiry_date.isoformat() if u.expiry_date else None
        }
        for u in users
    ]

@router.post("/users/{user_id}/expiry")
async def update_user_expiry(user_id: int, expiry: ExpiryUpdate, current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.expiry_date = expiry.expiry_date
    db.add(user)
    await db.commit()
    return {"status": "success"}

@router.post("/users")
async def create_user_admin(user: UserCreate, current_user = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    db_username = await crud.get_user_by_username(db, username=user.username)
    if db_username:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    hashed_password = get_password_hash(user.password)
    new_user = await crud.create_user(db, email=user.email, username=user.username, password_hash=hashed_password, role=user.role or "viewer")
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role}

@router.post("/sync-offline-data")
async def trigger_offline_sync(current_user = Depends(get_admin_user)):
    async def run_sync_and_scan():
        await sync_offline_data_from_yfinance()
        if main_app.trading_engine and main_app.trading_engine.polling_scanner:
            main_app.trading_engine.polling_scanner.offline_mode = True
            main_app.trading_engine.polling_scanner._offline_scan_done = False
            
    asyncio.create_task(run_sync_and_scan())
    return {"status": "success", "message": "Offline data sync started in the background. Check Live Logs for progress."}

@router.post("/toggle-offline")
async def toggle_offline_mode(current_user = Depends(get_admin_user)):
    if not main_app.trading_engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    current_state = main_app.trading_engine.polling_scanner.offline_mode
    main_app.trading_engine.polling_scanner.offline_mode = not current_state
    
    if not current_state: # Means it was toggled ON
        main_app.trading_engine.polling_scanner._offline_scan_done = False
    
    state_str = "ENABLED" if not current_state else "DISABLED"
    return {"status": "success", "message": f"Offline Mode {state_str}. Scanner will adapt on the next 2-minute cycle."}

@router.get("/cmp-filter")
async def get_cmp_filter(current_user = Depends(get_admin_user)):
    if not main_app.trading_engine or not main_app.trading_engine.polling_scanner:
        return {"mode": "none", "min_val": 0.0, "max_val": 0.0}
    
    scanner = main_app.trading_engine.polling_scanner
    return {
        "mode": scanner.cmp_filter_mode,
        "min_val": scanner.cmp_filter_min,
        "max_val": scanner.cmp_filter_max
    }

@router.post("/cmp-filter")
async def set_cmp_filter(filter_update: CMPFilterUpdate, current_user = Depends(get_admin_user)):
    if not main_app.trading_engine or not main_app.trading_engine.polling_scanner:
        raise HTTPException(status_code=503, detail="Engine not ready")
    
    scanner = main_app.trading_engine.polling_scanner
    scanner.save_cmp_filter(filter_update.mode, filter_update.min_val, filter_update.max_val)
    
    return {"status": "success", "message": "Scanner CMP filter updated successfully."}