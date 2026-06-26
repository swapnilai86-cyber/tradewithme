import asyncio
from backend.database.database import engine
from backend.database.models import SystemAlert

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(SystemAlert.__table__.create, checkfirst=True)
    print("Table SystemAlert created.")

if __name__ == "__main__":
    asyncio.run(main())
