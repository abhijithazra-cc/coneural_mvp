


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
    print(dept_id)
    if not dept_id or dept_id==0:
        existing_docs = db.query(OrgDocument).filter(
            OrgDocument.org_id == org_id,
            OrgDocument.dept_id == None,
            OrgDocument.scope == "global"
        ).all()
    else:
        existing_docs = db.query(OrgDocument).filter(
            OrgDocument.org_id == org_id,
            OrgDocument.dept_id == dept_id,
            OrgDocument.scope == "department"
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