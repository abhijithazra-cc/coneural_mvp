



from fastapi import Header, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_session
from models import User

async def get_current_user(
    x_user_id_header: int | None = Header(default=None, alias="X-User-Id"),
    x_user_id_query: int | None = Query(default=None, alias="x_user_id"),
    session: AsyncSession = Depends(get_session)
) -> User:
    """
    TEMP AUTH FOR TESTING:
    - Provide X-User-Id header OR ?x_user_id=... query parameter.
    - Loads the user from DB and returns it.
    """
    x_user_id = x_user_id_header or x_user_id_query
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Provide X-User-Id header or ?x_user_id= for testing")
    user = await session.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user id")
    return user
