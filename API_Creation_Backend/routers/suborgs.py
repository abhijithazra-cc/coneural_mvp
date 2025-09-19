from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, SubOrganization, Domain
from schemas import SuborgCreate, SuborgOut

router = APIRouter(prefix="/suborgs", tags=["suborgs"])

DEFAULT_DOMAINS = [
    ("HR", "Policies, leaves, payroll"),
    ("Finance", "Budgets, invoices, reimbursements"),
    ("IT", "Assets, access, security"),
    ("Operations", "Processes, SOPs, logistics"),
    ("Marketing", "Campaigns, branding, ads"),
]

@router.post("", response_model=SuborgOut, status_code=201)
async def create_suborg(payload: SuborgCreate, session: AsyncSession = Depends(get_session)):
    org = await session.get(Organization, payload.org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    exists = await session.execute(
        select(SubOrganization).where(SubOrganization.org_id == payload.org_id, SubOrganization.name == payload.name)
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Suborg already exists in this org")

    sub = SubOrganization(org_id=payload.org_id, name=payload.name)
    session.add(sub)
    await session.flush()

    for name, desc in DEFAULT_DOMAINS:
        session.add(Domain(org_id=payload.org_id, suborg_id=sub.suborg_id, name=name, description=desc))

    await session.commit()
    await session.refresh(sub)
    return sub

@router.get("", response_model=list[SuborgOut])
async def list_suborgs(org_id: int = Query(...), session: AsyncSession = Depends(get_session)):
    res = await session.execute(
        select(SubOrganization).where(SubOrganization.org_id == org_id).order_by(SubOrganization.suborg_id)
    )
    return res.scalars().all()
