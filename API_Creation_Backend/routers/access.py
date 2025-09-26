


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from db import get_session
from models import User, Domain, UserDomainAccess
from schemas import AccessGrant, AccessOut, UserOut, AdminTarget  # <- add AdminTarget in schemas.py
from auth_dep import get_current_user

router = APIRouter(prefix="/access", tags=["access"])


# ---------- helpers ----------
def _is_org_admin(u: User) -> bool:
    return (u.role or "").lower() == "org_admin"


def _is_suborg_admin(u: User) -> bool:
    return (u.role or "").lower() == "suborg_admin"


async def _ensure_same_org(session: AsyncSession, user: User, domain_id: int) -> Domain:
    dom = await session.get(Domain, domain_id)
    if not dom:
        raise HTTPException(status_code=404, detail="Domain not found")
    if dom.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Cross-org operation not allowed")
    return dom



#  Access mapping (grant / revoke / list)


@router.post("/grant", response_model=AccessOut, status_code=201)
async def grant_access(
    payload: AccessGrant,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(get_current_user),
):
    """
    Grant a user access to a domain.
    - org_admin: can grant for any domain in their org
    - suborg_admin: can grant only for domains in their own suborg
    """
    target = await session.get(User, payload.user_id)
    if not target or target.isDeleted:
        raise HTTPException(status_code=404, detail="Target user not found")

    dom = await _ensure_same_org(session, admin, payload.domain_id)

    # Scope enforcement
    if _is_org_admin(admin):
       
        pass
    elif _is_suborg_admin(admin):
        if admin.suborg_id != dom.suborg_id:
            raise HTTPException(status_code=403, detail="Suborg admin can manage only their suborg")
    else:
        raise HTTPException(status_code=403, detail="Only admins can grant access")

    # Target must be in the same org as domain
    if target.org_id != dom.org_id:
        raise HTTPException(status_code=400, detail="User and Domain belong to different orgs")

    # Upsert-like check
    exists = await session.execute(
        select(UserDomainAccess).where(
            UserDomainAccess.user_id == payload.user_id,
            UserDomainAccess.domain_id == payload.domain_id,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Access already granted")

    uda = UserDomainAccess(
        user_id=payload.user_id,
        domain_id=payload.domain_id,
        granted_by=admin.user_id,
    )
    session.add(uda)
    await session.commit()
    return AccessOut(user_id=payload.user_id, domain_id=payload.domain_id)


@router.delete("/revoke")
async def revoke_access(
    user_id: int = Query(...),
    domain_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(get_current_user),
):
    """
    Revoke a user’s access from a domain.
    - org_admin: any domain in org
    - suborg_admin: only their suborg
    """
    target = await session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    dom = await _ensure_same_org(session, admin, domain_id)

    if _is_org_admin(admin):
        pass
    elif _is_suborg_admin(admin):
        if admin.suborg_id != dom.suborg_id:
            raise HTTPException(status_code=403, detail="Suborg admin can manage only their suborg")
    else:
        raise HTTPException(status_code=403, detail="Only admins can revoke access")

    res = await session.execute(
        delete(UserDomainAccess).where(
            UserDomainAccess.user_id == user_id,
            UserDomainAccess.domain_id == domain_id,
        )
    )
    await session.commit()
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Access mapping not found")

    return {"message": "Access revoked"}


@router.get("/user-domains", response_model=list[AccessOut])
async def list_user_access(
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    viewer: User = Depends(get_current_user),
):
    """
    List all domain accesses for a given user.
    - org_admin: view for any user in org
    - suborg_admin: view only users in own suborg
    - user: view own access
    """
    target = await session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if _is_org_admin(viewer):
        if viewer.org_id != target.org_id:
            raise HTTPException(status_code=403, detail="Not allowed across orgs")
    elif _is_suborg_admin(viewer):
        if viewer.org_id != target.org_id or viewer.suborg_id != target.suborg_id:
            raise HTTPException(status_code=403, detail="Not allowed for other suborgs")
    else:
        if viewer.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not allowed")

    res = await session.execute(
        select(UserDomainAccess).where(UserDomainAccess.user_id == user_id)
    )
    rows = res.scalars().all()
    return [AccessOut(user_id=r.user_id, domain_id=r.domain_id) for r in rows]



#  Admin management (promote / demote)


@router.post("/promote/org-admin", response_model=UserOut)
async def promote_org_admin(
    payload: AdminTarget,
    session: AsyncSession = Depends(get_session),
    caller: User = Depends(get_current_user),
):
    """
    Make a user an org_admin.
    - Only an existing org_admin of the same org can promote.
    """
    if not _is_org_admin(caller):
        raise HTTPException(status_code=403, detail="Only org admins can promote org admins")

    target = await session.get(User, payload.user_id)
    if not target or target.isDeleted:
        raise HTTPException(status_code=404, detail="User not found")

    if target.org_id != caller.org_id:
        raise HTTPException(status_code=403, detail="User is in a different org")

    target.role = "org_admin"
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/demote/org-admin", response_model=UserOut)
async def demote_org_admin(
    payload: AdminTarget,
    session: AsyncSession = Depends(get_session),
    caller: User = Depends(get_current_user),
):
    """
    Remove org_admin role → becomes 'user'.
    - Only an org_admin in the same org can demote.
    """
    if not _is_org_admin(caller):
        raise HTTPException(status_code=403, detail="Only org admins can demote org admins")

    target = await session.get(User, payload.user_id)
    if not target or target.isDeleted:
        raise HTTPException(status_code=404, detail="User not found")

    if target.org_id != caller.org_id:
        raise HTTPException(status_code=403, detail="User is in a different org")

    target.role = "user"
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/promote/suborg-admin", response_model=UserOut)
async def promote_suborg_admin(
    payload: AdminTarget,
    session: AsyncSession = Depends(get_session),
    caller: User = Depends(get_current_user),
):
    """
    Make a user a suborg_admin.
    - org_admin of the same org can promote any user in that org’s suborgs.
    - suborg_admin can promote only within their own suborg.
    """
    target = await session.get(User, payload.user_id)
    if not target or target.isDeleted:
        raise HTTPException(status_code=404, detail="User not found")

    if _is_org_admin(caller):
        if caller.org_id != target.org_id:
            raise HTTPException(status_code=403, detail="Cross-org promotion not allowed")
    elif _is_suborg_admin(caller):
        if caller.org_id != target.org_id or caller.suborg_id != target.suborg_id:
            raise HTTPException(status_code=403, detail="Suborg admin can promote only within their suborg")
    else:
        raise HTTPException(status_code=403, detail="Only admins can promote")

    if target.suborg_id is None:
        raise HTTPException(status_code=400, detail="Target user must belong to a suborg to become suborg_admin")

    target.role = "suborg_admin"
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/demote/suborg-admin", response_model=UserOut)
async def demote_suborg_admin(
    payload: AdminTarget,
    session: AsyncSession = Depends(get_session),
    caller: User = Depends(get_current_user),
):
    """
    Remove suborg_admin role → becomes 'user'.
    - org_admin: can demote any suborg_admin in org
    - suborg_admin: can demote only within own suborg
    """
    target = await session.get(User, payload.user_id)
    if not target or target.isDeleted:
        raise HTTPException(status_code=404, detail="User not found")

    if _is_org_admin(caller):
        if caller.org_id != target.org_id:
            raise HTTPException(status_code=403, detail="Cross-org demotion not allowed")
    elif _is_suborg_admin(caller):
        if caller.org_id != target.org_id or caller.suborg_id != target.suborg_id:
            raise HTTPException(status_code=403, detail="Suborg admin can demote only within their suborg")
    else:
        raise HTTPException(status_code=403, detail="Only admins can demote")

    target.role = "user"
    await session.commit()
    await session.refresh(target)
    return target



#  Admin listing (org / suborg)


@router.get("/org-admins", response_model=list[UserOut])
async def list_org_admins(
    org_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    viewer: User = Depends(get_current_user),
):
    """
    List all org_admins for an org.
    - Only org_admin of that org can view.
    """
    if not _is_org_admin(viewer) or viewer.org_id != org_id:
        raise HTTPException(status_code=403, detail="Not allowed to view org admins")

    res = await session.execute(
        select(User).where(User.org_id == org_id, User.role == "org_admin", User.isDeleted == 0)
    )
    return res.scalars().all()


@router.get("/suborg-admins", response_model=list[UserOut])
async def list_suborg_admins(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    viewer: User = Depends(get_current_user),
):
    """
    List all suborg_admins for a suborg.
    - org_admin: can view any suborg in their org
    - suborg_admin: can view only their own suborg
    """
    if _is_org_admin(viewer):
        if viewer.org_id != org_id:
            raise HTTPException(status_code=403, detail="Org admin cannot view another org")
    elif _is_suborg_admin(viewer):
        if viewer.org_id != org_id or viewer.suborg_id != suborg_id:
            raise HTTPException(status_code=403, detail="Suborg admin cannot view another suborg")
    else:
        raise HTTPException(status_code=403, detail="Only admins can list suborg admins")

    res = await session.execute(
        select(User).where(
            User.org_id == org_id,
            User.suborg_id == suborg_id,
            User.role == "suborg_admin",
            User.isDeleted == 0,
        )
    )
    return res.scalars().all()

