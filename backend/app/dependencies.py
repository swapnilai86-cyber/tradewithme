from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.security import SECRET_KEY, ALGORITHM
from backend.database.database import get_db
from backend.database import crud
from backend.database.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await crud.get_user_by_username(db, username=username)
    if user is None:
        raise credentials_exception
        
    from datetime import datetime, timezone
    if user.expiry_date:
        expiry = user.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expiry:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account subscription has expired."
            )
            
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

async def get_trader_user(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["admin", "user"]:
        raise HTTPException(status_code=403, detail="Not authorized. Admin or User role required.")
    return current_user
