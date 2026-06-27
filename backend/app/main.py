import yaml
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api import auth, watchlist, trades, dashboard, admin, logs, alerts, charts
from backend.engine.core import TradingEngineCore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.engine.data_ingestion.yfinance_sync import sync_offline_data_from_yfinance

# Global engine and scheduler instances
trading_engine = None
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global trading_engine
    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "config.yaml")
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception:
        config = {}

    trading_engine = TradingEngineCore(config)
    
    # Start the engine in the background
    asyncio.create_task(trading_engine.start())
    
    # Wrapper to sync then scan once
    async def scheduled_sync_and_scan():
        await sync_offline_data_from_yfinance()
        if trading_engine and trading_engine.polling_scanner:
            trading_engine.polling_scanner.offline_mode = True
            trading_engine.polling_scanner._offline_scan_done = False
            
    # Schedule the offline sync for 16:30 every day (Mon-Fri)
    scheduler.add_job(
        scheduled_sync_and_scan,
        'cron',
        day_of_week='mon-fri',
        hour=16,
        minute=30
    )
    scheduler.start()
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    await trading_engine.stop()

app = FastAPI(title="Swing Trading API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In prod, restrict to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["Watchlist"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(logs.router, prefix="/api/logs", tags=["Logs"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(charts.router, prefix="/api/charts", tags=["Charts"])


@app.get("/")
def read_root():
    return {"message": "Swing Trading API is running"}
