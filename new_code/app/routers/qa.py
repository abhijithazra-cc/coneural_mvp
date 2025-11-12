# app/routers/qa.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
import os

from app.database import get_db
from app.services.auth import get_current_active_user
from app.models.user_model import User as UserModel, UserType
from app.models.access_model import UserDomainAccess
from app.models.doc_models import DocChunk                   # ✅ from doc_models
from app.models.org_document_model import OrgDocument       # ✅ from org_document_model
from app.utils.embeddings import embed_texts, get_embed_dim
from app.utils.faiss_manager import FaissManager

router = APIRouter(prefix="/qa", tags=["qa"])
_faiss = FaissManager(dim=get_embed_dim())


def _can_read(db: Session, user: UserModel, org_id: int, suborg_id: int) -> bool:
    # Org admin of same org can read everywhere in org
    if user.user_type == UserType.ADMIN and user.organization_id == org_id:
        return True
    # Else must have read access on this department
    acc = db.query(UserDomainAccess).filter(
        UserDomainAccess.org_id == org_id,
        UserDomainAccess.suborg_id == suborg_id,
        UserDomainAccess.user_id == user.id
    ).first()
    return bool(acc and acc.can_read)


@router.post("/ask", summary="Ask a question over allowed departments")
def ask(
    org_id: int,
    suborg_id: int,
    q: str = Query(..., description="Your question"),
    top_k: int = 5,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    if not _can_read(db, current_user, org_id, suborg_id):
        raise HTTPException(status_code=403, detail="No read access to this department")

    # Embed the question
    [qvec] = embed_texts([q])

    # Search FAISS for top-k chunk_ids
    hits = _faiss.search(org_id, suborg_id, qvec, k=top_k)
    if not hits:
        return {"answer": "No relevant documents yet.", "snippets": []}

    # Pull matching chunks (+ join to documents for any metadata you might want)
    chunk_ids = [cid for cid, _ in hits]
    rows = db.query(DocChunk, OrgDocument)\
             .join(OrgDocument, OrgDocument.id == DocChunk.doc_id)\
             .filter(DocChunk.id.in_(chunk_ids))\
             .all()

    # Build context
    snippets = [chunk.text for (chunk, _doc) in rows]
    context = "\n\n".join(f"Snippet {i+1}:\n{s}" for i, s in enumerate(snippets))

    # Ask OpenAI for a precise, non-GPTy answer constrained to snippets
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_msg = (
        "Answer concisely using only the provided snippets. "
        "If the answer is not in the snippets, say you don't know. "
        "Avoid generic phrasing; sound like a precise human-written note."
    )
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Question: {q}\n\nContext:\n{context}"}
        ],
        temperature=0.2
    )
    answer = completion.choices[0].message.content.strip()

    return {
        "answer": answer,
        "snippets": snippets[:top_k],
    }
