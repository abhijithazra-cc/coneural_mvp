# app/routers/documents.py

from dataclasses import Field
from enum import Enum
import io
from typing import List, Optional

from fastapi.responses import JSONResponse
# from prometheus_client import Enum
from app.Rag.VectorManager import vectorManager
from app.models.chat_thread_model import ChatThreads
import numpy as np
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from pydantic import BaseModel, Field
from fastapi import Query

from typing import Any, List, Optional
from app.models.user_model import User as UserModel
from app.models.doc_models import OrgDocument, DocChunk
from app.models.department_model import Department
from app.models.user_access_department_model import UserAccessDepartment,UserType
from app.services.auth import get_current_active_user
from app.utils.chunking import extract_text_from_file, chunk_text
# from app.Rag.text_splitters.CharacterSplitter import CharacterSplitter
from app.utils.embeddings import embed_texts
from app.utils.faiss_manager import add_vectors
from app.utils.text_extractors import extract_text
from app.Rag.utils import embeddings,BASE_DIR
from app.Rag.VectorManager import vectorManager
router = APIRouter(prefix="/org-documents", tags=["org_documents"])

# 5 MB limit as requested
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
import time
import base64

from app.utils.celery_app import celery_app
import pickle
from difflib import SequenceMatcher,context_diff
from app.Rag.CompareDoc import CompareDoc
from app.Rag.utils import ALLOWED_EXTENSIONS,validate_upload_file,MIME_MAP

def _check_duplicate(db: Session, org_id: int, dept_id: int, new_text: str, threshold: float = 0.9) -> Optional[OrgDocument]:
    """
    Check for duplicate documents in the database based on text similarity.

    Args:
        db (Session): Database session.
        org_id (int): Organization ID.
        dept_id (int): Department ID.
        new_text (str): Text of the new document to compare.
        threshold (float): Similarity threshold to consider as duplicate.

    Returns:
        Optional[OrgDocument]: The duplicate document if found, else None.
    """
    existing_docs = db.query(OrgDocument).filter(
        OrgDocument.org_id == org_id,
        OrgDocument.dept_id == dept_id
    ).all()

    compdoc=CompareDoc()    
    new_minhash = compdoc.create_minhash(new_text)
    for doc in existing_docs:
        existing_minhash = pickle.loads(doc.hash_bytes)
        similarity = new_minhash.jaccard(existing_minhash)
        print(f"Comparing with Doc ID {doc.id}: Similarity = {similarity}")
        if similarity >= threshold:
            return doc  # Duplicate found

    return None  # No duplicates found


def _ensure_org_admin(db: Session, current_user: UserModel, org_id: int) :
    org_admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    if org_admin:
        return 

    
    if not org_admin:
        raise HTTPException(
            status_code=403,
            detail="Only the organization admin can perform this action",
        )




def _ensure_org_admin_or_dept_admin_or_author(db: Session, current_user: UserModel, org_id: int, dept_id: int) :
    org_admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    if org_admin:
        return 

    dept_admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == UserType.DEPT_ADMIN,
        )
        .first()
    )
    if dept_admin:
        return
    
    dept_author = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == UserType.AUTHOR,
        )
        .first()
    )
    if not dept_author:
        raise HTTPException(
            status_code=403,
            detail="Only the organization admin or department admin or department author can perform this action",
        )

def _ensure_same_org(current: UserModel, org_id: int) -> None:
    if getattr(current, "org_id", None) != org_id:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")


def _get_dept_access(db: Session, user_id: int, org_id: int, dept_id: int) -> Optional[UserAccessDepartment]:
    return (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
        )
        .first()
    )
def _is_org_admin(db: Session, user_id: int, org_id: int) -> bool:
    row = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id.is_(None),
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    return row is not None

def _is_org_admin(db: Session, user_id: int, org_id: int) -> bool:
    row = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id.is_(None),
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    return row is not None
def _ensure_can_manage_global_docs(db: Session, current: UserModel, org_id: int) -> None:
    """
    Global docs: only Org Admin (recommended).
    """
    _ensure_same_org(current, org_id)
    if not _is_org_admin(db, current.id, org_id):
        raise HTTPException(status_code=403, detail="Only org admin can manage GLOBAL documents")
def _ensure_can_manage_dept_docs(db: Session, current: UserModel, org_id: int, dept_id: int) -> None:
    """
    Can list/update/delete dept docs if:
      - org admin OR
      - dept_access.user_type in (DEPT_ADMIN, AUTHOR)
    """
    _ensure_same_org(current, org_id)

    if _is_org_admin(db, current.id, org_id):
        return

    access = _get_dept_access(db, current.id, org_id, dept_id)
    if not access:
        raise HTTPException(status_code=403, detail="No access record for this department")

    if access.user_type in (UserType.DEPT_ADMIN, UserType.AUTHOR):
        return

    raise HTTPException(status_code=403, detail="Only org admin, dept admin, or author can manage documents")


from enum import Enum

class ScopeEnum(str, Enum):
    department = "department"
    global_scope = "global"

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Org Document (PDF/DOCX/TXT) → chunk → store → index",
)
async def upload_org_document(
    org_id: int = Form(),
    dept_id:  Optional[int] = Form(0),

    tag: str = Form(""),
    scope: ScopeEnum = Form(ScopeEnum.department),
    files:  list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    """
    Upload a document to a specific department (Department) and index it.

    Rules:
    - `dept_id` must belong to the given `org_id`.
    - Caller must be:
        * ORG ADMIN (UserType.ADMIN), or
        * The same `user_id` and have upload / author permission in `user_domain_access`.
    - We:
        * store doc metadata in `org_documents`
        * store text chunks in `doc_chunks`
        * create FAISS HNSW index for (org_id, dept_id) via `add_vectors(...)`
    """
    s=time.monotonic()
    # validate_upload_file(file=file)
    # 1) Suborg must belong to org

    print("dept id",dept_id)
    if not dept_id:
        _ensure_org_admin(db=db,current_user=current,org_id=org_id)
        doc_scope="global"
        print("global scope")
        
    else:
       
        sub = (
        db.query(Department)
        .filter(
            Department.id == dept_id,
            Department.org_id == org_id,
        )
        .first()
        )
        if not sub:
          raise HTTPException(
            status_code=404,
            detail="No access to department",
           )
        _ensure_org_admin_or_dept_admin_or_author(db=db,current_user=current,org_id=org_id,dept_id=dept_id)
        doc_scope="department"
    # 4) Read & size-check payload
    print("number of file",len(files))
    print(dept_id)
    # files=file
    for file in files:

         payload = await file.read()
         if not payload:
            raise HTTPException(status_code=400, detail="No text in File")
         if len(payload) > MAX_FILE_BYTES:
            raise HTTPException(
            status_code=413,
            detail="File too large. Max size is 5 MB.",
            )

    # 5) Extract text
         try:
            str_time=str(time.time()).replace(".","")
            filename=str(org_id)+"_"+str(current.id)+"_"+str_time+"_"+file.filename
            text,docs = extract_text(
            payload,
            filename=filename,
            mimetype=file.content_type or "",
            
              )
            new_text=text.lower()
            duplicate=_check_duplicate(db=db,org_id=org_id,dept_id=dept_id,new_text=new_text,threshold=0.8)
            if duplicate:
               raise HTTPException(
                status_code=409,
                detail=f"Duplicate document detected: {duplicate.title} (ID: {duplicate.id})",
            )
            compdoc=CompareDoc()
            m= compdoc.create_minhash(text)
            doc_hash=pickle.dumps(m)

         except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error extracting text: {str(e)}")

    # 6) Chunk text

         chunks = chunk_text(docs=docs, max_tokens=512, overlap=120)
         print("chunks",chunks)
         if not chunks:
            raise HTTPException(status_code=400, detail="No text chunks extracted from document")
    

         doc_bytes=base64.b64encode(payload)
    # if scope==ScopeEnum.global_scope:
    #     doc_scope="global"
    # else:
    #     doc_scope="department"
         
         doc = OrgDocument(
        org_id=org_id,
        
        uploaded_by=current.id,
        title=file.filename,
        tag= tag,
        scope=doc_scope,
        filename=filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(payload),
        file_bytes=doc_bytes,
        hash_bytes=doc_hash

            )
         if doc_scope=="global":
            doc.dept_id=None
         else:
            doc.dept_id=dept_id
         db.add(doc)
         db.flush()  # doc.id becomes available
    # await session.flush()  
         if doc_scope=="department":
            vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}/dept/{dept_id}")
            vectorStore.add_documents(documents=chunks,document_id=doc.id,dept_id=dept_id)
            vs=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}")
            vs.add_documents(documents=chunks,document_id=doc.id,dept_id=dept_id)
         else:
            vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}")
            vectorStore.add_documents(documents=chunks,document_id=doc.id,dept_id='global')

         db.add_all(
        [
            DocChunk(
                document_id=doc.id,
   
                content=chunk.page_content,
            )
            for i, chunk in enumerate(chunks)
        ]
        )
         db.commit()
         db.refresh(doc)

    e=time.monotonic()
    return JSONResponse(
        status_code=200,
        content={"message": "document uploaded successfully","upload_time":e-s,"number_of_files":len(files)},
    )
    # return {
    #     "doc": {
    #         "id": doc.id,
    #         "title": doc.title,
    #         "filename": doc.filename,
    #         "mime_type": doc.mime_type,
    #         "chunks": len(chunks),
    #     },
    #     "department": {"org_id": org_id, "dept_id": dept_id},
    #     "upload_time_taken":e-s,
    #     "number_of_files":len(files)

    # }


# def _ensure_org_admin(db:Session,current_user: UserModel,org_id:int) -> None:
#     """
#     Only admins of the SAME org can manage access for that org.
#     """
#     dom=db.query(UserAccessDepartment).filter(UserAccessDepartment.org_id==org_id,UserAccessDepartment.user_id==current_user.id,UserAccessDepartment.user_type==UserType.ADMIN).first()
    
#     if not dom:
#         raise HTTPException(status_code=403, detail="Only the organization admin can delete this document")
#     return dom

class DocumentOut(BaseModel):
    id: int
    org_id: int
    dept_id: Optional[int] = None
    scope: str
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: Optional[int] = None
    tag: Optional[str] = None
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: List[DocumentOut]
    total: int
    page: int
    page_size: int


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=512)
    tag: Optional[str] = Field(None, max_length=128)
@router.get(
    "/list",
    response_model=DocumentListResponse,
    summary="List documents in a department (or global). Only org_admin/dept_admin/author.",
)
def list_documents(
    org_id: int = Query(...),
    scope: str = Query("dept", description="dept or global"),
    dept_id: Optional[int] = Query(None, description="Required when scope=dept"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    scope_norm = (scope or "dept").strip().lower()
    if scope_norm not in ("dept", "global"):
        raise HTTPException(status_code=400, detail="scope must be dept or global")

    if scope_norm == "global":
        _ensure_can_manage_global_docs(db, current, org_id)
        q = db.query(OrgDocument).filter(
            OrgDocument.org_id == org_id,
            OrgDocument.dept_id.is_(None),
        )
    else:
        if dept_id is None:
            raise HTTPException(status_code=400, detail="dept_id is required when scope=dept")
        dept_id_int = int(dept_id)
        _ensure_can_manage_dept_docs(db, current, org_id, dept_id_int)

        q = db.query(OrgDocument).filter(
            OrgDocument.org_id == org_id,
            OrgDocument.dept_id == dept_id_int,
        )

    total = q.count()
    rows = (
        q.order_by(OrgDocument.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DocumentListResponse(
        items=[DocumentOut.model_validate(r, from_attributes=True) for r in rows],
        total=int(total),
        page=int(page),
        page_size=int(page_size),
    )


# ───────────────────────── NEW: Update doc metadata ─────────────────────────

@router.patch(
    "/{doc_id}",
    response_model=DocumentOut,
    summary="Update document title/tag. Only org_admin/dept_admin/author.",
)
def update_document(
    doc_id: int,
    payload: DocumentUpdateRequest,
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    doc = db.query(OrgDocument).filter(OrgDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    _ensure_same_org(current, int(doc.org_id))

    # ACL based on scope
    if getattr(doc, "dept_id", None) is None:
        _ensure_can_manage_global_docs(db, current, int(doc.org_id))
    else:
        _ensure_can_manage_dept_docs(db, current, int(doc.org_id), int(doc.dept_id))

    if payload.title is not None:
        doc.title = payload.title.strip() or doc.title
    if payload.tag is not None:
        doc.tag = payload.tag.strip() or None

    db.commit()
    db.refresh(doc)
    return DocumentOut.model_validate(doc, from_attributes=True)






@router.delete(
    "/{document_id}",
    summary="Delete document (and its chunks)",
)
def delete_org_document(
    document_id: int,
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    s=time.monotonic()
    doc = db.query(OrgDocument).filter(OrgDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Only org admin of that org can delete
    _ensure_org_admin(db=db,current_user=current,org_id=doc.org_id)

    # Deleting doc will cascade to chunks (because of FK ondelete="CASCADE" if set)
    db.delete(doc)
    db.commit()
    
    vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{current.org_id}/dept/{doc.dept_id}")
    vectorStore.delete_document_by_id(document_id=document_id)
    # vectorManager.load_store(persist_dir=f"{BASE_DIR}\{current.org_id}\dept\{doc.dept_id}")
    # NOTE: We are not removing from FAISS index here; next time you rebuild index
    # you would re-add remaining chunks. Implementing FAISS delete is possible but
    # more complex; for now this keeps DB clean and doesn't affect uploads.
    e=time.monotonic()
    return {"message": "Document deleted successfully","delete_time":e-s}

