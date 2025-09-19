

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, SubOrganization, User
from schemas import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    org = await session.get(Organization, payload.org_id)
    sub = await session.get(SubOrganization, payload.suborg_id)
    if not org or not sub or sub.org_id != payload.org_id:
        raise HTTPException(status_code=400, detail="Invalid org/suborg")

    if (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")

    user = User(org_id=payload.org_id, suborg_id=payload.suborg_id, name=payload.name, email=payload.email, role="user")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

@router.get("", response_model=list[UserOut])
async def list_users(org_id: int = Query(...), suborg_id: int = Query(...), session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(User).where(User.org_id == org_id, User.suborg_id == suborg_id).order_by(User.user_id)
    )
    return res.scalars().all()

@router.delete("/{user_id}")
async def delete_user(user_id: int = Path(...), org_id: int = Query(...), suborg_id: int = Query(...),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user or user.org_id != org_id or (user.suborg_id or 0) != suborg_id:
        raise HTTPException(status_code=404, detail="User not found in given org/suborg")
    await session.delete(user)
    await session.commit()
    return {"message": "User deleted"}
