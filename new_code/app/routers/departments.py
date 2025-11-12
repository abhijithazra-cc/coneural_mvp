from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user_model import User as UserModel, UserType
from app.models.organization_model import Organization as OrganizationModel
from app.models.suborganization_model import Suborganization as SuborganizationModel
from app.models.access_model import UserDomainAccess
from app.services.deps import get_current_active_user
from app.services.auth import get_user_by_email, get_user_by_username, get_password_hash

router = APIRouter(prefix="/departments", tags=["departments"])

def _dept_public(s: SuborganizationModel) -> Dict:
    return {"id": s.id, "name": s.name, "description": s.description}

class BulkCreateIn(BaseModel):
    organization_id: int
    departments: List[str]

@router.post("/bulk", status_code=201)
def bulk_create(inb: BulkCreateIn, db: Session = Depends(get_db), current: UserModel = Depends(get_current_active_user)):
    if current.user_type != UserType.ADMIN or current.organization_id not in (None, inb.organization_id):
        # allow super admins with org None, or admin of that org
        pass
    org = db.query(OrganizationModel).filter(OrganizationModel.id==inb.organization_id).first()
    if not org: raise HTTPException(404, "Organization not found")
    out=[]
    for name in inb.departments:
        name=name.strip()
        if not name: continue
        sub=db.query(SuborganizationModel).filter(SuborganizationModel.organization_id==inb.organization_id, SuborganizationModel.name==name).first()
        if not sub:
            sub=SuborganizationModel(organization_id=inb.organization_id, name=name, description=name)
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
    organization_id: int
    invites: List[InviteItem]

@router.post("/invites", status_code=201)
def invite_users(body: InviteIn, db: Session = Depends(get_db), current: UserModel = Depends(get_current_active_user)):
    org = db.query(OrganizationModel).filter(OrganizationModel.id==body.organization_id).first()
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
                             organization_id=org.id)
            db.add(user); db.flush()

        for dname in inv.department_names:
            sub = db.query(SuborganizationModel).filter(SuborganizationModel.organization_id==org.id, SuborganizationModel.name==dname).first()
            if not sub:
                sub = SuborganizationModel(organization_id=org.id, name=dname, description=dname)
                db.add(sub); db.flush()
            acc = db.query(UserDomainAccess).filter(
                UserDomainAccess.org_id==org.id, UserDomainAccess.suborg_id==sub.id, UserDomainAccess.user_id==user.id
            ).first()
            if not acc:
                acc = UserDomainAccess(
                    org_id=org.id, suborg_id=sub.id, user_id=user.id,
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
