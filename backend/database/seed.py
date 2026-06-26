import asyncio
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.database.database import AsyncSessionLocal
from backend.database.crud import create_user
from backend.database.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

async def seed_admin():
    async with AsyncSessionLocal() as db:
        # Check if admin exists
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalars().first()
        if not admin:
            # Policy: min 12 chars, mix of upper/lower/number/special
            hashed_pwd = get_password_hash("Admin@Swing123!") 
            await create_user(db, "admin@swingtrade.local", "admin", hashed_pwd, role="admin")
            print("Admin user created successfully.")
        else:
            print("Admin user already exists.")

if __name__ == "__main__":
    asyncio.run(seed_admin())
