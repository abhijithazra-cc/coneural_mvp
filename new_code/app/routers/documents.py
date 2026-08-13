# app/routers/documents.py

from dataclasses import Field
from enum import Enum
import io
from typing import List, Optional

from sqlalchemy import MetaData, Table
from app.services.embedding_token import user_license_and_token_update,_count_tokens_for_openai_embeddings,dept_license_and_token_update,user_license_and_token_update,org_license_and_token_update
from fastapi.responses import JSONResponse
from sqlalchemy import update, select, Table, MetaData
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
from app.Rag.CompareDoc import CompareDoc
import pickle
router = APIRouter(prefix="/org-documents", tags=["org_documents"])

# 5 MB limit as requested
MAX_FILE_BYTES = 50 * 1024 * 1024  # 5 MB
import time
import base64

from app.utils.celery_app import celery_app,upload_file_to_db_task
from app.services.document import _ensure_org_admin,_ensure_org_admin_or_dept_admin_or_author,_ensure_can_manage_global_docs,_ensure_can_manage_dept_docs,_ensure_same_org,_check_duplicate
from app.database import SessionLocal
import base64, pickle, time, traceback
from celery import shared_task


from enum import Enum

class ScopeEnum(str, Enum):
    department = "department"
    global_scope = "global"




# @router.post(
#     "/",
#     status_code=status.HTTP_201_CREATED,
#     summary="Upload Org Document (PDF/DOCX/TXT) → chunk → store → index",
# )
# async def upload_org_document(
#     org_id: int = Form(),
#     dept_id:  Optional[int] = Form(0),

#     tag: str = Form(""),
#     scope: ScopeEnum = Form(ScopeEnum.department),
#     files:  list[UploadFile] = File(...),
#     db: Session = Depends(get_db),
#     current: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Upload a document to a specific department (Department) and index it.

#     Rules:
#     - `dept_id` must belong to the given `org_id`.
#     - Caller must be:
#         * ORG ADMIN (UserType.ADMIN), or
#         * The same `user_id` and have upload / author permission in `user_domain_access`.
#     - We:
#         * store doc metadata in `org_documents`
#         * store text chunks in `doc_chunks`
#         * create FAISS HNSW index for (org_id, dept_id) via `add_vectors(...)`
#     """
#     s=time.monotonic()
    
#     if not dept_id:
#         _ensure_org_admin(db=db,current_user=current,org_id=org_id)
#         doc_scope="global"
         
#     else:
       
#         sub = (
#         db.query(Department)
#         .filter(
#             Department.id == dept_id,
#             Department.org_id == org_id,
#         )
#         .first()
#         )
#         if not sub:
#           raise HTTPException(
#             status_code=404,
#             detail="No access to department",
#            )
#         _ensure_org_admin_or_dept_admin_or_author(db=db,current_user=current,org_id=org_id,dept_id=dept_id)
#         doc_scope="department"

#     for file in files:

#          payload = await file.read()
#          if not payload:
#             raise HTTPException(status_code=400, detail="No text in File")
#          if len(payload) > MAX_FILE_BYTES:
#             raise HTTPException(
#             status_code=413,
#             detail="File too large. Max size is 5 MB.",
#             )

#     # 5) Extract text
#          try:
#             str_time=str(time.time()).replace(".","")
#             filename=str(org_id)+"_"+str(current.id)+"_"+str_time+"_"+file.filename
#             text,docs = extract_text(
#             payload,
#             filename=filename,
#             mimetype=file.content_type or "",
            
#               )
#             new_text=text.lower()
#             print("extracted text length",len(new_text))
#             print("extacted content",new_text)
#             duplicate=_check_duplicate(db=db,org_id=org_id,dept_id=dept_id,new_text=new_text,threshold=0.8)
#             # if duplicate:
#             #    raise HTTPException(
#             #     status_code=409,
#             #     detail=f"Duplicate document detected: {duplicate.title} (ID: {duplicate.id})",
#             # )
#             compdoc=CompareDoc()
#             m= compdoc.create_minhash(text)
#             doc_hash=pickle.dumps(m)

#          except Exception as e:
#             raise HTTPException(status_code=400, detail=f"Error extracting text: {str(e)}")

#     # 6) Chunk text

#          chunks = chunk_text(docs=docs, max_tokens=512, overlap=120)
#         #  print("chunks",chunks)
#          if not chunks:
#             raise HTTPException(status_code=400, detail="No text chunks extracted from document")
#          with open(f"app/filedata/{filename}", "wb") as f:
#             f.write(payload)

#          doc_bytes=base64.b64encode(payload)
#     # if scope==ScopeEnum.global_scope:
#     #     doc_scope="global"
#     # else:
#     #     doc_scope="department"
         
#          doc = OrgDocument(
#         org_id=org_id,
        
#         uploaded_by=current.id,
#         title=file.filename,
#         tag= tag,
#         scope=doc_scope,
#         filename=filename,
#         mime_type=file.content_type or "application/octet-stream",
#         size_bytes=len(payload),
#         file_bytes=doc_bytes,
#         hash_bytes=doc_hash

#             )
#          if doc_scope=="global":
#             doc.dept_id=None
#          else:
#             doc.dept_id=dept_id
#          db.add(doc)
#          db.flush()  # doc.id becomes available
#     # await session.flush()  
#          if doc_scope=="department":

#             vs=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}")
#             vs.add_documents(documents=chunks,document_id=doc.id,dept_id=dept_id)
#          else:
#             vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}")
#             vectorStore.add_documents(documents=chunks,document_id=doc.id,dept_id='global')
#          token=0
#          for chunk in chunks:
#                  token+=_count_tokens_for_openai_embeddings(model_name="text-embedding-ada-002",texts=[chunk.page_content])
#          print("total tokens for embedding",token)
         
         
#          if dept_id and doc_scope=="department":
#             user_license_and_token_update(db=db,user_id=current.id,dept_id=dept_id,tokens_used=token)
#             dept_license_and_token_update(db=db,dept_id=dept_id,org_id=org_id,tokens_used=token)
#          else :

#              org_license_and_token_update(db=db,org_id=org_id,tokens_used=token)
#          db.add_all(
#         [
#             DocChunk(
#                 document_id=doc.id,
   
#                 content=chunk.page_content,
#             )
#             for i, chunk in enumerate(chunks)
#         ]
#         )
#          db.commit()
#          db.refresh(doc)

#     e=time.monotonic()
#     return JSONResponse(
#         status_code=200,
#         content={"message": "document uploaded successfully","upload_time":e-s,"number_of_files":len(files)},
#     )


# from app.utils.celery_app import upload_pipeline


# from app.utils.celery_app import celery_app

from fastapi import HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.models.user_access_department_model import UserAccessDepartment, UserType as AccessUserType
from app.models.department_model import Department as DepartmentModel
from app.models.user_model import User as UserModel
from langsmith import traceable

@traceable(name="check_if_org_admin", project="core", metadata={"description": "Check if user is org admin"}, tags=["documents"])
def _is_org_admin(db: Session, user_id: int, org_id: int) -> bool:
    row = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user_id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id.is_(None),
            UserAccessDepartment.user_type == AccessUserType.ADMIN,
        )
        .first()
    )
    return row is not None

@traceable(name="ensure_same_org", project="core", metadata={"description": "Ensure user belongs to the same organization"}, tags=["documents"])
def _ensure_same_org(current: UserModel, org_id: int) -> None:
    if getattr(current, "org_id", None) != org_id:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")


@traceable(name="get_dept_access", project="core", metadata={"description": "Get department access record"}, tags=["documents"])
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


@traceable(name="ensure_can_manage_dept_docs", project="core", metadata={"description": "Ensure user can manage documents for a specific department"}, tags=["documents"])
def _ensure_can_manage_dept_docs(db: Session, current: UserModel, org_id: int, dept_id: int) -> None:
    _ensure_same_org(current, org_id)

    if _is_org_admin(db, current.id, org_id):
        return

    access = _get_dept_access(db, current.id, org_id, dept_id)
    if not access:
        raise HTTPException(status_code=403, detail="No access record for this department")

    if access.user_type in (AccessUserType.DEPT_ADMIN, AccessUserType.AUTHOR):
        return

    raise HTTPException(status_code=403, detail="Only org admin, dept admin, or author can manage documents")


@traceable(name="ensure_can_manage_global_docs", project="core", metadata={"description": "Ensure user can manage GLOBAL documents"}, tags=["documents"])
def _ensure_can_manage_global_docs(db: Session, current: UserModel, org_id: int) -> None:
    _ensure_same_org(current, org_id)
    if not _is_org_admin(db, current.id, org_id):
        raise HTTPException(status_code=403, detail="Only org admin can manage GLOBAL documents")


# from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
# from sqlalchemy.orm import Session
# from typing import Optional

# from app.database import get_db
# from app.services.auth import get_current_active_user
# from app.models.user_model import User as UserModel
# from app.models.department_model import Department as DepartmentModel
# from app.schemas.enums import ScopeEnum  # wherever your ScopeEnum is
# from app.celery_tasks import upload_file_to_db_task  # adjust import
# import time



MAX_FILE_BYTES = 50 * 1024 * 1024  # example, keep your existing

from app.Rag.DocumentConverter import DocumentConverter
converter = DocumentConverter()

from fastapi import Response
@router.post("/convert")
async def convert(file: UploadFile):
    file_bytes = await file.read()
    pdf_bytes = converter.convert_to_pdf_bytes(file_bytes, file.filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={file.filename}.pdf"
        },
    )


from fastapi.responses import FileResponse
@traceable(name="get_file_bytes", project="core", metadata={"description": "Retrieve file bytes for a given document ID"}, tags=["documents"])
def get_file_bytes(db: Session, document_id: int,current: UserModel) -> bytes:
    if document_id <= 0:
        doc = db.query(OrgDocument).filter(OrgDocument.id == document_id,OrgDocument.org_id == current.org_id,OrgDocument.dept_id.is_(None)).first()
    else:
        doc = db.query(OrgDocument).filter(OrgDocument.id == document_id,OrgDocument.org_id == current.org_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return base64.b64decode(doc.file_bytes),doc.filename    

@router.get("/download/{doc_id}")
async def download_file(db: Session=Depends(get_db), doc_id: int = 0,current=Depends(get_current_active_user)):
    print("download doc_id",doc_id)
    print("current user",current.org_id,current.id)
    file_bytes,filename = get_file_bytes(db, int(doc_id), current=current)
    with open(f"app/filedata/{filename}", "rb") as f:
        file_bytes = f.read()
    # file_bytes=
    return Response(
        content=file_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )
        

async def upload_documents(dept_id: Optional[int], tag: str, scope: ScopeEnum, files: list[UploadFile], db: Session, current: UserModel):
        if dept_id is None:
            doc_scope="global"
        # if scope == ScopeEnum.global_scope:
            # scope_norm = "global"
        else:
            doc_scope="dept"
            # scope_norm = "dept"  # "department" also ok; keep consistent with rest of code
        # print("doc_scope",doc_scope,"scope_norm",scope_norm)
        # ---- access control + dept validation ----
        if doc_scope == "global":
            _ensure_can_manage_global_docs(db, current, current.org_id)
            dept_id_final = None
            doc_scope = "global"
        else:
            if dept_id is None:
                raise HTTPException(status_code=400, detail="dept_id is required when scope is department")
    
            dept_id_final = int(dept_id)
    
            dept_row = (
                db.query(DepartmentModel)
                .filter(DepartmentModel.id == dept_id_final, DepartmentModel.org_id == current.org_id)
                .first()
            )
            if not dept_row:
                raise HTTPException(status_code=404, detail="Department not found in this organization")
    
            _ensure_can_manage_dept_docs(db, current, current.org_id, dept_id_final)
            doc_scope = "department"
    
        # ---- schedule tasks ----
        response_list = []
        for file in files:
            payload = await file.read()
    
            if not payload:
                raise HTTPException(status_code=400, detail=f"Empty file: {file.filename}")
    
            if len(payload) > MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {file.filename}. Max size is {MAX_FILE_BYTES} bytes.",
                )
            original_filename=file.filename.replace(" ", "_")
            
            filename = f"{current.org_id}_{current.id}_{int(time.time())}_{original_filename}"
            Path(f"app/filedata/{filename}").write_bytes(payload)
            task = upload_file_to_db_task.delay(
                payload=payload,
                original_filename=original_filename,
                filename=filename,
                content_type=file.content_type,
                org_id=current.org_id,
                dept_id=dept_id_final,   # None for global
                user_id=current.id,
                tag=tag,
                doc_scope=doc_scope,
            )
            response_list.append({"filename": file.filename, "task_id": task.id})
    
        return {"message": "Upload started", "response": response_list}


from pathlib import Path






@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Org Document (PDF/DOCX/TXT) → chunk → store → index",
)
async def upload_doc(
 
    dept_id: Optional[int] = Form(None),
    tag: str = Form(""),
    scope: ScopeEnum = Form(ScopeEnum.department),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    # ---- normalize scope (match your earlier router semantics) ----
    # You used ScopeEnum.global_scope vs ScopeEnum.department earlier.
    # Map that to string scope for storage/task payload.
    
     res=await upload_documents(dept_id=dept_id, tag=tag, scope=scope, files=files, db=db, current=current)
     return res
# @router.post(
#     "/",
#     status_code=status.HTTP_201_CREATED,
#     summary="Upload Org Document (PDF/DOCX/TXT) → chunk → store → index",
# )
# async def upload_doc(
#     org_id: int = Form(),
#     dept_id:  Optional[int] = Form(0),

#     tag: str = Form(""),
#     scope: ScopeEnum = Form(ScopeEnum.department),
#     files:  list[UploadFile] = File(...),
#     db: Session = Depends(get_db),
#     current: UserModel = Depends(get_current_active_user),

# ):
#     # payload = await file.read()

#     # file_path = f"/tmp/{time.time()}_{file.filename}"
#     # with open(file_path, "wb") as f:
#     #     f.write(payload)
#     response_list=[]
#     for file in files:

#          payload = await file.read()
#          if not payload:
#             raise HTTPException(status_code=400, detail="No text in File")
#          if len(payload) > MAX_FILE_BYTES:
#             raise HTTPException(
#             status_code=413,
#             detail="File too large. Max size is 5 MB.",
#             )
#          if scope==ScopeEnum.global_scope:
#            doc_scope="global"
#          else:
#            doc_scope="department"

#          task = upload_file_to_db_task.delay(
#         payload=payload,
#         original_filename=file.filename,
#         content_type=file.content_type,
#         org_id=org_id,
#         dept_id=dept_id,
#         user_id=current.id,
#         tag=tag,
#         doc_scope=doc_scope,
#         )
#          response_list.append({"filename": file.filename, "task_id": task.id})

#     return {
#         "message": "Upload started",
#         "response": response_list,
#     }


from langchain_community.callbacks.manager import get_openai_callback


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
            OrgDocument.deleted_at.isnot(None),
            
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


from fastapi.responses import StreamingResponse

@router.get("/document_content/{document_id}", summary="Get document content by id")
def get_document_content(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    document = (
        db.query(OrgDocument)
        .filter(
            
            OrgDocument.id == document_id,
            OrgDocument.org_id == current_user.org_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    pdf_bytes = base64.b64decode(document.file_bytes)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",headers={"Content-Disposition": f"inline"})


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
    vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{current.org_id}")
    vectorStore.delete_document_by_id(document_id=document_id)
    # Deleting doc will cascade to chunks (because of FK ondelete="CASCADE" if set)
    db.delete(doc)
    db.commit()
    

    # vectorManager.load_store(persist_dir=f"{BASE_DIR}\{current.org_id}\dept\{doc.dept_id}")
    # NOTE: We are not removing from FAISS index here; next time you rebuild index
    # you would re-add remaining chunks. Implementing FAISS delete is possible but
    # more complex; for now this keeps DB clean and doesn't affect uploads.
    e=time.monotonic()
    return {"message": "Document deleted successfully","delete_time":e-s}






# """
# FastAPI RAG service — LangChain + FAISS edition
# -------------------------------------------------
# Upload a document -> parse it with LlamaCloud -> chunk with LangChain's
# RecursiveCharacterTextSplitter -> embed + store in a LangChain FAISS
# vector store -> query the document with a LangChain ChatOpenAI model using
# retrieved chunks as context.

# Run:
#     pip install -r requirements.txt
#     export OPENAI_API_KEY=sk-...
#     export LLAMA_CLOUD_API_KEY=llx-...
#     uvicorn app:app --reload

# Endpoints:
#     POST /upload            -> upload + parse + embed a document, returns doc_id
#     POST /query              -> ask a question about a previously uploaded doc_id
#     GET  /documents          -> list uploaded documents
#     DELETE /documents/{id}   -> remove a document's index (memory + disk)
# """

# import os
# import uuid
# import shutil
# import tempfile
# from typing import List, Dict, Optional

# from fastapi import FastAPI, UploadFile, File, HTTPException
# from pydantic import BaseModel
# from starlette.concurrency import run_in_threadpool

# from llama_cloud import AsyncLlamaCloud

# from langchain_core.documents import Document
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.vectorstores import FAISS
# from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# # ---------------------------------------------------------------------------
# # Config
# # ---------------------------------------------------------------------------

# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# LLAMA_CLOUD_API_KEY = os.environ.get("LLAMA_CLOUD_API_KEY")

# EMBEDDING_MODEL = "text-embedding-3-small"
# CHAT_MODEL = "gpt-5.2"

# CHUNK_SIZE = 512       # characters per chunk
# CHUNK_OVERLAP = 128     # character overlap between chunks
# TOP_K = 4               # number of chunks retrieved per query

# PERSIST_DIR = "faiss_indexes"   # each doc's FAISS index is saved to PERSIST_DIR/{doc_id}
# MARKDOWN_DIR = "parsed_markdown"  # each doc's raw parsed markdown is saved to MARKDOWN_DIR/{doc_id}.md

# if not OPENAI_API_KEY:
#     raise RuntimeError("Set the OPENAI_API_KEY environment variable.")
# if not LLAMA_CLOUD_API_KEY:
#     raise RuntimeError("Set the LLAMA_CLOUD_API_KEY environment variable.")

# llama_client = AsyncLlamaCloud(api_key=LLAMA_CLOUD_API_KEY)
# embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
# llm = ChatOpenAI(model=CHAT_MODEL, api_key=OPENAI_API_KEY, temperature=0.2)

# text_splitter = RecursiveCharacterTextSplitter(
#     chunk_size=CHUNK_SIZE,
#     chunk_overlap=CHUNK_OVERLAP,
# )

# PROMPT = ChatPromptTemplate.from_messages(
#     [
#         (
#             "system",
#             "You are a helpful assistant that answers questions using ONLY the "
#             "provided document context. If the answer isn't in the context, say so.",
#         ),
#         ("human", "Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"),
#     ]
# )

# # app = FastAPI(title="RAG API (LlamaCloud + LangChain FAISS + OpenAI)")

# # ---------------------------------------------------------------------------
# # In-memory store: doc_id -> {"vectorstore": FAISS, "filename": str, "num_chunks": int}
# # Each vector store is also persisted to disk under PERSIST_DIR/{doc_id}, so it
# # survives a restart and can be lazily reloaded in /query.
# # ---------------------------------------------------------------------------

# DOC_STORE: Dict[str, Dict] = {}


# # ---------------------------------------------------------------------------
# # Helpers
# # ---------------------------------------------------------------------------

# async def parse_document(file_path: str) -> str:
#     """Send the file to LlamaCloud and return the parsed markdown text."""
#     file_obj = await llama_client.files.create(file=file_path, purpose="parse")
#     result = await llama_client.parsing.parse(
#         file_id=file_obj.id,
#         tier="agentic",
#         version="latest",
#         expand=["markdown_full"],
#     )
#     return result.markdown_full


# def _save_markdown(text: str, doc_id: str) -> str:
#     """Persist the raw parsed markdown to MARKDOWN_DIR/{doc_id}.md and return its path."""
#     os.makedirs(MARKDOWN_DIR, exist_ok=True)
#     path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     with open(path, "w", encoding="utf-8") as f:
#         f.write(text)
#     return path


# def _split_into_documents(text: str, doc_id: str, filename: str) -> List[Document]:
#     chunks = text_splitter.split_text(text)
#     return [
#         Document(
#             page_content=chunk,
#             metadata={"doc_id": doc_id, "filename": filename, "chunk_index": i},
#         )
#         for i, chunk in enumerate(chunks)
#     ]


# async def _build_vector_store(text: str, doc_id: str, filename: str) -> FAISS:
#     """Chunk the text and build a LangChain FAISS vector store (off the event loop)."""
#     documents = _split_into_documents(text, doc_id, filename)
#     if not documents:
#         raise ValueError("No chunks could be produced from this document.")

#     # FAISS.from_documents calls the (sync) embeddings API under the hood, so
#     # run it in a thread to avoid blocking the event loop.
#     vectorstore = await run_in_threadpool(FAISS.from_documents, documents, embeddings)
#     return vectorstore


# async def _persist_vector_store(vectorstore: FAISS, doc_id: str) -> None:
#     os.makedirs(PERSIST_DIR, exist_ok=True)
#     path = os.path.join(PERSIST_DIR, doc_id)
#     await run_in_threadpool(vectorstore.save_local, path)


# async def _load_vector_store_from_disk(doc_id: str) -> Optional[FAISS]:
#     path = os.path.join(PERSIST_DIR, doc_id)
#     if not os.path.isdir(path):
#         return None
#     return await run_in_threadpool(
#         FAISS.load_local, path, embeddings, allow_dangerous_deserialization=True
#     )


# async def _get_doc_entry(doc_id: str) -> Optional[Dict]:
#     """Look up a document's vector store, falling back to the on-disk index."""
#     doc = DOC_STORE.get(doc_id)
#     if doc is not None:
#         return doc

#     vectorstore = await _load_vector_store_from_disk(doc_id)
#     if vectorstore is None:
#         return None

#     markdown_path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     doc = {
#         "vectorstore": vectorstore,
#         "filename": None,
#         "num_chunks": vectorstore.index.ntotal,
#         "markdown_path": markdown_path if os.path.isfile(markdown_path) else None,
#     }
#     DOC_STORE[doc_id] = doc
#     return doc


# # ---------------------------------------------------------------------------
# # Schemas
# # ---------------------------------------------------------------------------

# class QueryRequest(BaseModel):
#     doc_id: str
#     question: str
#     top_k: int = TOP_K


# class QueryResponse(BaseModel):
#     answer: str
#     sources: List[str]


# class UploadResponse(BaseModel):
#     doc_id: str
#     filename: str
#     num_chunks: int
#     markdown_path: str


# # ---------------------------------------------------------------------------
# # Routes
# # ---------------------------------------------------------------------------

# @router.post("/upload", response_model=UploadResponse)
# async def upload_document(file: UploadFile = File(...)):
#     """Upload a file, parse it via LlamaCloud, and build a LangChain FAISS index."""
#     suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
#     tmp_path = None
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = tmp.name

#         markdown_text = await parse_document(tmp_path)
#         if not markdown_text or not markdown_text.strip():
#             raise HTTPException(status_code=422, detail="LlamaCloud returned empty content for this file.")

#         doc_id = str(uuid.uuid4())
#         markdown_path = await run_in_threadpool(_save_markdown, markdown_text, doc_id)

#         try:
#             vectorstore = await _build_vector_store(markdown_text, doc_id, file.filename)
#         except ValueError as exc:
#             raise HTTPException(status_code=422, detail=str(exc))

#         await _persist_vector_store(vectorstore, doc_id)

#         num_chunks = vectorstore.index.ntotal
#         DOC_STORE[doc_id] = {
#             "vectorstore": vectorstore,
#             "filename": file.filename,
#             "num_chunks": num_chunks,
#             "markdown_path": markdown_path,
#         }

#         return UploadResponse(
#             doc_id=doc_id,
#             filename=file.filename,
#             num_chunks=num_chunks,
#             markdown_path=markdown_path,
#         )

#     finally:
#         if tmp_path and os.path.exists(tmp_path):
#             os.remove(tmp_path)


# @router.post("/query", response_model=QueryResponse)
# async def query_document(payload: QueryRequest):
#     """Answer a question about a previously uploaded document using retrieved chunks + OpenAI."""
#     doc = await _get_doc_entry(payload.doc_id)
#     if doc is None:
#         raise HTTPException(status_code=404, detail="doc_id not found. Upload a document first.")

#     vectorstore: FAISS = doc["vectorstore"]
#     retriever = vectorstore.as_retriever(
#         search_type="similarity",
#         search_kwargs={"k": payload.top_k},
#     )

#     retrieved_docs = await retriever.ainvoke(payload.question)
#     context = "\n\n---\n\n".join(d.page_content for d in retrieved_docs)

#     messages = PROMPT.format_messages(context=context, question=payload.question)
#     response = await llm.ainvoke(messages)

#     return QueryResponse(answer=response.content, sources=[d.page_content for d in retrieved_docs])


# @router.get("/documents")
# async def list_documents():
#     return [
#         {
#             "doc_id": doc_id,
#             "filename": doc["filename"],
#             "num_chunks": doc["num_chunks"],
#             "markdown_path": doc.get("markdown_path"),
#         }
#         for doc_id, doc in DOC_STORE.items()
#     ]


# @router.delete("/documents/{doc_id}")
# async def delete_document(doc_id: str):
#     existed_in_memory = DOC_STORE.pop(doc_id, None) is not None

#     path = os.path.join(PERSIST_DIR, doc_id)
#     existed_on_disk = os.path.isdir(path)
#     if existed_on_disk:
#         shutil.rmtree(path)

#     markdown_path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     if os.path.isfile(markdown_path):
#         os.remove(markdown_path)

#     if not existed_in_memory and not existed_on_disk:
#         raise HTTPException(status_code=404, detail="doc_id not found.")

#     return {"status": "deleted", "doc_id": doc_id}


# @router.get("/documents/{doc_id}/markdown")
# async def get_markdown(doc_id: str):
#     """Return the raw parsed markdown that was saved for this document."""
#     doc = await _get_doc_entry(doc_id)
#     if doc is None or not doc.get("markdown_path") or not os.path.isfile(doc["markdown_path"]):
#         raise HTTPException(status_code=404, detail="Markdown not found for this doc_id.")

#     with open(doc["markdown_path"], "r", encoding="utf-8") as f:
#         content = f.read()

#     return {"doc_id": doc_id, "markdown": content}


# # @app.get("/health")
# # async def health():
# #     return {"status": "ok"}


######################################################################################################

"""
FastAPI RAG service — LangChain + FAISS edition
-------------------------------------------------
Upload a document -> parse it with LlamaCloud -> chunk with LangChain's
RecursiveCharacterTextSplitter -> embed + store in a LangChain FAISS
vector store -> query the document with a LangChain ChatOpenAI model using
retrieved chunks as context.

Run:
    pip install -r requirements.txt
    export OPENAI_API_KEY=sk-...
    export LLAMA_CLOUD_API_KEY=llx-...
    uvicorn app:app --reload

Endpoints:
    POST /upload            -> upload + parse + embed a document, returns doc_id
    POST /query              -> ask a question about a previously uploaded doc_id
                                 (streams back plain text + stage markers, same
                                 protocol as the QA service)
    GET  /documents          -> list uploaded documents
    DELETE /documents/{id}   -> remove a document's index (memory + disk)
"""

# import json
# import os
# import uuid
# import shutil
# import tempfile
# from typing import AsyncGenerator, List, Dict, Optional

# from fastapi import FastAPI, UploadFile, File, HTTPException
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel
# from starlette.concurrency import run_in_threadpool

# from llama_cloud import AsyncLlamaCloud

# from langchain_core.documents import Document
# from langchain_core.messages import SystemMessage, HumanMessage
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.vectorstores import FAISS
# from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# # ---------------------------------------------------------------------------
# # Config
# # ---------------------------------------------------------------------------

# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# LLAMA_CLOUD_API_KEY = os.environ.get("LLAMA_CLOUD_API_KEY")

# EMBEDDING_MODEL = "text-embedding-3-small"
# CHAT_MODEL = "gpt-5.2"

# CHUNK_SIZE = 1024       # characters per chunk
# CHUNK_OVERLAP = 128     # character overlap between chunks
# TOP_K = 10               # number of chunks retrieved per query

# PERSIST_DIR = "faiss_indexes"   # each doc's FAISS index is saved to PERSIST_DIR/{doc_id}
# MARKDOWN_DIR = "parsed_markdown"  # each doc's raw parsed markdown is saved to MARKDOWN_DIR/{doc_id}.md

# if not OPENAI_API_KEY:
#     raise RuntimeError("Set the OPENAI_API_KEY environment variable.")
# if not LLAMA_CLOUD_API_KEY:
#     raise RuntimeError("Set the LLAMA_CLOUD_API_KEY environment variable.")

# llama_client = AsyncLlamaCloud(api_key=LLAMA_CLOUD_API_KEY)
# embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
# llm = ChatOpenAI(model=CHAT_MODEL, api_key=OPENAI_API_KEY, temperature=0.2, streaming=True)

# text_splitter = RecursiveCharacterTextSplitter(
#     chunk_size=CHUNK_SIZE,
#     chunk_overlap=CHUNK_OVERLAP,
# )

# # Same "clean markdown" system prompt style as the QA streaming service --
# # but scoped to answering strictly from the provided document context.
# SYSTEM_PROMPT_TEMPLATE = """You are a helpful assistant that answers questions using ONLY the
# provided document context. If the answer isn't in the context, say so plainly instead of
# guessing. Respond in clean markdown.

# Guidelines:
# - Use "## " headings only when they genuinely help organize a longer answer.
# - Use a markdown table whenever comparing 2+ things across shared attributes.
# - Use bullet lists ("- ") for flat, non-comparable lists.
# - Use short paragraphs for everything else.

# MATH:
# The renderer (Streamdown + KaTeX) ONLY recognizes double-dollar delimiters for math, for
# BOTH inline and block expressions. Do not use \\( \\), \\[ \\], or single $ -- none of those
# are recognized and will render as broken literal text.
# - Inline math: $$x^2 + y^2 = z^2$$ written inline within a sentence.
# - Block/display math: put $$ on its own line, the expression on the next line(s), then a
#   closing $$ on its own line.
# - Do not use \\tag{{...}} for equation numbering (unsupported) -- refer back to an equation
#   in words instead (e.g. "from the first equation").
# - \\boxed{{...}} is fine to use inside a $$...$$ block to highlight a final result.
# - Never leave a $$ block unterminated.

# Context:
# {context}
# """

# # Control token the frontend strips out of the visible markdown -- used to
# # ship structured metadata (retrieved sources) after the streamed answer.
# META_MARKER = "===STREAM_META==="

# # app = FastAPI(title="RAG API (LlamaCloud + LangChain FAISS + OpenAI)")

# # ---------------------------------------------------------------------------
# # In-memory store: doc_id -> {"vectorstore": FAISS, "filename": str, "num_chunks": int}
# # Each vector store is also persisted to disk under PERSIST_DIR/{doc_id}, so it
# # survives a restart and can be lazily reloaded in /query.
# # ---------------------------------------------------------------------------

# DOC_STORE: Dict[str, Dict] = {}


# # ---------------------------------------------------------------------------
# # Helpers
# # ---------------------------------------------------------------------------

# def stage(label: str) -> str:
#     """Build a stage marker token, e.g. stage('retrieving relevant chunks')."""
#     return f"[[STAGE:{label}]]"


# async def parse_document(file_path: str) -> str:
#     """Send the file to LlamaCloud and return the parsed markdown text."""
    
#     file_obj = await llama_client.files.create(file=file_path, purpose="parse")
#     result = await llama_client.parsing.parse(
#         file_id=file_obj.id,
#         tier="agentic",
#         version="latest",
#         expand=["markdown_full"],
        
#     )
    
#     return result.markdown_full


# def _save_markdown(text: str, doc_id: str) -> str:
#     """Persist the raw parsed markdown to MARKDOWN_DIR/{doc_id}.md and return its path."""
#     os.makedirs(MARKDOWN_DIR, exist_ok=True)
#     path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     with open(path, "w", encoding="utf-8") as f:
#         f.write(text)
#     return path


# def _split_into_documents(text: str, doc_id: str, filename: str) -> List[Document]:
#     chunks = text_splitter.split_text(text)
#     return [
#         Document(
#             page_content=chunk,
#             metadata={"doc_id": doc_id, "filename": filename, "chunk_index": i},
#         )
#         for i, chunk in enumerate(chunks)
#     ]


# async def _build_vector_store(text: str, doc_id: str, filename: str) -> FAISS:
#     """Chunk the text and build a LangChain FAISS vector store (off the event loop)."""
#     documents = _split_into_documents(text, doc_id, filename)
#     if not documents:
#         raise ValueError("No chunks could be produced from this document.")

#     # FAISS.from_documents calls the (sync) embeddings API under the hood, so
#     # run it in a thread to avoid blocking the event loop.
#     vectorstore = await run_in_threadpool(FAISS.from_documents, documents, embeddings)
#     return vectorstore


# async def _persist_vector_store(vectorstore: FAISS, doc_id: str) -> None:
#     os.makedirs(PERSIST_DIR, exist_ok=True)
#     path = os.path.join(PERSIST_DIR, doc_id)
#     await run_in_threadpool(vectorstore.save_local, path)


# async def _load_vector_store_from_disk(doc_id: str) -> Optional[FAISS]:
#     path = os.path.join(PERSIST_DIR, doc_id)
#     if not os.path.isdir(path):
#         return None
#     return await run_in_threadpool(
#         FAISS.load_local, path, embeddings, allow_dangerous_deserialization=True
#     )


# async def _get_doc_entry(doc_id: str) -> Optional[Dict]:
#     """Look up a document's vector store, falling back to the on-disk index."""
#     doc = DOC_STORE.get(doc_id)
#     if doc is not None:
#         return doc

#     vectorstore = await _load_vector_store_from_disk(doc_id)
#     if vectorstore is None:
#         return None

#     markdown_path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     doc = {
#         "vectorstore": vectorstore,
#         "filename": None,
#         "num_chunks": vectorstore.index.ntotal,
#         "markdown_path": markdown_path if os.path.isfile(markdown_path) else None,
#     }
#     DOC_STORE[doc_id] = doc
#     return doc


# async def answer_stream(doc_id: str, question: str, top_k: int) -> AsyncGenerator[str, None]:
#     """
#     Stream a RAG answer the same way the QA service streams chat answers:
#     plain markdown chunks over text/plain, with [[STAGE:...]] markers for
#     slow steps and a trailing ===STREAM_META=== JSON blob carrying sources.
#     """
#     yield stage("looking up document")

#     doc = await _get_doc_entry(doc_id)
#     if doc is None:
#         # Emit an error as a normal chunk so the client renders it inline,
#         # then close out with empty metadata.
#         yield f"Sorry, I couldn't find a document with id `{doc_id}`. Please upload it first."
#         yield META_MARKER + json.dumps({"sources": []})
#         return

#     vectorstore: FAISS = doc["vectorstore"]
#     retriever = vectorstore.as_retriever(
#         search_type="similarity",
#         search_kwargs={"k": top_k},
#     )

#     yield stage("retrieving relevant chunks")
#     retrieved_docs = await retriever.ainvoke(question)
#     context = "\n\n---\n\n".join(d.page_content for d in retrieved_docs)

#     system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

#     first_chunk = True
#     async for chunk in llm.astream([
#         SystemMessage(content=system_prompt),
#         HumanMessage(content=question),
#     ]):
#         if first_chunk:
#             yield stage("starting")
#             first_chunk = False

#         if chunk.content:
#             # Send raw as-is -- the frontend markdown renderer repairs
#             # incomplete **bold, `code, [links, etc. on its own.
#             yield chunk.content

#     meta = {
#         "sources": [d.page_content for d in retrieved_docs],
#         "filenames": sorted({d.metadata.get("filename") for d in retrieved_docs if d.metadata.get("filename")}),
#     }
#     yield META_MARKER + json.dumps(meta)


# # ---------------------------------------------------------------------------
# # Schemas
# # ---------------------------------------------------------------------------

# class QueryRequest(BaseModel):
#     doc_id: str
#     question: str
#     top_k: int = TOP_K


# class UploadResponse(BaseModel):
#     doc_id: str
#     filename: str
#     num_chunks: int
#     markdown_path: str


# # ---------------------------------------------------------------------------
# # Routes
# # ---------------------------------------------------------------------------

# @router.post("/upload", response_model=UploadResponse)
# async def upload_document(file: UploadFile = File(...)):
#     """Upload a file, parse it via LlamaCloud, and build a LangChain FAISS index."""
#     return UploadResponse(
#             doc_id="1",
#             filename="file.pdf",
#             num_chunks=5,
#             markdown_path="./parsed_markdown/file.md",
#         )

#     suffix = os.path.splitext(file.filename or "")[1] or ".pdf"
#     tmp_path = None
#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
#             shutil.copyfileobj(file.file, tmp)
#             tmp_path = tmp.name

#         markdown_text = await parse_document(tmp_path)
#         if not markdown_text or not markdown_text.strip():
#             raise HTTPException(status_code=422, detail="LlamaCloud returned empty content for this file.")

#         doc_id = str(uuid.uuid4())
#         markdown_path = await run_in_threadpool(_save_markdown, markdown_text, doc_id)

#         try:
#             vectorstore = await _build_vector_store(markdown_text, doc_id, file.filename)
#         except ValueError as exc:
#             raise HTTPException(status_code=422, detail=str(exc))

#         await _persist_vector_store(vectorstore, doc_id)

#         num_chunks = vectorstore.index.ntotal
#         DOC_STORE[doc_id] = {
#             "vectorstore": vectorstore,
#             "filename": file.filename,
#             "num_chunks": num_chunks,
#             "markdown_path": markdown_path,
#         }

#         return UploadResponse(
#             doc_id=doc_id,
#             filename=file.filename,
#             num_chunks=num_chunks,
#             markdown_path=markdown_path,
#         )

#     finally:
#         if tmp_path and os.path.exists(tmp_path):
#             os.remove(tmp_path)


# # @router.post("/query")
# # async def query_document(payload: QueryRequest):
# #     """
# #     Answer a question about a previously uploaded document, streaming the
# #     response the same way /qa/ask does: text/plain chunks, [[STAGE:...]]
# #     markers while retrieving/starting, and a trailing ===STREAM_META===
# #     JSON blob with the retrieved sources.
# #     """
# #     return StreamingResponse(
# #         answer_stream(payload.doc_id, payload.question, payload.top_k),
# #         media_type="text/plain",
# #         headers={
# #             "Cache-Control": "no-cache",
# #             "X-Accel-Buffering": "no",
# #         },
# #     )


# @router.get("/documents")
# async def list_documents():
#     return [
#         {
#             "doc_id": doc_id,
#             "filename": doc["filename"],
#             "num_chunks": doc["num_chunks"],
#             "markdown_path": doc.get("markdown_path"),
#         }
#         for doc_id, doc in DOC_STORE.items()
#     ]


# @router.delete("/documents/{doc_id}")
# async def delete_document(doc_id: str):
#     existed_in_memory = DOC_STORE.pop(doc_id, None) is not None

#     path = os.path.join(PERSIST_DIR, doc_id)
#     existed_on_disk = os.path.isdir(path)
#     if existed_on_disk:
#         shutil.rmtree(path)

#     markdown_path = os.path.join(MARKDOWN_DIR, f"{doc_id}.md")
#     if os.path.isfile(markdown_path):
#         os.remove(markdown_path)

#     if not existed_in_memory and not existed_on_disk:
#         raise HTTPException(status_code=404, detail="doc_id not found.")

#     return {"status": "deleted", "doc_id": doc_id}


# @router.get("/documents/{doc_id}/markdown")
# async def get_markdown(doc_id: str):
#     """Return the raw parsed markdown that was saved for this document."""
#     doc = await _get_doc_entry(doc_id)
#     if doc is None or not doc.get("markdown_path") or not os.path.isfile(doc["markdown_path"]):
#         raise HTTPException(status_code=404, detail="Markdown not found for this doc_id.")

#     with open(doc["markdown_path"], "r", encoding="utf-8") as f:
#         content = f.read()

#     return {"doc_id": doc_id, "markdown": content}


# # @app.get("/health")
# # async def health():
# #     return {"status": "ok"}


# import asyncio
# import json
# from pathlib import Path

# from fastapi import APIRouter
# from fastapi.responses import StreamingResponse
# from langchain_experimental.agents import create_csv_agent
# from langchain_openai import ChatOpenAI

# from langchain_anthropic import ChatAnthropic
# from langchain_google_genai import ChatGoogleGenerativeAI
# # from lang


# # router = APIRouter()

# # DOC_STORE_DIR = Path("uploads")  # adjust to wherever doc_id -> csv path is resolved

# DOC_STORE_DIR="app/filedata/annual.csv"
# def resolve_csv_path(doc_id: str) -> Path:
#     path = DOC_STORE_DIR 

#     return path


# async def answer_stream_csv(doc_id: str, question: str, top_k: int | None = None):
#     """
#     Streams: [[STAGE:...]] markers, then the agent's answer in chunks,
#     then a trailing ===STREAM_META=== JSON blob with source info.
#     """
#     yield "[[STAGE:retrieving]]"

#     try:
#         csv_path = resolve_csv_path(doc_id)
#     except FileNotFoundError as e:
#         yield f"[[STAGE:error]]{e}"
#         return

#     yield "[[STAGE:starting]]"

#     llm = ChatGoogleGenerativeAI(
#             model="gemini-3.5-flash",
#             temperature=0.2,
#             google_api_key=os.getenv("GOOGLE_API_KEY"),
#             streaming=False,
#         )
#     # llm = ChatAnthropic(
#     #         model="claude-sonnet-4-6",
#     #         temperature=0.2,
#     #         api_key=os.getenv("ANTHROPIC_API_KEY"),
#     #         streaming=False,
#     #     )

#     agent = create_csv_agent(
#         llm,
#         str(csv_path),
#         verbose=True,
#         allow_dangerous_code=True,  # required: agent executes generated Python/pandas code
#         handle_parsing_errors=True,
       
#     )

#     # create_csv_agent has no native async token streaming, so run it in a
#     # worker thread and then chunk the final answer to preserve the
#     # streaming response shape.
#     loop = asyncio.get_event_loop()
#     result = await loop.run_in_executor(None, lambda: agent.invoke({"input": question}))

#     answer = result.get("output", "") if isinstance(result, dict) else str(result)

#     chunk_size = 40
#     for i in range(0, len(answer), chunk_size):
#         yield answer[i : i + chunk_size]
#         await asyncio.sleep(0)

#     meta = {
#         "sources": [str(csv_path)],
#         "doc_id": doc_id,
#         "question": question,
#     }
#     yield f"\n===STREAM_META==={json.dumps(meta)}"


# @router.post("/query")
# async def csv_query_document(payload: QueryRequest):
#     """
#     Answer a question about a previously uploaded CSV document using a
#     LangChain CSV agent, streaming the response the same way /qa/ask does:
#     text/plain chunks, [[STAGE:...]] markers while retrieving/starting, and
#     a trailing ===STREAM_META=== JSON blob with the source CSV path.
#     """
#     return StreamingResponse(
#         answer_stream_csv(payload.doc_id, payload.question, payload.top_k),
#         media_type="text/plain",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#         },
#     )