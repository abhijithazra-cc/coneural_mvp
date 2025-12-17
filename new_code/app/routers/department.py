from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.models.department_model import Department as DepartmentModel
from app.models.organization_model import Organization as OrganizationModel
from app.models.user_model import User as UserModel
from app.services.auth import get_current_active_user
from app.schemas.department_schema import DepartmentCreate, DepartmentUpdate

from app.database import get_db
from app.Rag.VectorManager import vectorManager
from app.Rag.utils import embeddings,BASE_DIR
router = APIRouter(prefix="/Departments", tags=["Departments"])

def _sub_public(s: DepartmentModel) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description}

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_Department(Department: DepartmentCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        org = db.query(OrganizationModel).filter(OrganizationModel.id == Department.org_id).first()
        if not org: raise HTTPException(status_code=404, detail="Parent organization not found")
        dup = db.query(DepartmentModel).filter(
            DepartmentModel.name == Department.name,
            DepartmentModel.org_id == Department.org_id
        ).first()
        if dup: raise HTTPException(status_code=400, detail="Department name already exists in this organization")
        s = DepartmentModel(name=Department.name, description=Department.description, org_id=Department.org_id)

        db.add(s); db.commit(); db.refresh(s)
        db.flush()
        vectorManager.create_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{Department.org_id}/dept/{s.id}")
        return _sub_public(s)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/", status_code=status.HTTP_200_OK)
def list_Departments(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                          org_id: Optional[int] = None, is_active: Optional[bool] = None,
                          db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        if org_id is not None:
            if not db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first():
                raise HTTPException(status_code=404, detail="Organization ID not found")
        q = db.query(DepartmentModel)
        if org_id is not None: q = q.filter(DepartmentModel.org_id == org_id)
        if is_active is not None: q = q.filter(DepartmentModel.is_active == is_active)
        return [_sub_public(s) for s in q.offset(skip).limit(limit).all()]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/{Department_id}", status_code=status.HTTP_200_OK)
def get_Department(Department_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    s = db.query(DepartmentModel).filter(DepartmentModel.id == Department_id).first()
    if not s: raise HTTPException(status_code=404, detail="Department not found")
    return _sub_public(s)

@router.put("/{Department_id}", status_code=status.HTTP_200_OK)
def update_Department(Department_id: int, sub_update: DepartmentUpdate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        s = db.query(DepartmentModel).filter(DepartmentModel.id == Department_id).first()
        if not s: raise HTTPException(status_code=404, detail="Department not found")
        if sub_update.org_id and sub_update.org_id != s.org_id:
            if not db.query(OrganizationModel).filter(OrganizationModel.id == sub_update.org_id).first():
                raise HTTPException(status_code=404, detail="Parent organization not found")
            s.org_id = sub_update.org_id
        if sub_update.name and sub_update.name != s.name:
            target_org_id = sub_update.org_id if sub_update.org_id else s.org_id
            exists = db.query(DepartmentModel).filter(
                DepartmentModel.name == sub_update.name,
                DepartmentModel.org_id == target_org_id,
                DepartmentModel.id != Department_id
            ).first()
            if exists: raise HTTPException(status_code=400, detail="Department name already exists in this organization")
            s.name = sub_update.name
        if sub_update.description is not None: s.description = sub_update.description
        if sub_update.is_active is not None: s.is_active = sub_update.is_active
        db.commit(); db.refresh(s)
        return _sub_public(s)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/{Department_id}", status_code=status.HTTP_200_OK)
def delete_Department(Department_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        s = db.query(DepartmentModel).filter(DepartmentModel.id == Department_id).first()
        if not s: raise HTTPException(status_code=404, detail="Department not found")
        db.delete(s); db.commit()
        return {"message": "Department deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
