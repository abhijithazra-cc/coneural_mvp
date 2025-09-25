from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, SubOrganization, User
from schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])



# Create User

@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    org = await session.get(Organization, payload.org_id)
    sub = await session.get(SubOrganization, payload.suborg_id)
    if not org or not sub or sub.org_id != payload.org_id:
        raise HTTPException(status_code=400, detail="Invalid org/suborg")

    # check duplicate email
    if (await session.execute(select(User).where(User.email == payload.email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")

    user = User(
        org_id=payload.org_id,
        suborg_id=payload.suborg_id,
        name=payload.name,
        email=payload.email,
        role="user",
        isDeleted=0,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user



# List Users (with pagination + skip deleted)

@router.get("", response_model=list[UserOut])
async def list_users(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(
        select(User)
        .where(User.org_id == org_id, User.suborg_id == suborg_id, User.isDeleted == 0)
        .order_by(User.user_id)
        .offset(skip)
        .limit(limit)
    )
    return res.scalars().all()



# Update User (rename, email, role, soft delete)

@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int = Path(...),
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    payload: UserUpdate = None,
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if not user or user.org_id != org_id or (user.suborg_id or 0) != suborg_id or user.isDeleted:
        raise HTTPException(status_code=404, detail="User not found in given org/suborg")

    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        # check duplicate email
        exists = await session.execute(
            select(User).where(User.email == payload.email, User.user_id != user_id)
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another user with this email already exists")
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.isDeleted is not None:
        user.isDeleted = 1 if payload.isDeleted else 0

    await session.commit()
    await session.refresh(user)
    return user
