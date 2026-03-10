from sqlalchemy import select, func
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query,WebSocket,BackgroundTasks
from app.schemas.request_schema import AskRequest,AskRequestOnDocument
from sqlalchemy.orm import Session
from sqlalchemy import select
import os
# from pydantic import BaseModel,Field
from app.database import get_db
from app.services.auth import get_current_active_user,get_current_active_socket_user
from app.models.user_model import User as UserModel
from app.models.user_access_department_model import UserAccessDepartment
from app.models.department_model import Department as DepartmentModel
from app.models.doc_models import DocChunk                   #  from doc_models
# from app.models.org_document_model import OrgDocument       #  from org_document_model
from app.models.doc_models import OrgDocument,DocChunk  
from app.utils.embeddings import embed_texts
from app.models.chat_thread_model import ChatThreads

router = APIRouter(prefix="/search", tags=["search documents"])
def search_data(data:DocChunk):
    return {"document_id":data.document_id,"content":data.content}
def search_content(session, query, document_ids: list):
    q = (
        select(DocChunk)
        .where(DocChunk.document_id.in_(document_ids))   # filter by list of document_ids
        .where(func.lower(DocChunk.content).like(f"%{query.lower()}%"))
    )
    rows = session.execute(q).scalars().all()
    return [ search_data(r) for r in rows]


@router.post("/docsearch", status_code=200)
def search_documents(data: AskRequestOnDocument, db: Session = Depends(get_db), current = Depends(get_current_active_user)):
    if current.user_type not in (UserType.ADMIN, UserType.USER):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Check if user has access to the specified documents
    user_access = db.query(UserAccessDepartment).filter(
        UserAccessDepartment.user_id == current.id,
        UserAccessDepartment.org_id == data.org_id,
        UserAccessDepartment.dept_id.in_(
            db.query(OrgDocument.dept_id).filter(OrgDocument.id.in_(data.document_id))
        )
    ).first()

    if not user_access:
        raise HTTPException(status_code=403, detail="No access to the specified documents")

    # Perform the search
    results = search_content(db, data.q, data.document_id)
    print("Raw search results:", results)
    unique_results = list({r['document_id'] for r in results})
    print("Search results:", unique_results)
    return {"results": unique_results}