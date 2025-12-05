from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.models.suborganization_model import Suborganization as SuborganizationModel
from app.models.organization_model import Organization as OrganizationModel
from app.models.user_model import User as UserModel
from app.services.auth import get_current_active_user
from app.schemas.suborganization_schema import SuborganizationCreate, SuborganizationUpdate
from app.database import get_db
from app.Rag.VectorManager import vectorManager
from app.Rag.utils import embeddings,BASE_DIR
router = APIRouter(prefix="/suborganizations", tags=["suborganizations"])

def _sub_public(s: SuborganizationModel) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description}

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_suborganization(suborganization: SuborganizationCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        org = db.query(OrganizationModel).filter(OrganizationModel.id == suborganization.organization_id).first()
        if not org: raise HTTPException(status_code=404, detail="Parent organization not found")
        dup = db.query(SuborganizationModel).filter(
            SuborganizationModel.name == suborganization.name,
            SuborganizationModel.organization_id == suborganization.organization_id
        ).first()
        if dup: raise HTTPException(status_code=400, detail="Suborganization name already exists in this organization")
        s = SuborganizationModel(name=suborganization.name, description=suborganization.description, organization_id=suborganization.organization_id)

        db.add(s); db.commit(); db.refresh(s)
        db.flush()
        vectorManager.create_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{suborganization.organization_id}\\dept\\{s.id}")
        return _sub_public(s)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/", status_code=status.HTTP_200_OK)
def list_suborganizations(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                          organization_id: Optional[int] = None, is_active: Optional[bool] = None,
                          db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        if organization_id is not None:
            if not db.query(OrganizationModel).filter(OrganizationModel.id == organization_id).first():
                raise HTTPException(status_code=404, detail="Organization ID not found")
        q = db.query(SuborganizationModel)
        if organization_id is not None: q = q.filter(SuborganizationModel.organization_id == organization_id)
        if is_active is not None: q = q.filter(SuborganizationModel.is_active == is_active)
        return [_sub_public(s) for s in q.offset(skip).limit(limit).all()]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/{suborganization_id}", status_code=status.HTTP_200_OK)
def get_suborganization(suborganization_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    s = db.query(SuborganizationModel).filter(SuborganizationModel.id == suborganization_id).first()
    if not s: raise HTTPException(status_code=404, detail="Suborganization not found")
    return _sub_public(s)

@router.put("/{suborganization_id}", status_code=status.HTTP_200_OK)
def update_suborganization(suborganization_id: int, sub_update: SuborganizationUpdate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        s = db.query(SuborganizationModel).filter(SuborganizationModel.id == suborganization_id).first()
        if not s: raise HTTPException(status_code=404, detail="Suborganization not found")
        if sub_update.organization_id and sub_update.organization_id != s.organization_id:
            if not db.query(OrganizationModel).filter(OrganizationModel.id == sub_update.organization_id).first():
                raise HTTPException(status_code=404, detail="Parent organization not found")
            s.organization_id = sub_update.organization_id
        if sub_update.name and sub_update.name != s.name:
            target_org_id = sub_update.organization_id if sub_update.organization_id else s.organization_id
            exists = db.query(SuborganizationModel).filter(
                SuborganizationModel.name == sub_update.name,
                SuborganizationModel.organization_id == target_org_id,
                SuborganizationModel.id != suborganization_id
            ).first()
            if exists: raise HTTPException(status_code=400, detail="Suborganization name already exists in this organization")
            s.name = sub_update.name
        if sub_update.description is not None: s.description = sub_update.description
        if sub_update.is_active is not None: s.is_active = sub_update.is_active
        db.commit(); db.refresh(s)
        return _sub_public(s)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/{suborganization_id}", status_code=status.HTTP_200_OK)
def delete_suborganization(suborganization_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        s = db.query(SuborganizationModel).filter(SuborganizationModel.id == suborganization_id).first()
        if not s: raise HTTPException(status_code=404, detail="Suborganization not found")
        db.delete(s); db.commit()
        return {"message": "Suborganization deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
