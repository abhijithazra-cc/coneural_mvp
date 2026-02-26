# app/routers/users.py

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel
from app.models.user_access_department_model import UserType,UserAccessDepartment
from app.models.organization_model import Organization as OrganizationModel
from app.services.auth import (
    get_current_active_user,
    get_user_by_email,
    get_user_by_username,
       # USE hashing from services.auth
)
from app.utils.security import get_password_hash 

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
        409: {"description": "Conflict"},
        500: {"description": "Internal server error"},
    },
)

# ─────────────────────── Schemas ───────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=255)
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="8–72 characters (bcrypt ≤72 bytes)",
    )
    org_id: int  # must equal admin's org
    # NOTE: user_type is intentionally NOT accepted here to prevent privilege escalation.

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72-byte bcrypt limit")
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72-byte bcrypt limit")
        return v


class UserPublic(BaseModel):
    id: int
    name: str
    email: EmailStr
    


# ─────────────────────── Helpers ───────────────────────

def _require_admin_same_org(db:Session,current_user: UserModel, org_id: int):
    """
    Only ADMIN of that org can operate on users of that org.
    """
    dom=db.query(UserAccessDepartment).filter(UserAccessDepartment.org_id==org_id,UserAccessDepartment.user_id==current_user.id).first()
    if not dom: 
        raise HTTPException(status_code=403, detail="No department access found for current user")
    if dom.user_type != UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Only org admins can perform this action")

    if current_user.org_id != org_id:
        raise HTTPException(status_code=403, detail="org_id does not match your organization")


# ─────────────────────── Routes ───────────────────────

@router.post(
    "/",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (org-scoped; no department binding here)",
)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Create a new **USER** in the current admin's organization.
    - Admin-only.
    - `org_id` must equal admin's org.
    - Department (Department) access is handled separately via `/access` APIs.
    """
    _require_admin_same_org(db,current_user, body.org_id)

    # Organization must exist
    org = db.query(OrganizationModel).filter(OrganizationModel.id == body.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Uniqueness checks
    if get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    if get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="Username already taken")

    # Always create as USER (no ADMIN promotion from this endpoint)
    hashed = get_password_hash(body.password)
    user = UserModel(
        email=body.email,
        username=body.username,
        hashed_password=hashed,
   
        org_id=body.org_id,
        # Department_id left as None; access per department is in user_domain_access
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return UserPublic(
        id=user.id,
        name=user.username,
        email=user.email,
       
    )


@router.get(
    "/",
    response_model=List[UserPublic],
    summary="List users in your organization",
)
def list_users(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Admin-only: list all users in your organization.
    """
    _require_admin_same_org(db,current_user, current_user.org_id)

    users = db.query(UserModel).filter(UserModel.org_id == current_user.org_id).all()
    return [
        UserPublic(
            id=u.id,
            name=str(u.username),
            email=u.email,
         
        )
        for u in users
    ]


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Get user by ID (org-scoped)",
)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Admin-only: fetch a user by id within your organization.
    """
    _require_admin_same_org(current_user, current_user.org_id)

    user = (
        db.query(UserModel)
        .filter(
            UserModel.id == user_id,
            UserModel.org_id == current_user.org_id,
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found in your organization")

    return UserPublic(
        id=user.id,
        name=user.username,
        email=user.email
    )


@router.patch(
    "/{user_id}",
    response_model=UserPublic,
    summary="Update user (username / password)",
)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """
    Admin-only partial update within your org:
    - Change username (unique)
    - Change password
    (No user_type changes here; admin promotion is handled elsewhere if needed.)
    """
    _require_admin_same_org(current_user, current_user.org_id)

    user = (
        db.query(UserModel)
        .filter(
            UserModel.id == user_id,
            UserModel.org_id == current_user.org_id,
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found in your organization")

    if body.username and body.username != user.username:
        if get_user_by_username(db, body.username):
            raise HTTPException(status_code=409, detail="Username already taken")
        user.username = body.username

    if body.password:
        user.hashed_password = get_password_hash(body.password)

    db.commit()
    db.refresh(user)

    return UserPublic(
        id=user.id,
        name=user.username,
        email=user.email,
        
    )



# app/routers/users.py
# app/routers/users.py
# from typing import Optional, List

# from fastapi import APIRouter, Depends, HTTPException, status
# from pydantic import BaseModel, EmailStr, Field, field_validator
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.models.user_model import User as UserModel, UserType
# from app.models.organization_model import Organization as OrganizationModel

# from app.services.auth import (
#     get_current_active_user,
#     get_user_by_email,
#     get_user_by_username,
# )
# from app.utils.security import get_password_hash

# router = APIRouter(
#     prefix="/users",
#     tags=["users"],
#     responses={
#         401: {"description": "Unauthorized"},
#         403: {"description": "Forbidden"},
#         404: {"description": "Not found"},
#         409: {"description": "Conflict"},
#         500: {"description": "Internal server error"},
#     },
# )

# # ─────────────────────── Schemas ───────────────────────

# class UserCreate(BaseModel):
#     email: EmailStr
#     username: str = Field(..., min_length=2, max_length=255)
#     password: str = Field(..., min_length=8, max_length=72, description="8–72 characters (bcrypt ≤72 bytes)")
#     org_id: int  # must equal admin's org
#     # NOTE: user_type is intentionally NOT accepted here to prevent privilege escalation.

#     @field_validator("password")
#     @classmethod
#     def _bcrypt_limit(cls, v: str) -> str:
#         if len(v.encode("utf-8")) > 72:
#             raise ValueError("Password exceeds 72-byte bcrypt limit")
#         return v


# class UserUpdate(BaseModel):
#     username: Optional[str] = Field(None, min_length=2, max_length=255)
#     password: Optional[str] = Field(None, min_length=8, max_length=72)

#     @field_validator("password")
#     @classmethod
#     def _bcrypt_limit(cls, v: Optional[str]) -> Optional[str]:
#         if v is None:
#             return v
#         if len(v.encode("utf-8")) > 72:
#             raise ValueError("Password exceeds 72-byte bcrypt limit")
#         return v


# class UserPublic(BaseModel):
#     id: int
#     name: str
#     email: EmailStr
#     user_type: str


# # ─────────────────────── Helpers ───────────────────────

# def _require_admin_same_org(current_user: UserModel, org_id: int):
#     if current_user.user_type != UserType.ADMIN:
#         raise HTTPException(status_code=403, detail="Only org admins can perform this action")
#     if current_user.org_id != org_id:
#         raise HTTPException(status_code=403, detail="org_id does not match your organization")


# # ─────────────────────── Routes ───────────────────────

# @router.post(
#     "/",
#     response_model=UserPublic,
#     status_code=status.HTTP_201_CREATED,
#     summary="Create a user (org-scoped; no Department)"
# )
# def create_user(
#     body: UserCreate,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Create a new **USER** in the current admin's organization.
#     - Admin-only.
#     - `org_id` must equal admin's org.
#     - No Department here (domain access handled in /access router).
#     """
#     _require_admin_same_org(current_user, body.org_id)

#     # Organization must exist
#     org = db.query(OrganizationModel).filter(OrganizationModel.id == body.org_id).first()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found")

#     # Uniqueness
#     if get_user_by_email(db, body.email):
#         raise HTTPException(status_code=409, detail="Email already registered")
#     if get_user_by_username(db, body.username):
#         raise HTTPException(status_code=409, detail="Username already taken")

#     # Create as USER (no admin promotion here)
#     hashed = get_password_hash(body.password)
#     user = UserModel(
#         email=body.email,
#         username=body.username,
#         hashed_password=hashed,
#         user_type=UserType.USER,
#         org_id=body.org_id,
#         # Department_id intentionally ignored/left None
#     )
#     db.add(user)
#     db.commit()
#     db.refresh(user)

#     return {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value}


# @router.get(
#     "/",
#     response_model=List[UserPublic],
#     summary="List users in your organization"
# )
# def list_users(
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Admin-only: list all users in your organization.
#     """
#     _require_admin_same_org(current_user, current_user.org_id)

#     users = db.query(UserModel).filter(UserModel.org_id == current_user.org_id).all()
#     return [
#         {"id": u.id, "name": u.username, "email": u.email, "user_type": u.user_type.value}
#         for u in users
#     ]


# @router.get(
#     "/{user_id}",
#     response_model=UserPublic,
#     summary="Get user by ID (org-scoped)"
# )
# def get_user_by_id(
#     user_id: int,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Admin-only: fetch a user by id within your organization.
#     """
#     _require_admin_same_org(current_user, current_user.org_id)

#     user = db.query(UserModel).filter(
#         UserModel.id == user_id,
#         UserModel.org_id == current_user.org_id
#     ).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found in your organization")

#     return {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value}


# @router.patch(
#     "/{user_id}",
#     response_model=UserPublic,
#     summary="Update user (username / password)"
# )
# def update_user(
#     user_id: int,
#     body: UserUpdate,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Admin-only partial update within your org:
#     - Change username (unique)
#     - Change password
#     (No user_type changes here; admin promotion is handled elsewhere if needed.)
#     """
#     _require_admin_same_org(current_user, current_user.org_id)

#     user = db.query(UserModel).filter(
#         UserModel.id == user_id,
#         UserModel.org_id == current_user.org_id
#     ).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found in your organization")

#     if body.username and body.username != user.username:
#         if get_user_by_username(db, body.username):
#             raise HTTPException(status_code=409, detail="Username already taken")
#         user.username = body.username

#     if body.password:
#         user.hashed_password = get_password_hash(body.password)

#     db.commit()
#     db.refresh(user)

#     return {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value}
