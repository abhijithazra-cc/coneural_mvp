from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, User
from schemas import OrgCreate, OrgOut

router = APIRouter(prefix="/orgs", tags=["organizations"])

@router.post("", response_model=OrgOut, status_code=201)
async def create_org(payload: OrgCreate, session: AsyncSession = Depends(get_session)):
    # unique org name
    if (await session.execute(select(Organization).where(Organization.name == payload.name))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Organization name already exists")

    org = Organization(name=payload.name)
    session.add(org)
    await session.flush()  # get org_id

    # ensure admin email unique
    if (await session.execute(select(User).where(User.email == payload.admin_email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Admin email already in use")

    # create org_admin user (no suborg yet)
    admin_user = User(org_id=org.org_id, suborg_id=None, name="Org Admin", email=payload.admin_email, role="org_admin")
    session.add(admin_user)

    await session.commit()
    await session.refresh(org)
    return org

@router.get("", response_model=list[OrgOut])
async def list_orgs(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Organization).order_by(Organization.org_id))
    return res.scalars().all()
