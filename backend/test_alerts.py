import asyncio
from datetime import datetime, time
import os
import sys

# Add backend to path
sys.path.append("/app")

from backend.database.database import AsyncSessionLocal
from backend.database.models import SystemAlert
from sqlalchemy.future import select

async def main():
    async with AsyncSessionLocal() as db:
        target_date = datetime.strptime("2026-06-26", "%Y-%m-%d").date()
        print("Target date:", target_date)
        
        # Get all alerts count without filter
        res = await db.execute(select(SystemAlert))
        all_alerts = res.scalars().all()
        print(f"Total alerts in DB: {len(all_alerts)}")
        
        # Test the filter logic
        dt_min = datetime.combine(target_date, time.min)
        dt_max = datetime.combine(target_date, time.max)
        
        stmt = select(SystemAlert).filter(
            SystemAlert.timestamp >= dt_min,
            SystemAlert.timestamp <= dt_max
        )
        res = await db.execute(stmt)
        filtered = res.scalars().all()
        print(f"Filtered alerts (naive): {len(filtered)}")
        
if __name__ == "__main__":
    asyncio.run(main())
