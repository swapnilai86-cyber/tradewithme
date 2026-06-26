import asyncio
from backend.database.database import AsyncSessionLocal
from backend.database import crud
from backend.app.security import get_password_hash
from backend.database.models import User

async def create_initial_user():
    async with AsyncSessionLocal() as session:
        db_user = await crud.get_user_by_username(session, username="admin")
        if not db_user:
            hashed_password = get_password_hash("admin123")
            new_user = User(
                email="admin@example.com",
                username="admin",
                password_hash=hashed_password,
                role="admin"
            )
            session.add(new_user)
            await session.commit()
            print("User 'admin' created with password 'admin123'")
        else:
            print("User 'admin' already exists with password 'admin123'")

if __name__ == "__main__":
    asyncio.run(create_initial_user())
