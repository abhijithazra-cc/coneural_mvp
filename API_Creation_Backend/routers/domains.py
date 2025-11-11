from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import Organization, SubOrganization, Domain
from schemas import DomainCreate, DomainOut, DomainUpdate
from Rag.ai import embeddings ,BASE_DIR
from Rag.FaissVectorstore import FaissVectorstore
#  this must exist for main.py to import
from Rag.VectorManager import vectorManager
router = APIRouter(prefix="/domains", tags=["domains"])


@router.post("", response_model=DomainOut, status_code=201)
async def create_domain(payload: DomainCreate, session: AsyncSession = Depends(get_session)):
    """Create a new domain under an org/suborg"""
    org = await session.get(Organization, payload.org_id)
    sub = await session.get(SubOrganization, payload.suborg_id)
    if not org or not sub or sub.org_id != payload.org_id:
        raise HTTPException(status_code=400, detail="Invalid org/suborg")

    exists = await session.execute(
        select(Domain).where(
            Domain.suborg_id == payload.suborg_id,
            Domain.name == payload.name
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Domain already exists in this suborg")

    dom = Domain(
        org_id=payload.org_id,
        suborg_id=payload.suborg_id,
        name=payload.name,
        description=payload.description,
    )
    session.add(dom)
    await session.commit()
    await session.refresh(dom)
    vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{payload.org_id}\\dept\\{dom.domain_id}")
    return dom


@router.get("", response_model=list[DomainOut])
async def list_domains(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    """List all domains for a given org + suborg"""
    res = await session.execute(
        select(Domain).where(
            Domain.org_id == org_id,
            Domain.suborg_id == suborg_id
        ).order_by(Domain.name)
    )
    return res.scalars().all()


@router.patch("/{domain_id}", response_model=DomainOut)
async def update_domain(domain_id: int, payload: DomainUpdate, session: AsyncSession = Depends(get_session)):
    """Update domain name/description"""
    dom = await session.get(Domain, domain_id)
    if not dom:
        raise HTTPException(status_code=404, detail="Domain not found")

    if payload.name:
        exists = await session.execute(
            select(Domain).where(
                Domain.suborg_id == dom.suborg_id,
                Domain.name == payload.name,
                Domain.domain_id != domain_id
            )
        )
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another domain with this name exists in this suborg")
        dom.name = payload.name

    if payload.description is not None:
        dom.description = payload.description

    await session.commit()
    await session.refresh(dom)
    return dom


@router.delete("/{domain_id}")
async def delete_domain(
    domain_id: int,
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    """Delete a domain from an org/suborg"""
    dom = await session.get(Domain, domain_id)
    if not dom or dom.org_id != org_id or dom.suborg_id != suborg_id:
        raise HTTPException(status_code=404, detail="Domain not found in given org/suborg")

    await session.delete(dom)
    await session.commit()
    return {"message": "Domain deleted"}
