from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, User
from schemas import OrgCreate, OrgOut, OrgUpdate, OrgAdminOut
from Rag.ai import embeddings ,loader,splitter,vectorStore,retriever,llm,BASE_DIR
from Rag.FaissVectorstore import FaissVectorstore
from Rag.VectorManager import vectorManager
router = APIRouter(prefix="/orgs", tags=["organizations"])

# Create Organization



@router.post("", response_model=OrgOut, status_code=201)
async def create_org(payload: OrgCreate, session: AsyncSession = Depends(get_session)):
    # check duplicate org name
    exists = await session.execute(select(Organization).where(Organization.name == payload.name))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Organization name already exists")

    # create org
    org = Organization(name=payload.name, isDeleted=0)
    session.add(org)
    await session.flush()  # to get org_id
    
    # check duplicate admin email
    if (await session.execute(select(User).where(User.email == payload.admin_email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Admin email already in use")
    org_vector=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org.org_id}")
    # org_vector=FaissVectorstore(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org.org_id}")
    # org_vector._load_or_create_store()
    # create admin user
    admin_user = User(
        org_id=org.org_id,
        suborg_id=None,
        name="Org Admin",
        email=payload.admin_email,
        role="org_admin",
        isDeleted=0,
    )
    session.add(admin_user)
    await session.commit()
    await session.refresh(org)
    await session.refresh(admin_user)

    return OrgOut(
        org_id=org.org_id,
        name=org.name,
        isDeleted=org.isDeleted,
        admin=OrgAdminOut(
            user_id=admin_user.user_id,
            name=admin_user.name,
            email=admin_user.email,
            role=admin_user.role,
        ),
    )



# List Organizations (with pagination + skip deleted)

@router.get("", response_model=list[OrgOut])
async def list_orgs(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
):
    res = await session.execute(
        select(Organization).where(Organization.isDeleted == 0).order_by(Organization.org_id).offset(skip).limit(limit)
    )
    orgs = res.scalars().all()

    results = []
    for org in orgs:
        # get admin user for each org
        q = await session.execute(
            select(User).where(User.org_id == org.org_id, User.role == "org_admin", User.isDeleted == 0)
        )
        admin = q.scalar_one_or_none()
        results.append(
            OrgOut(
                org_id=org.org_id,
                name=org.name,
                isDeleted=org.isDeleted,
                admin=OrgAdminOut(
                    user_id=admin.user_id,
                    name=admin.name,
                    email=admin.email,
                    role=admin.role,
                ) if admin else None,
            )
        )

    return results



# Update Organization (name or soft delete)

@router.patch("/{org_id}", response_model=OrgOut)
async def update_org(org_id: int, payload: OrgUpdate, session: AsyncSession = Depends(get_session)):
    org = await session.get(Organization, org_id)
    if not org or org.isDeleted:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payload.name:
        # check duplicate name
        exists = await session.execute(
            select(Organization).where(Organization.name == payload.name, Organization.org_id != org_id)
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another organization with this name already exists")
        org.name = payload.name

    if payload.isDeleted is not None:
        org.isDeleted = 1 if payload.isDeleted else 0

    await session.commit()
    await session.refresh(org)

    # fetch current admin
    q = await session.execute(
        select(User).where(User.org_id == org.org_id, User.role == "org_admin", User.isDeleted == 0)
    )
    admin = q.scalar_one_or_none()

    return OrgOut(
        org_id=org.org_id,
        name=org.name,
        isDeleted=org.isDeleted,
        admin=OrgAdminOut(
            user_id=admin.user_id,
            name=admin.name,
            email=admin.email,
            role=admin.role,
        ) if admin else None,
    )
