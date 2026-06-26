import asyncio
from backend.database.database import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN expiry_date TIMESTAMP WITH TIME ZONE;"))
            print("Successfully added expiry_date column.")
        except Exception as e:
            print(f"Column might already exist or error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
