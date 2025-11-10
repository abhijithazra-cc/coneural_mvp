

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, SubOrganization, Domain, User
from schemas import SuborgCreate, SuborgOut, SuborgUpdate, SuborgAdminOut
from Rag.FaissVectorstore import FaissVectorstore
from Rag.ai import embeddings,BASE_DIR
from Rag.VectorManager import vectorManager
router = APIRouter(prefix="/suborgs", tags=["suborgs"])

# Default domains added when a suborg is created
DEFAULT_DOMAINS = [
    ("HR", "Policies, leaves, payroll"),
    ("Finance", "Budgets, invoices, reimbursements"),
    ("IT", "Assets, access, security"),
    ("Operations", "Processes, SOPs, logistics"),
    ("Marketing", "Campaigns, branding, ads"),
]



# Create Suborg (with default domains + admin user)

@router.post("", response_model=SuborgOut, status_code=201)
async def create_suborg(payload: SuborgCreate, session: AsyncSession = Depends(get_session)):
    org = await session.get(Organization, payload.org_id)
    if not org or org.isDeleted:
        raise HTTPException(status_code=404, detail="Organization not found")

    exists = await session.execute(
        select(SubOrganization).where(SubOrganization.org_id == payload.org_id, SubOrganization.name == payload.name)
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Suborg already exists in this org")

    sub = SubOrganization(org_id=payload.org_id, name=payload.name, isDeleted=0)
    session.add(sub)
    await session.flush()  # get suborg_id

    # Check duplicate admin email
    if (await session.execute(select(User).where(User.email == payload.admin_email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Admin email already in use")

    # Create suborg admin
    admin_user = User(
        org_id=payload.org_id,
        suborg_id=sub.suborg_id,
        name=payload.admin_name,
        email=payload.admin_email,
        role="suborg_admin",
        isDeleted=0,
    )
    session.add(admin_user)

    
    for name, desc in DEFAULT_DOMAINS:
        dom=Domain(org_id=payload.org_id, suborg_id=sub.suborg_id, name=name, description=desc)
        session.add(dom)
        await session.flush()
        # print(dom.domain_id)
        vc=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{payload.org_id}/dept/{dom.domain_id}")
        # vc=FaissVectorstore(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{payload.org_id}/dept/{dom.domain_id}")
        # vc._load_or_create_store()


    await session.commit()
    await session.refresh(sub)
    await session.refresh(admin_user)

    return SuborgOut(
        suborg_id=sub.suborg_id,
        org_id=sub.org_id,
        name=sub.name,
        isDeleted=sub.isDeleted,
        admin=SuborgAdminOut(
            user_id=admin_user.user_id,
            name=admin_user.name,
            email=admin_user.email,
            role=admin_user.role,
        ),
    )


# List Suborgs (with pagination + skip deleted)

@router.get("", response_model=list[SuborgOut])
async def list_suborgs(
    org_id: int = Query(...),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(
        select(SubOrganization)
        .where(SubOrganization.org_id == org_id, SubOrganization.isDeleted == 0)
        .order_by(SubOrganization.suborg_id)
        .offset(skip)
        .limit(limit)
    )
    suborgs = res.scalars().all()

    results = []
    for sub in suborgs:
        q = await session.execute(
            select(User).where(
                User.org_id == sub.org_id,
                User.suborg_id == sub.suborg_id,
                User.role == "suborg_admin",
                User.isDeleted == 0,
            )
        )
        admin = q.scalar_one_or_none()
        results.append(
            SuborgOut(
                suborg_id=sub.suborg_id,
                org_id=sub.org_id,
                name=sub.name,
                isDeleted=sub.isDeleted,
                admin=SuborgAdminOut(
                    user_id=admin.user_id,
                    name=admin.name,
                    email=admin.email,
                    role=admin.role,
                ) if admin else None,
            )
        )

    return results


# Update Suborg (rename or soft delete)

@router.patch("/{suborg_id}", response_model=SuborgOut)
async def update_suborg(suborg_id: int, payload: SuborgUpdate, session: AsyncSession = Depends(get_session)):
    sub = await session.get(SubOrganization, suborg_id)
    if not sub or sub.isDeleted:
        raise HTTPException(status_code=404, detail="Suborg not found")

    if payload.name:
        exists = await session.execute(
            select(SubOrganization).where(
                SubOrganization.org_id == sub.org_id,
                SubOrganization.name == payload.name,
                SubOrganization.suborg_id != suborg_id,
            )
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another suborg with this name exists in this org")
        sub.name = payload.name

    if payload.isDeleted is not None:
        sub.isDeleted = 1 if payload.isDeleted else 0

    await session.commit()
    await session.refresh(sub)

    q = await session.execute(
        select(User).where(
            User.org_id == sub.org_id,
            User.suborg_id == sub.suborg_id,
            User.role == "suborg_admin",
            User.isDeleted == 0,
        )
    )
    admin = q.scalar_one_or_none()

    return SuborgOut(
        suborg_id=sub.suborg_id,
        org_id=sub.org_id,
        name=sub.name,
        isDeleted=sub.isDeleted,
        admin=SuborgAdminOut(
            user_id=admin.user_id,
            name=admin.name,
            email=admin.email,
            role=admin.role,
        ) if admin else None,
    )

