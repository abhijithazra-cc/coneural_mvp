# app/routers/documents.py

import io
from typing import Optional
from app.Rag.VectorManager import vectorManager
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
from app.models.user_model import User as UserModel, UserType
from app.models.doc_models import OrgDocument, DocChunk
from app.models.suborganization_model import Suborganization
from app.models.access_model import UserDomainAccess
from app.services.auth import get_current_active_user
from app.utils.chunking import extract_text_from_file, chunk_text
from app.utils.embeddings import embed_texts
from app.utils.faiss_manager import add_vectors
from app.utils.text_extractors import extract_text
from app.Rag.ai import embeddings,BASE_DIR
from app.Rag.VectorManager import vectorManager
router = APIRouter(prefix="/org-documents", tags=["org_documents"])

# 5 MB limit as requested
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Org Document (PDF/DOCX/TXT) → chunk → store → index",
)
async def upload_org_document(
    org_id: int = Form(...),
    suborg_id: int = Form(...),
    user_id: Optional[int] = Form(
        None, description="Uploader user id (optional, default = current user)"
    ),
    title: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: UserModel = Depends(get_current_active_user),
):
    """
    Upload a document to a specific department (suborganization) and index it.

    Rules:
    - `suborg_id` must belong to the given `org_id`.
    - Caller must be:
        * ORG ADMIN (UserType.ADMIN), or
        * The same `user_id` and have upload / author permission in `user_domain_access`.
    - We:
        * store doc metadata in `org_documents`
        * store text chunks in `doc_chunks`
        * create FAISS HNSW index for (org_id, suborg_id) via `add_vectors(...)`
    """

    # 1) Suborg must belong to org
    sub = (
        db.query(Suborganization)
        .filter(
            Suborganization.id == suborg_id,
            Suborganization.organization_id == org_id,
        )
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=404,
            detail="Suborganization not found in this organization",
        )

    # 2) Decide effective uploader id
    effective_user_id = user_id or current.id

    # 3) Authorization
    is_admin = current.user_type == UserType.ADMIN

    if not is_admin:
        # Non-admin can only upload on their own behalf
        if effective_user_id != current.id:
            raise HTTPException(
                status_code=403,
                detail="You can only upload on your own behalf",
            )

        # Check access row
        access = (
            db.query(UserDomainAccess)
            .filter(
                UserDomainAccess.org_id == org_id,
                UserDomainAccess.suborg_id == suborg_id,
                UserDomainAccess.user_id == current.id,
            )
            .first()
        )
        if not access or not (access.can_upload or access.is_author):
            raise HTTPException(
                status_code=403,
                detail="No upload permission for this department",
            )

    # 4) Read & size-check payload
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large (5MB limit)",
        )

    # 5) Extract text
    try:
        # text = extract_text_from_file(
        #     io.BytesIO(payload),
        #     filename=file.filename,
        #     mime_type=file.content_type or "",
        # )
        text,docs = extract_text(
            payload,
            filename=file.filename,
            mimetype=file.content_type or "",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {e}")

    # 6) Chunk text
    chunks = chunk_text(docs=docs, max_tokens=600, overlap=120)
    print("chunks",chunks)
    if not chunks:
        raise HTTPException(status_code=400, detail="No text content in file")

    # 7) Create document row
    doc = OrgDocument(
        org_id=org_id,
        suborg_id=suborg_id,
        owner_id=effective_user_id,
        title=title or file.filename,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(payload),
    )
    db.add(doc)
    db.flush()  # doc.id becomes available
    # await session.flush()  

    vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\{org_id}\dept\{suborg_id}")
    vectorStore.add_documents(documents=chunks,doc_id=doc.id)
    # 8) Persist chunks in SQL
    db.add_all(
        [
            DocChunk(
                doc_id=doc.id,
                org_id=org_id,
                suborg_id=suborg_id,
                chunk_index=i,
                content=chunk,
            )
            for i, chunk in enumerate(chunks)
        ]
    )
    db.commit()
    db.refresh(doc)

    # 9) Embed & index (FAISS HNSW)
    # vectors = embed_texts(chunks)  # shape (N, D), float32

    # if not isinstance(vectors, np.ndarray):
    #     vectors = np.asarray(vectors, dtype="float32")
    # if vectors.dtype != np.float32:
    #     vectors = vectors.astype("float32", copy=False)

    # # unique ids per chunk for this doc
    # ids = np.array(
    #     [doc.id * 1_000_000 + i for i in range(len(chunks))], dtype="int64"
    # )
    # add_vectors(org_id=org_id, suborg_id=suborg_id, vectors=vectors, ids=ids)

    return {
        "doc": {
            "id": doc.id,
            "title": doc.title,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "chunks": len(chunks),
        },
        "department": {"org_id": org_id, "suborg_id": suborg_id},
    }




# # app/routers/documents.py
# import io
# import numpy as np
# from typing import Optional

# from fastapi import (
#     APIRouter, UploadFile, File, Form, Depends, HTTPException, status
# )
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.models.user_model import User as UserModel, UserType
# from app.models.doc_models import OrgDocument, DocChunk
# from app.models.suborganization_model import Suborganization
# from app.models.access_model import UserDomainAccess
# from app.services.auth import get_current_active_user  # <-- correct import
# from app.utils.chunking import extract_text_from_file, chunk_text
# from app.utils.embeddings import embed_texts
# from app.utils.faiss_manager import add_vectors

# router = APIRouter(prefix="/org-documents", tags=["org_documents"])

# MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


# @router.post(
#     "/",
#     status_code=status.HTTP_201_CREATED,
#     summary="Upload Org Document (PDF/DOCX/TXT) and chunk → store → index"
# )
# async def upload_org_document(
#     org_id: int = Form(...),
#     suborg_id: int = Form(...),
#     user_id: Optional[int] = Form(None, description="Uploader user id (optional if admin)"),
#     title: str = Form(""),
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
#     current: UserModel = Depends(get_current_active_user),
# ):
#     """
#     Rules:
#     - Suborg must belong to given org.
#     - Uploader must be either:
#         * ORG ADMIN (current.user_type == ADMIN), or
#         * The same `user_id` **and** has upload/author permission in `user_domain_access`.
#     - Stores metadata in `org_documents`, text chunks in `doc_chunks`,
#       and vectors into FAISS via `add_vectors(...)`.
#     """

#     # --- Validate suborg belongs to org
#     sub = (
#         db.query(Suborganization)
#         .filter(Suborganization.id == suborg_id, Suborganization.organization_id == org_id)
#         .first()
#     )
#     if not sub:
#         raise HTTPException(status_code=404, detail="Suborganization not found in this organization")

#     # --- Decide effective uploader id
#     effective_user_id = user_id or current.id

#     # --- Authorization
#     is_admin = current.user_type == UserType.ADMIN
#     if not is_admin:
#         if effective_user_id != current.id:
#             raise HTTPException(status_code=403, detail="You can only upload on your own behalf")
#         access = (
#             db.query(UserDomainAccess)
#             .filter(
#                 UserDomainAccess.org_id == org_id,
#                 UserDomainAccess.suborg_id == suborg_id,
#                 UserDomainAccess.user_id == current.id,
#             )
#             .first()
#         )
#         if not access or not (access.can_upload or access.is_author):
#             raise HTTPException(status_code=403, detail="No upload permission for this department")

#     # --- Read & size-check
#     payload = await file.read()
#     if not payload:
#         raise HTTPException(status_code=400, detail="Empty file")
#     if len(payload) > MAX_FILE_BYTES:
#         raise HTTPException(status_code=413, detail="File too large (20MB limit)")

#     # --- Extract text
#     try:
#         text = extract_text_from_file(io.BytesIO(payload), file.filename, file.content_type)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"Cannot read file: {e}")

#     # --- Chunk text
#     chunks = chunk_text(text, max_tokens=600, overlap=120)
#     if not chunks:
#         raise HTTPException(status_code=400, detail="No text content in file")

#     # --- Create document row
#     doc = OrgDocument(
#         org_id=org_id,
#         suborg_id=suborg_id,
#         owner_user_id=effective_user_id,
#         title=title or file.filename,
#         filename=file.filename,
#         mime_type=file.content_type or "application/octet-stream",
#         size_bytes=len(payload),
#     )
#     db.add(doc)
#     db.flush()  # need doc.id

#     # --- Persist chunks
#     db.add_all(
#         [
#             DocChunk(
#                 doc_id=doc.id,
#                 org_id=org_id,
#                 suborg_id=suborg_id,
#                 chunk_index=i,
#                 content=chunk,
#             )
#             for i, chunk in enumerate(chunks)
#         ]
#     )
#     db.commit()
#     db.refresh(doc)

#     # --- Embed & index (FAISS HNSW)
#     vectors = embed_texts(chunks)  # shape (N, D) float32
#     if not isinstance(vectors, np.ndarray):
#         vectors = np.asarray(vectors, dtype="float32")
#     if vectors.dtype != np.float32:
#         vectors = vectors.astype("float32", copy=False)

#     ids = np.array([doc.id * 1_000_000 + i for i in range(len(chunks))], dtype="int64")
#     add_vectors(org_id=org_id, suborg_id=suborg_id, vectors=vectors, ids=ids)

#     return {
#         "doc": {
#             "id": doc.id,
#             "title": doc.title,
#             "filename": doc.filename,
#             "mime_type": doc.mime_type,
#             "chunks": len(chunks),
#         },
#         "department": {"org_id": org_id, "suborg_id": suborg_id},
#     }
