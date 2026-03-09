from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.database import get_db
from app.models.organization_model import Organization as OrganizationModel
from app.models.department_model import Department as DepartmentModel
from app.models.user_model import User as UserModel
from app.models.user_access_department_model import UserAccessDepartment,UserType
from app.services.auth import (
    get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_active_user, get_user_by_email, get_user_by_username
)
from app.schemas.onboarding_schema import (
    SignupRequest, SignupResponse, OrgProfileUpdate,
    DepartmentBulkCreate, InviteUsersRequest, InviteUsersResponse, RoleEnum
)
from app.Rag.VectorManager import vectorManager
from app.Rag.utils import embeddings,BASE_DIR
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

def _org_public(o: OrganizationModel) -> Dict:
    return {"id": o.id, "name": o.name, "description": o.description}

def _sub_public(s: DepartmentModel) -> Dict:
    return {"id": s.id, "name": s.name, "description": s.description}

# STEP 1: Org + Admin signup (single call that your first screen needs)
@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    # 409 if org name exists
    existing_org = db.query(OrganizationModel).filter(OrganizationModel.name == payload.organization_name).first()
    if existing_org:
        raise HTTPException(status_code=409, detail="Organization name already exists")

    if get_user_by_email(db, payload.admin_email):
        raise HTTPException(status_code=409, detail="Email already registered")

    if get_user_by_username(db, payload.admin_name):
        raise HTTPException(status_code=409, detail="Admin username already taken")

    # Create org
    org = OrganizationModel(name=payload.organization_name, description=payload.description or None)
    db.add(org); db.commit(); db.refresh(org)

    # Create admin user
    hashed = get_password_hash(payload.password)
    admin = UserModel(
        email=payload.admin_email, username=payload.admin_name,
        hashed_password=hashed, user_type=UserType.ADMIN, org_id=org.id
    )
    db.add(admin); db.commit(); db.refresh(admin)
    db.flush()
    vectorManager.create_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\{org.id}")
    # JWT
    token = create_access_token(data={"sub": admin.email}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    return {
        "access_token": token,
        "token_type": "bearer",
        "organization": _org_public(org),
        "admin_user": {"id": admin.id, "name": admin.username, "email": admin.email, "user_type": admin.user_type.value}
    }

# STEP 2: Update org profile (second screen)
@router.put("/organization/{org_id}/profile", status_code=status.HTTP_200_OK)
def update_org_profile(
    org_id: int, payload: OrgProfileUpdate, db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Organization not found")
    if current_user.user_type != UserType.ADMIN or current_user.org_id != org_id:
        raise HTTPException(status_code=403, detail="Only organization admin can update profile")

    if payload.website_url is not None: org.website_url = str(payload.website_url)
    if payload.industry is not None: org.industry = payload.industry
    if payload.company_size is not None: org.company_size = payload.company_size
    if payload.social_handles is not None: org.social_handles = payload.social_handles

    db.commit(); db.refresh(org)
    return _org_public(org)

# STEP 3: Select/Create departments in bulk
@router.post("/departments/bulk", status_code=status.HTTP_201_CREATED)
def bulk_create_departments(
    body: DepartmentBulkCreate, db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    if current_user.user_type != UserType.ADMIN or current_user.org_id != body.org_id:
        raise HTTPException(status_code=403, detail="Only organization admin can manage departments")

    org = db.query(OrganizationModel).filter(OrganizationModel.id == body.org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Organization not found")

    created_or_existing = []
    for name in body.departments:
        name_norm = name.strip()
        if not name_norm:
            continue
        sub = db.query(DepartmentModel).filter(
            DepartmentModel.org_id == body.org_id,
            DepartmentModel.name == name_norm
        ).first()
        if not sub:
            sub = DepartmentModel(org_id=body.org_id, name=name_norm, description=name_norm)
            db.add(sub)
        db.flush()
        vectorManager.create_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\{sub.org_id}\dept\{sub.id}")
        created_or_existing.append(sub)
    db.commit()
    return [_sub_public(s) for s in created_or_existing]

# STEP 4: Invite users, set role, departments, cap
@router.post("/invites", response_model=InviteUsersResponse, status_code=status.HTTP_201_CREATED)
def invite_users(
    body: InviteUsersRequest, db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    if current_user.user_type != UserType.ADMIN or current_user.org_id != body.org_id:
        raise HTTPException(status_code=403, detail="Only organization admin can invite users")

    org = db.query(OrganizationModel).filter(OrganizationModel.id == body.org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Organization not found")

    out = []
    for inv in body.invites:
        # Create or reuse user
        user = get_user_by_email(db, inv.email)
        if not user:
            # temp username from email local-part, ensure unique
            base = inv.email.split("@")[0]
            uname = base
            suffix = 1
            while get_user_by_username(db, uname):
                suffix += 1
                uname = f"{base}{suffix}"
            # temp password (store hash). Frontend can send a real password later via /auth/signup if you prefer.
            tmp_hash = get_password_hash("Temp@1234")
            user_type = UserType.USER if inv.role != RoleEnum.ADMIN else UserType.ADMIN
            user = UserModel(email=inv.email, username=uname, hashed_password=tmp_hash,
                              org_id=org.id)
            db.add(user); db.flush()

        # Map departments
        dept_ids = []
        for dname in inv.department_names:
            sub = db.query(DepartmentModel).filter(
                DepartmentModel.org_id == org.id,
                DepartmentModel.name == dname
            ).first()
            if not sub:
                # auto-create if not found (nice UX)
                sub = DepartmentModel(org_id=org.id, name=dname.strip(), description=dname.strip())
                db.add(sub); db.flush()
            dept_ids.append(sub.id)

        # Access rows
        for sid in dept_ids:
            access = db.query(UserAccessDepartment).filter(
                UserAccessDepartment.org_id == org.id,
                UserAccessDepartment.dept_id == sid,
                UserAccessDepartment.user_id == user.id
            ).first()
            if not access:
                access = UserAccessDepartment(
                    org_id=org.id, dept_id=sid, user_id=user.id,
                    can_read=True,
                    can_upload=True if inv.role in (RoleEnum.ADMIN, RoleEnum.DEPT_AUTHOR) else False,
                    is_author=True if inv.role == RoleEnum.DEPT_AUTHOR else False,
                    neural_cap=inv.neural_cap or 1000000
                )
                db.add(access)
            else:
                access.can_read = True
                access.can_upload = True if inv.role in (RoleEnum.ADMIN, RoleEnum.DEPT_AUTHOR) else False
                access.is_author = True if inv.role == RoleEnum.DEPT_AUTHOR else False
                access.neural_cap = inv.neural_cap or access.neural_cap

        out.append({
            "id": user.id, "email": user.email,
            "role": user.user_type.value if inv.role == RoleEnum.ADMIN else inv.role.value,
            "departments": inv.department_names
        })

    db.commit()
    return {"created_users": out}
