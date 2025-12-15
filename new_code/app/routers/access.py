# from typing import Dict
# from fastapi import APIRouter, Depends, HTTPException, status, Query
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.models.user_model import User as UserModel, UserType
# from app.models.organization_model import Organization as OrganizationModel
# from app.models.suborganization_model import Suborganization as SuborganizationModel
# from app.models.access_model import UserDomainAccess
# from app.services.auth import get_current_active_user
# from app.schemas.access_schema import AccessGrant, AccessRevoke

# router = APIRouter(prefix="/access", tags=["access"])


# # -----------------------------
# # Helpers
# # -----------------------------
# def _ensure_org_exists(db: Session, org_id: int) -> OrganizationModel:
#     org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found")
#     return org

# def _ensure_suborg_in_org(db: Session, org_id: int, suborg_id: int) -> SuborganizationModel:
#     sub = db.query(SuborganizationModel).filter(
#         SuborganizationModel.id == suborg_id,
#         SuborganizationModel.organization_id == org_id
#     ).first()
#     if not sub:
#         raise HTTPException(status_code=404, detail="Department (suborganization) not found in this organization")
#     return sub

# def _ensure_user_exists(db: Session, user_id: int) -> UserModel:
#     user = db.query(UserModel).filter(UserModel.id == user_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     return user

# def _ensure_org_admin(current_user: UserModel, org_id: int) -> None:
#     """
#     Only org admins of the SAME org can manage access for that org.
#     """
#     if current_user.user_type != UserType.ADMIN or current_user.organization_id != org_id:
#         raise HTTPException(status_code=403, detail="Only the organization admin can perform this action")

# def _access_public(a: UserDomainAccess) -> Dict:
#     return {
#         "id": a.id,
#         "org_id": a.org_id,
#         "suborg_id": a.suborg_id,
#         "user_id": a.user_id,
#         "can_read": a.can_read,
#         "can_upload": a.can_upload,
#         "is_author": a.is_author,
#         "neural_cap": getattr(a, "neural_cap", None),
#     }


# # -----------------------------
# # Grant / Revoke Access
# # -----------------------------
# @router.post("/grant", status_code=status.HTTP_200_OK, summary="Grant/Update user access for a department")
# def grant_access(
#     payload: AccessGrant,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Body (AccessGrant):
#     - org_id: int
#     - suborg_id: int
#     - user_id: int
#     - can_read: bool
#     - can_upload: bool
#     - is_author: bool
#     - neural_cap: Optional[int]  (if present in your schema/model)
#     """
#     _ensure_org_admin(current_user, payload.org_id)
#     _ensure_org_exists(db, payload.org_id)
#     _ensure_suborg_in_org(db, payload.org_id, payload.suborg_id)
#     _ensure_user_exists(db, payload.user_id)

#     # author implies upload & read
#     can_read = bool(payload.can_read or payload.can_upload or payload.is_author)
#     can_upload = bool(payload.can_upload or payload.is_author)
#     is_author = bool(payload.is_author)

#     access = db.query(UserDomainAccess).filter(
#         UserDomainAccess.org_id == payload.org_id,
#         UserDomainAccess.suborg_id == payload.suborg_id,
#         UserDomainAccess.user_id == payload.user_id,
#     ).first()

#     if access is None:
#         access = UserDomainAccess(
#             org_id=payload.org_id,
#             suborg_id=payload.suborg_id,
#             user_id=payload.user_id,
#             can_read=can_read,
#             can_upload=can_upload,
#             is_author=is_author,
#         )
#         # Optional neural_cap if your table has it and schema provides it
#         if hasattr(access, "neural_cap") and hasattr(payload, "neural_cap") and payload.neural_cap is not None:
#             access.neural_cap = payload.neural_cap
#         db.add(access)
#         db.commit()
#         db.refresh(access)
#         return {"message": "Access granted", "access": _access_public(access)}
#     else:
#         access.can_read = can_read
#         access.can_upload = can_upload
#         access.is_author = is_author
#         if hasattr(access, "neural_cap") and hasattr(payload, "neural_cap") and payload.neural_cap is not None:
#             access.neural_cap = payload.neural_cap
#         db.commit()
#         db.refresh(access)
#         return {"message": "Access updated", "access": _access_public(access)}


# @router.post("/revoke", status_code=status.HTTP_200_OK, summary="Revoke user access for a department")
# def revoke_access(
#     payload: AccessRevoke,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Body (AccessRevoke):
#     - org_id: int
#     - suborg_id: int
#     - user_id: int
#     """
#     _ensure_org_admin(current_user, payload.org_id)

#     access = db.query(UserDomainAccess).filter(
#         UserDomainAccess.org_id == payload.org_id,
#         UserDomainAccess.suborg_id == payload.suborg_id,
#         UserDomainAccess.user_id == payload.user_id,
#     ).first()
#     if not access:
#         raise HTTPException(status_code=404, detail="Access record not found")

#     db.delete(access)
#     db.commit()
#     return {"message": "Access revoked"}


# # -----------------------------
# # Promote/Demote ORG ADMIN
# # -----------------------------
# @router.post("/promote/org-admin", status_code=status.HTTP_200_OK, summary="Make a user Organization Admin")
# def promote_org_admin(
#     user_id: int = Query(..., description="Target user id"),
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     user = _ensure_user_exists(db, user_id)
#     _ensure_org_admin(current_user, user.organization_id)
#     user.user_type = UserType.ADMIN
#     db.commit()
#     db.refresh(user)
#     return {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value}


# @router.post("/demote/org-admin", status_code=status.HTTP_200_OK, summary="Remove Organization Admin role")
# def demote_org_admin(
#     user_id: int = Query(...),
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     user = _ensure_user_exists(db, user_id)
#     _ensure_org_admin(current_user, user.organization_id)
#     user.user_type = UserType.USER
#     db.commit()
#     db.refresh(user)
#     return {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value}


# # -----------------------------
# # Promote/Demote AUTHOR (department-level)
# # -----------------------------
# @router.post("/promote/author", status_code=status.HTTP_200_OK, summary="Make user Author for a department")
# def promote_author(
#     org_id: int = Query(...),
#     suborg_id: int = Query(...),
#     user_id: int = Query(...),
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     _ensure_org_admin(current_user, org_id)
#     _ensure_org_exists(db, org_id)
#     _ensure_suborg_in_org(db, org_id, suborg_id)
#     _ensure_user_exists(db, user_id)

#     access = db.query(UserDomainAccess).filter(
#         UserDomainAccess.org_id == org_id,
#         UserDomainAccess.suborg_id == suborg_id,
#         UserDomainAccess.user_id == user_id,
#     ).first()
#     if not access:
#         access = UserDomainAccess(
#             org_id=org_id, suborg_id=suborg_id, user_id=user_id,
#             can_read=True, can_upload=True, is_author=True
#         )
#         db.add(access)
#     else:
#         access.can_read = True
#         access.can_upload = True
#         access.is_author = True
#     db.commit()
#     db.refresh(access)
#     return {"message": "User promoted to author", "access": _access_public(access)}


# @router.post("/demote/author", status_code=status.HTTP_200_OK, summary="Remove Author for a department")
# def demote_author(
#     org_id: int = Query(...),
#     suborg_id: int = Query(...),
#     user_id: int = Query(...),
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     _ensure_org_admin(current_user, org_id)
#     access = db.query(UserDomainAccess).filter(
#         UserDomainAccess.org_id == org_id,
#         UserDomainAccess.suborg_id == suborg_id,
#         UserDomainAccess.user_id == user_id,
#     ).first()
#     if not access:
#         raise HTTPException(status_code=404, detail="Access row not found")
#     access.is_author = False
#     access.can_upload = False
#     # keep can_read as-is (or set explicitly if you want)
#     db.commit()
#     db.refresh(access)
#     return {"message": "User demoted from author", "access": _access_public(access)}





# app/routers/access.py
# app/routers/access.py

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel, UserType
from app.models.organization_model import Organization as OrganizationModel
from app.models.suborganization_model import Suborganization as SuborganizationModel
from app.models.access_model import UserDomainAccess
from app.services.auth import get_current_active_user

router = APIRouter(prefix="/access", tags=["access"])

# ─────────────────────────── Schemas ───────────────────────────

class AccessGrant(BaseModel):
    """
    Grant or update access for a user on a department (suborganization).
    """
    org_id: int
    suborg_id: int
    user_id: int
    can_read: bool = True
    can_upload: bool = False
    is_author: bool = False
    is_dept_admin: bool = False
    neural_cap: int | None = Field(default=None, description="Optional token/usage cap")


class AccessRevoke(BaseModel):
    """
    Revoke access for a user on a department (suborganization).
    """
    org_id: int
    suborg_id: int
    user_id: int


# ─────────────────────────── Helpers ───────────────────────────

def _ensure_org_exists(db: Session, org_id: int) -> OrganizationModel:
    org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _ensure_suborg_in_org(db: Session, org_id: int, suborg_id: int) -> SuborganizationModel:
    sub = (
        db.query(SuborganizationModel)
        .filter(
            SuborganizationModel.id == suborg_id,
            SuborganizationModel.organization_id == org_id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Department (suborganization) not found in this organization")
    return sub


def _ensure_user_exists(db: Session, user_id: int) -> UserModel:
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _ensure_org_admin(current_user: UserModel, org_id: int) -> None:
    """
    Only admins of the SAME org can manage access for that org.
    """
    if current_user.user_type != UserType.ADMIN or current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Only the organization admin can perform this action")

def _ensure_admin_can_delete_dept_head(db: Session,user_id: int, org_id: int,suborg_id:int)-> None:
     sub = (
        db.query(SuborganizationModel)
        .filter(
            SuborganizationModel.id == suborg_id,
            SuborganizationModel.organization_id == org_id,
            SuborganizationModel.dept_head==user_id
        )
        .first()
    )
     if sub:
          raise HTTPException(status_code=403, detail="Only the organization admin can remove department head")

def _ensure_org_admin_or_dept_head(db: Session,current_user: UserModel, org_id: int,suborg_id:int) -> None:
    """
    Only admins of the SAME org can manage access for that org.
    """
    sub = (
        db.query(SuborganizationModel)
        .filter(
            SuborganizationModel.id == suborg_id,
            SuborganizationModel.organization_id == org_id,
        )
        .first()
    )
    if (current_user.user_type != UserType.ADMIN and sub.dept_head!=current_user.id) or current_user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="Only the organization admin or dept head can perform this action")


def _access_public(a: UserDomainAccess) -> Dict:
    return {
        "id": a.id,
        "org_id": a.org_id,
        "suborg_id": a.suborg_id,
        "user_id": a.user_id,
        "can_read": getattr(a, "can_read", True),
        "can_upload": getattr(a, "can_upload", False),
        "is_author": getattr(a, "is_author", False),
        "neural_cap": getattr(a, "neural_cap", None),
    }


# ─────────────────────────── CRUD / LIST ───────────────────────────

@router.get(
    "/user/{user_id}",
    response_model=List[Dict],
    summary="List a user's department permissions (org-scoped)",
)
def list_user_access(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Admin-only: list which departments (suborganizations) this user has access to
    within the admin's organization.
    """
    if current_user.user_type != UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Only org admins can view access")

    user = _ensure_user_exists(db, user_id)
    if user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="User is not in your organization")

    rows = (
        db.query(UserDomainAccess)
        .join(
            SuborganizationModel,
            SuborganizationModel.id == UserDomainAccess.suborg_id,
        )
        .filter(
            SuborganizationModel.organization_id == current_user.organization_id,
            UserDomainAccess.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r) for r in rows]


# ─────────────────────────── Grant / Revoke ───────────────────────────



# @router.post(
#     "/aasign_dept_head",
#     status_code=status.HTTP_200_OK,
#     summary="Grant/Update user access for a department (suborganization)",
# )
# def grant_access(
#     payload: AccessGrant,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
from types import SimpleNamespace
import json
@router.post(
    "/assign-dept-head",

)
def assign_dept_head(
    used_id: int,
    organization_id:int,
    suborganization_id:int,
    neural_cap:int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Grant or update a user's permissions for a department (suborganization):

    - org_id, suborg_id, user_id (required)
    - can_read, can_upload, is_author
      * If is_author=True, user can_read and can_upload will be forced to True.
    - neural_cap (optional, if present in model)
    """
    
    payload={"id":used_id,"organization_id":organization_id,"suborganization_id":suborganization_id,"neural_cap":neural_cap}
    payload=json.loads(json.dumps(payload), object_hook=lambda d: SimpleNamespace(**d))

    _ensure_org_admin(current_user, payload.organization_id)
    _ensure_org_exists(db, payload.organization_id)
    _ensure_suborg_in_org(db, payload.organization_id, payload.suborganization_id)
    user = _ensure_user_exists(db, payload.id)
    sub_org=db.query(SuborganizationModel).filter(SuborganizationModel.id==suborganization_id).first()
    sub_org.dept_head=used_id
    if user.organization_id != payload.organization_id:
        raise HTTPException(status_code=403, detail="User is not in this organization")
    # user.user_type=UserType.DEPT_HEAD
    
    db.commit()
    db.refresh(sub_org)
    # author implies upload & read
    can_read = True
    can_upload = True
    is_author = True


    access = UserDomainAccess(
            org_id=payload.organization_id,
            suborg_id=payload.suborganization_id,
            user_id=payload.id,
            can_read=can_read,
            can_upload=can_upload,
            is_author=is_author,
        )
    if hasattr(access, "neural_cap") and payload.neural_cap is not None:
            access.neural_cap = payload.neural_cap
            db.add(access)


    db.commit()
    db.refresh(access)

    return {"message": "Access upserted"}




@router.post(
    "/grant",
    status_code=status.HTTP_200_OK,
    summary="Grant/Update user access for a department (suborganization)",
)
def grant_access(
    payload: AccessGrant,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Grant or update a user's permissions for a department (suborganization):

    - org_id, suborg_id, user_id (required)
    - can_read, can_upload, is_author
      * If is_author=True, user can_read and can_upload will be forced to True.
    - neural_cap (optional, if present in model)
    """
    
    # _ensure_org_admin(current_user, payload.org_id)
    _ensure_org_admin_or_dept_head(db,current_user,payload.org_id,payload.suborg_id)
    _ensure_org_exists(db, payload.org_id)
    _ensure_suborg_in_org(db, payload.org_id, payload.suborg_id)

    user = _ensure_user_exists(db, payload.user_id)
    

    if user.organization_id != payload.org_id :
        raise HTTPException(status_code=403, detail="User is not in this organization")

    # author implies upload & read
    can_read = bool(payload.can_read or payload.can_upload or payload.is_author)
    can_upload = bool(payload.can_upload or payload.is_author)
    is_author = bool(payload.is_author)
    # is_dept_admin=bool(payload.is_dept_admin)
    # if is_dept_admin:
    #     _ensure_org_admin(current_user, payload.org_id)
    access = (
        db.query(UserDomainAccess)
        .filter(
            UserDomainAccess.org_id == payload.org_id,
            UserDomainAccess.suborg_id == payload.suborg_id,
            UserDomainAccess.user_id == payload.user_id
        )
        .first()
    )

    if access is None:
        access = UserDomainAccess(
            org_id=payload.org_id,
            suborg_id=payload.suborg_id,
            user_id=payload.user_id,
            can_read=can_read,
            can_upload=can_upload,
            is_author=is_author,
        
        )
        if hasattr(access, "neural_cap") and payload.neural_cap is not None:
            access.neural_cap = payload.neural_cap
        db.add(access)
    else:
        access.can_read = can_read
        access.can_upload = can_upload
        access.is_author = is_author

        if hasattr(access, "neural_cap") and payload.neural_cap is not None:
            access.neural_cap = payload.neural_cap

    db.commit()
    db.refresh(access)
    return {"message": "Access upserted", "access": _access_public(access)}


@router.post(
    "/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke user access for a department (suborganization)",
)
def revoke_access(
    payload: AccessRevoke,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    # _ensure_org_admin(current_user, payload.org_id)
    _ensure_org_admin_or_dept_head(db,current_user,payload.org_id,payload.suborg_id)
    _ensure_admin_can_delete_dept_head(db,payload.user_id,payload.org_id,payload.suborg_id)
    access = (
        db.query(UserDomainAccess)
        .filter(
            UserDomainAccess.org_id == payload.org_id,
            UserDomainAccess.suborg_id == payload.suborg_id,
            UserDomainAccess.user_id == payload.user_id,
        )
        .first()
    )
    if not access:
        raise HTTPException(status_code=404, detail="Access record not found")

    db.delete(access)
    db.commit()
    return {"message": "Access revoked"}


# ───────────────────── Promote/Demote Author (department-level) ─────────────────────


@router.post(
    "/promote/author",
    status_code=status.HTTP_200_OK,
    summary="Make user Author for a department (suborganization)",
)
def promote_author(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Mark a user as Author for a department (suborganization).
    This implies can_read=True and can_upload=True for that department.
    """
    _ensure_org_admin(current_user, org_id)
    _ensure_org_exists(db, org_id)
    _ensure_suborg_in_org(db, org_id, suborg_id)
    user = _ensure_user_exists(db, user_id)

    if user.organization_id != org_id:
        raise HTTPException(status_code=403, detail="User is not in this organization")

    access = (
        db.query(UserDomainAccess)
        .filter(
            UserDomainAccess.org_id == org_id,
            UserDomainAccess.suborg_id == suborg_id,
            UserDomainAccess.user_id == user_id,
        )
        .first()
    )
    if not access:
        access = UserDomainAccess(
            org_id=org_id,
            suborg_id=suborg_id,
            user_id=user_id,
            can_read=True,
            can_upload=True,
            is_author=True,
        )
        db.add(access)
    else:
        access.can_read = True
        access.can_upload = True
        access.is_author = True

    db.commit()
    db.refresh(access)
    return {"message": "User promoted to author", "access": _access_public(access)}


@router.post(
    "/demote/author",
    status_code=status.HTTP_200_OK,
    summary="Remove Author role for a department (suborganization)",
)
def demote_author(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Remove author/upload rights for a department.
    (You can still leave read access or revoke separately using /access/grant or /access/revoke.)
    """
    _ensure_org_admin(current_user, org_id)

    access = (
        db.query(UserDomainAccess)
        .filter(
            UserDomainAccess.org_id == org_id,
            UserDomainAccess.suborg_id == suborg_id,
            UserDomainAccess.user_id == user_id,
        )
        .first()
    )
    if not access:
        raise HTTPException(status_code=404, detail="Access row not found")

    access.is_author = False
    access.can_upload = False
    db.commit()
    db.refresh(access)
    return {"message": "User demoted from author", "access": _access_public(access)}
