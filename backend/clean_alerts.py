import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, delete
from backend.database.database import AsyncSessionLocal
from backend.database.models import SystemAlert

async def clean_duplicates():
    async with AsyncSessionLocal() as db:
        # Get all alerts
        result = await db.execute(select(SystemAlert).order_by(SystemAlert.timestamp.asc()))
        alerts = result.scalars().all()
        
        seen = {}
        to_delete = []
        
        for a in alerts:
            key = f"{a.symbol}_{a.alert_type}"
            if key not in seen:
                seen[key] = a
                continue
                
            last_alert = seen[key]
            
            # Check time difference - if within same day, it might be a duplicate
            time_diff = (a.timestamp - last_alert.timestamp).total_seconds()
            
            # For EARLY_RADAR, check 3% price diff
            if a.alert_type == "EARLY_RADAR":
                diff_pct = abs((a.price - last_alert.price) / last_alert.price) * 100
                if diff_pct <= 3.0 and time_diff < 86400: # Within 24 hours and < 3% diff
                    to_delete.append(a.id)
                else:
                    seen[key] = a # Update to latest valid alert
                    
            # For ENTRY_TRIGGER and RETEST, check target price in data
            elif a.alert_type in ["ENTRY_TRIGGER", "RETEST_REENTRY"]:
                last_target = last_alert.data.get("target", 0) if last_alert.data else 0
                curr_target = a.data.get("target", 0) if a.data else 0
                
                if last_target > 0 and curr_target > 0:
                    diff_pct = abs((curr_target - last_target) / last_target) * 100
                    if diff_pct <= 3.0 and time_diff < 86400:
                        to_delete.append(a.id)
                    else:
                        seen[key] = a
                else:
                    seen[key] = a
        
        if to_delete:
            print(f"Found {len(to_delete)} duplicate alerts. Deleting...")
            await db.execute(delete(SystemAlert).where(SystemAlert.id.in_(to_delete)))
            await db.commit()
            print("Successfully deleted duplicates.")
        else:
            print("No duplicate alerts found.")

if __name__ == "__main__":
    asyncio.run(clean_duplicates())
