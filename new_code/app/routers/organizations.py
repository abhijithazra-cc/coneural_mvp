from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.models.organization_model import Organization as OrganizationModel
from app.models.user_model import User as UserModel
from app.services.auth import get_current_active_user
from app.schemas.organization_schema import OrganizationCreate, OrganizationUpdate
from app.database import get_db
from app.Rag.VectorManager import vectorManager
from app.Rag.utils import embeddings,BASE_DIR 
from app.models.user_access_department_model import UserType,UserAccessDepartment
router = APIRouter(prefix="/organizations", tags=["organizations"],
    responses={400: {"description": "Bad Request"}, 401: {"description": "Unauthorized"},
               404: {"description": "Not Found"}, 500: {"description": "Internal Server Error"}})

def _org_public(o: OrganizationModel) -> dict:
    return {"id": o.id, "name": o.name, "description": o.description}

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_organization(
    organization: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    try:
        existing = db.query(OrganizationModel).filter(OrganizationModel.name == organization.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Organization name already exists")
        org = OrganizationModel(name=organization.name, description=organization.description)
        user_access = UserAccessDepartment(
            org_id=org.id,
          
            user_id=current_user.id,
            user_type=UserType.ADMIN
        )
        db.add(user_access)
        db.add(org); db.commit(); db.refresh(org)
        db.flush()
        print("org_id",org.id)
        vectorManager.create_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org.id}")
        return _org_public(org)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/", status_code=status.HTTP_200_OK)
def list_organizations(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None, name: Optional[str] = None,
    db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user),
):
    try:
        q = db.query(OrganizationModel)
        if is_active is not None: q = q.filter(OrganizationModel.is_active == is_active)
        if name: q = q.filter(OrganizationModel.name.ilike(f"%{name}%"))
        return [_org_public(o) for o in q.offset(skip).limit(limit).all()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/{org_id}", status_code=status.HTTP_200_OK)
def get_organization(org_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
    if not org: raise HTTPException(status_code=404, detail="Organization not found")
    return _org_public(org)

@router.put("/{org_id}", status_code=status.HTTP_200_OK)
def update_organization(org_id: int, organization_update: OrganizationUpdate,
                        db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
        admin=db.query(UserModel).join(UserAccessDepartment,
            (UserAccessDepartment.user_id==UserModel.id) & 
            (UserAccessDepartment.org_id==org_id) & 
            (UserAccessDepartment.user_type==UserType.ADMIN)
        ).filter(UserModel.id==current_user.id).first()
        if not admin:
            raise HTTPException(status_code=403, detail="You do not have permission to update this organization")
        if not org: raise HTTPException(status_code=404, detail="Organization not found")
        if organization_update.organization_name and organization_update.organization_name != org.name:
            conflict = db.query(OrganizationModel).filter(OrganizationModel.name == organization_update.organization_name,
                                                          OrganizationModel.id != org_id).first()
            if conflict: raise HTTPException(status_code=400, detail="Organization name already exists")
            org.name = organization_update.organization_name
        if organization_update.country is not None: org.description = organization_update.country
        if organization_update.website_url is not None: org.website_url = organization_update.website_url   
        if organization_update.industry is not None: org.industry = organization_update.industry
        if organization_update.company_size is not None: org.company_size = organization_update.company_size
        if organization_update.social_handles is not None: org.social_handles = organization_update.social_handles
        if hasattr(organization_update, "is_active") and organization_update.is_active is not None:
            org.is_active = organization_update.is_active
        if organization_update.your_name is not None: admin.username = organization_update.your_name
        # if organization_update.name and organization_update.name != org.name:
        #     conflict = db.query(OrganizationModel).filter(OrganizationModel.name == organization_update.name,
        #                                                   OrganizationModel.id != org_id).first()
        #     if conflict: raise HTTPException(status_code=400, detail="Organization name already exists")
        #     org.name = organization_update.name
        # if organization_update.description is not None: org.description = organization_update.description
        # if hasattr(organization_update, "is_active") and organization_update.is_active is not None:
        #     org.is_active = organization_update.is_active
        db.commit(); db.refresh(org)
        return _org_public(org)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/{org_id}", status_code=status.HTTP_200_OK)
def delete_organization(org_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_active_user)):
    try:
        org = db.query(OrganizationModel).filter(OrganizationModel.id == org_id).first()
        if not org: raise HTTPException(status_code=404, detail="Organization not found")
        db.delete(org); db.commit()
        return {"message": "Organization deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
