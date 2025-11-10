

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import OrgDocument, Organization, SubOrganization, Domain, User, DocEmbedding
from schemas import OrgDocumentOut
from Rag.ai import embeddings,BASE_DIR
#  Import shared utils
from utils.text_extractors import extract_text
from utils.embeddings import chunk_text, generate_embedding
from Rag.FaissVectorstore import FaissVectorstore
from Rag.VectorManager import vectorManager
router = APIRouter(prefix="/org-documents", tags=["org_documents"])


#ENDPOINTS

@router.post("", response_model=OrgDocumentOut, status_code=201)
async def upload_org_document(
    org_id: int = Form(...),
    suborg_id: int = Form(...),
    domain_id: int = Form(...),
    user_id: int = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload a document:
      - validate org/suborg/domain/user
      - extract text (via utils.text_extractors)
      - chunk + embed (via utils.embeddings)
      - save to org_documents + doc_embeddings
    """
    # ---------- validate ----------
    org = await session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=400, detail="Invalid org_id")

    suborg = await session.get(SubOrganization, suborg_id)
    if not suborg or suborg.org_id != org_id:
        raise HTTPException(status_code=400, detail="Invalid suborg_id")

    domain = await session.get(Domain, domain_id)
    if not domain or domain.suborg_id != suborg_id:
        raise HTTPException(status_code=400, detail="Invalid domain_id")

    user = await session.get(User, user_id)
    if not user or user.org_id != org_id:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    # ---------- read + extract ----------
    raw = await file.read()
    text,docs = extract_text(raw, file.filename, file.content_type)

    if not text:
        text = "[[NO TEXT EXTRACTED]]"

    doc = OrgDocument(
        org_id=org_id,
        suborg_id=suborg_id,
        domain_id=domain_id,
        user_id=user_id,
        filename=file.filename,
        mimetype=file.content_type,
        size_bytes=len(raw),
        file_bytes=raw,
        content_text=text[:2_000_000],
    )
    session.add(doc)
    await session.flush()  
    print("list of vectorStore path",vectorManager.list_stores())
    vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}/dept/{domain_id}")
    print("list of vectorStore path",vectorManager.list_stores())
    # vectorStore=FaissVectorstore(embeddings=embeddings,persist_dir=f"{BASE_DIR}/{org_id}/dept/{domain_id}")
    # embeddings 
    if text and not text.startswith("[[NO TEXT EXTRACTED]]"):
        chunks = chunk_text(docs, max_chars=1500, overlap=200)
        # vectorStore.add_documents(d)
        # vectorStore.add_documents(doc)
        vectorStore.add_documents(documents=chunks,doc_id=doc.doc_id)

        for ch in chunks:
            vec = generate_embedding(ch.page_content)
            if vec:
                session.add(DocEmbedding(
                    doc_id=doc.doc_id,
                    chunk_text=ch.page_content,
                    embedding=vec,
                ))

    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("", response_model=List[OrgDocumentOut])
async def list_org_documents(
    org_id: int = Query(...),
    suborg_id: int = Query(...),
    domain_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """
    List all org documents (optionally filter by domain).
    """
    q = select(OrgDocument).where(
        OrgDocument.org_id == org_id,
        OrgDocument.suborg_id == suborg_id,
    )
    if domain_id:
        q = q.where(OrgDocument.domain_id == domain_id)

    res = await session.execute(q.order_by(OrgDocument.uploaded_at.desc()))
    return res.scalars().all()


@router.get("/{doc_id}", response_model=OrgDocumentOut)
async def get_org_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    """
    Fetch one document by ID.
    """
    doc = await session.get(OrgDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_org_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    """
    Delete a document and cascade its embeddings.
    """
    doc = await session.get(OrgDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.delete(doc)
    await session.commit()
    return {"message": "Document deleted"}
