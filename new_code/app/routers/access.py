

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel
from app.models.organization_model import Organization as OrganizationModel
from app.models.department_model import Department as DepartmentModel
from app.models.user_access_department_model import UserAccessDepartment, UserType
from app.services.auth import get_current_active_user

router = APIRouter(prefix="/access", tags=["access"])

# ─────────────────────────── Schemas ───────────────────────────

class AccessGrant(BaseModel):
    """
    Grant or update access for a user on a department (Department).
    """
    org_id: int
    dept_id: int
    user_id: int
    user_type:str


class AccessRevoke(BaseModel):
    """
    Revoke access for a user on a department (Department).
    """
    org_id: int
    dept_id: int
    user_id: int


# ─────────────────────────── Helpers ───────────────────────────

def _ensure_org_exists(db: Session, org_id: int) -> OrganizationModel:
    org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _ensure_user_exists(db: Session, user_id: int) -> UserModel:
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _ensure_org_admin(db:Session,current_user: UserModel, org_id: int) -> None:
    """
    Only admins of the SAME org can manage access for that org.
    """
    dom=db.query(UserAccessDepartment).filter(UserAccessDepartment.org_id==current_user.org_id,UserAccessDepartment.user_id==current_user.id,UserAccessDepartment.user_type==UserType.ADMIN).first()
    
    if not dom:
        raise HTTPException(status_code=403, detail="Only the organization admin can perform this action")
    return dom


def _ensure_org_or_dept_admin(db: Session,current_user: UserModel, org_id: int,dept_id:int,role:str) -> None:
    """
    Only admins of the SAME org can manage access for that org.
    """
    orgdom=db.query(UserAccessDepartment).filter(UserAccessDepartment.org_id==current_user.org_id,UserAccessDepartment.user_id==current_user.id,UserAccessDepartment.user_type==UserType.ADMIN).first()
 

    if not orgdom:
                  
       dom=db.query(UserAccessDepartment).filter(UserAccessDepartment.org_id==org_id,UserAccessDepartment.dept_id==dept_id,UserAccessDepartment.user_type==UserType.DEPT_ADMIN).first()
       if role==UserType.DEPT_ADMIN:
           raise HTTPException(status_code=403, detail="Only the organization admin can assign another department admin")

       if not dom:
          raise HTTPException(status_code=403, detail="Only the organization admin or dept head can perform this action")


def _access_public(a: UserAccessDepartment) -> Dict:
    return {
        "id": a.id,
        "org_id": a.org_id,
        "dept_id": a.dept_id,
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
    Admin-only: list which departments (Departments) this user has access to
    within the admin's organization.
    """
    if current_user.user_type != UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Only org admins can view access")

    user = _ensure_user_exists(db, user_id)
    if user.org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="User is not in your organization")

    rows = (
        db.query(UserAccessDepartment)
        .join(
            DepartmentModel,
            DepartmentModel.id == UserAccessDepartment.dept_id,
        )
        .filter(
            DepartmentModel.org_id == current_user.org_id,
            UserAccessDepartment.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r) for r in rows]


# ─────────────────────────── Grant / Revoke ───────────────────────────


from types import SimpleNamespace
# import json
# @router.post(
#     "/assign-dept-head",

# )
# def assign_dept_head(
#     used_id: int,
#     org_id:int,
#     Department_id:int,
#     neural_cap:int,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Grant or update a user's permissions for a department (Department):

#     - org_id, dept_id, user_id (required)
#     - can_read, can_upload, is_author
#       * If is_author=True, user can_read and can_upload will be forced to True.
#     - neural_cap (optional, if present in model)
#     """
    
#     payload={"id":used_id,"org_id":org_id,"Department_id":Department_id,"neural_cap":neural_cap}
#     payload=json.loads(json.dumps(payload), object_hook=lambda d: SimpleNamespace(**d))

#     _ensure_org_admin(current_user, payload.org_id)
#     _ensure_org_exists(db, payload.org_id)
#     _ensure_suborg_in_org(db, payload.org_id, payload.Department_id)
#     user = _ensure_user_exists(db, payload.id)
#     sub_org=db.query(DepartmentModel).filter(DepartmentModel.id==Department_id).first()
#     sub_org.dept_head=used_id
#     if user.org_id != payload.org_id:
#         raise HTTPException(status_code=403, detail="User is not in this organization")
#     # user.user_type=UserType.DEPT_HEAD
    
#     db.commit()
#     db.refresh(sub_org)
#     # author implies upload & read
#     can_read = True
#     can_upload = True
#     is_author = True


#     access = UserAccessDepartment(
#             org_id=payload.org_id,
#             dept_id=payload.Department_id,
#             user_id=payload.id,
#             can_read=can_read,
#             can_upload=can_upload,
#             is_author=is_author,
#         )
#     if hasattr(access, "neural_cap") and payload.neural_cap is not None:
#             access.neural_cap = payload.neural_cap
#             db.add(access)


#     db.commit()
#     db.refresh(access)

#     return {"message": "Access upserted"}




@router.post(
    "/grant",
    status_code=status.HTTP_200_OK,
    summary="Grant/Update user access for a department (Department)",
)
def grant_access(
    payload: AccessGrant,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Grant or update a user's permissions for a department (Department):

    - org_id, dept_id, user_id (required)
    - can_read, can_upload, is_author
      * If is_author=True, user can_read and can_upload will be forced to True.
    - neural_cap (optional, if present in model)
    """
    
    _ensure_org_or_dept_admin(db,current_user, payload.org_id,payload.dept_id,payload.user_type)


    access = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == payload.org_id,
            UserAccessDepartment.dept_id == payload.dept_id,
            UserAccessDepartment.user_id == payload.user_id
        )
        .first()
    )

    if access is None:
        access = UserAccessDepartment(
            org_id=payload.org_id,
            dept_id=payload.dept_id,
            user_id=payload.user_id,
            user_type=payload.user_type,
        
        )
  
        db.add(access)


    db.commit()
    db.refresh(access)
    return {"message": "Access upserted", "access": _access_public(access)}


@router.post(
    "/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke user access for a department ",
)
def revoke_access(
    payload: AccessRevoke,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    # _ensure_org_admin(current_user, payload.org_id)
    _ensure_org_or_dept_admin(db,current_user,payload.org_id,payload.dept_id,"")

    access = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == payload.org_id,
            UserAccessDepartment.dept_id == payload.dept_id,
            UserAccessDepartment.user_id == payload.user_id,
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
    summary="Make user Author for a department (Department)",
)
def promote_author(
    org_id: int = Query(...),
    dept_id: int = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Mark a user as Author for a department (Department).
    This implies can_read=True and can_upload=True for that department.
    """
    _ensure_org_or_dept_admin(db,current_user, org_id,dept_id,"")
    user = _ensure_user_exists(db, user_id)

    if user.org_id != org_id:
        raise HTTPException(status_code=403, detail="User is not in this organization")

    access = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.user_type == UserType.USER
        )
        .first()
    )
    if not access:
        access = UserAccessDepartment(
            org_id=org_id,
            dept_id=dept_id,
            user_id=user_id,
            user_type=UserType.AUTHOR,
        )
        db.add(access)
    else:
        access.user_type=UserType.AUTHOR

    db.commit()
    db.refresh(access)
    return {"message": "User promoted to author", "access": _access_public(access)}


@router.post(
    "/demote/author",
    status_code=status.HTTP_200_OK,
    summary="Remove Author role for a department (Department)",
)
def demote_author(
    org_id: int = Query(...),
    dept_id: int = Query(...),
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Remove author/upload rights for a department.
    (You can still leave read access or revoke separately using /access/grant or /access/revoke.)
    """
    _ensure_org_or_dept_admin(db,current_user, org_id,dept_id,"")
    user = _ensure_user_exists(db, user_id)

    if user.org_id != org_id:
        raise HTTPException(status_code=403, detail="User is not in this organization")

    access = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.user_type == UserType.AUTHOR
        )
        .first()
    )
    if not access:
        access = UserAccessDepartment(
            org_id=org_id,
            dept_id=dept_id,
            user_id=user_id,
            user_type=UserType.USER,
        )
        db.add(access)
    else:
        access.user_type=UserType.USER
    db.commit()
    db.refresh(access)
    return {"message": "User demoted from author", "access": _access_public(access)}
