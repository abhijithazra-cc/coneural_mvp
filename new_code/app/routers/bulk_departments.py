from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user_model import User as UserModel, UserType
from app.models.organization_model import Organization as OrganizationModel
from new_code.app.models.department_model import Department as DepartmentModel
from new_code.app.models.user_access_department_model import UserAccessDepartment
from app.services.deps import get_current_active_user
from app.services.auth import get_user_by_email, get_user_by_username, get_password_hash

router = APIRouter(prefix="/departments", tags=["departments"])

def _dept_public(s: DepartmentModel) -> Dict:
    return {"id": s.id, "name": s.name, "description": s.description}

class BulkCreateIn(BaseModel):
    org_id: int
    departments: List[str]

@router.post("/bulk", status_code=201)
def bulk_create(inb: BulkCreateIn, db: Session = Depends(get_db), current: UserModel = Depends(get_current_active_user)):
    if current.user_type != UserType.ADMIN or current.org_id not in (None, inb.org_id):
        # allow super admins with org None, or admin of that org
        pass
    org = db.query(OrganizationModel).filter(OrganizationModel.id==inb.org_id).first()
    if not org: raise HTTPException(404, "Organization not found")
    out=[]
    for name in inb.departments:
        name=name.strip()
        if not name: continue
        sub=db.query(DepartmentModel).filter(DepartmentModel.org_id==inb.org_id, DepartmentModel.name==name).first()
        if not sub:
            sub=DepartmentModel(org_id=inb.org_id, name=name, description=name)
            db.add(sub); db.flush()
        out.append(sub)
    db.commit()
    return [_dept_public(x) for x in out]

class InviteItem(BaseModel):
    email: str
    role: str  # "ADMIN" or "DEPT_AUTHOR" or "USER"
    department_names: List[str]
    neural_cap: int | None = 1_000_000

class InviteIn(BaseModel):
    org_id: int
    invites: List[InviteItem]

@router.post("/invites", status_code=201)
def invite_users(body: InviteIn, db: Session = Depends(get_db), current: UserModel = Depends(get_current_active_user)):
    org = db.query(OrganizationModel).filter(OrganizationModel.id==body.org_id).first()
    if not org: raise HTTPException(404, "Organization not found")
    if current.user_type != UserType.ADMIN: raise HTTPException(403, "Only admin can invite")

    out=[]
    for inv in body.invites:
        user = get_user_by_email(db, inv.email)
        if not user:
            base = inv.email.split("@")[0]
            uname = base
            i=1
            while get_user_by_username(db, uname):
                i+=1; uname=f"{base}{i}"
            user = UserModel(email=inv.email, username=uname, hashed_password=get_password_hash("Temp@1234"),
                             user_type=UserType.ADMIN if inv.role=="ADMIN" else UserType.USER,
                             org_id=org.id)
            db.add(user); db.flush()

        for dname in inv.department_names:
            sub = db.query(DepartmentModel).filter(DepartmentModel.org_id==org.id, DepartmentModel.name==dname).first()
            if not sub:
                sub = DepartmentModel(org_id=org.id, name=dname, description=dname)
                db.add(sub); db.flush()
            acc = db.query(UserAccessDepartment).filter(
                UserAccessDepartment.org_id==org.id, UserAccessDepartment.dept_id==sub.id, UserAccessDepartment.user_id==user.id
            ).first()
            if not acc:
                acc = UserAccessDepartment(
                    org_id=org.id, dept_id=sub.id, user_id=user.id,
                    can_read=True,
                    can_upload=(inv.role in ("ADMIN","DEPT_AUTHOR")),
                    is_author=(inv.role=="DEPT_AUTHOR"),
                    neural_cap=inv.neural_cap or 1_000_000
                )
                db.add(acc)
            else:
                acc.can_read=True
                acc.can_upload=(inv.role in ("ADMIN","DEPT_AUTHOR"))
                acc.is_author=(inv.role=="DEPT_AUTHOR")
                acc.neural_cap=inv.neural_cap or acc.neural_cap
        out.append({"id": user.id, "email": user.email, "role": inv.role, "departments": inv.department_names})
    db.commit()
    return {"created_users": out}
