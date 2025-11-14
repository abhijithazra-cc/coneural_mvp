# app/routers/qa.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.schemas.request_schema import AskRequest
from sqlalchemy.orm import Session
from sqlalchemy import select
import os

from app.database import get_db
from app.services.auth import get_current_active_user
from app.models.user_model import User as UserModel, UserType
from app.models.access_model import UserDomainAccess
from app.models.suborganization_model import Suborganization as SuborganizationModel
from app.models.doc_models import DocChunk                   # ✅ from doc_models
from app.models.org_document_model import OrgDocument       # ✅ from org_document_model
from app.utils.embeddings import embed_texts
from fastapi.responses import StreamingResponse
# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings,llm,BASE_DIR,retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
router = APIRouter(prefix="/qa", tags=["qa"])
# _faiss = FaissManager(dim=get_embed_dim())

def _access_public(a: UserDomainAccess) -> Dict:
    return {
        "id": a.id,
        "org_id": a.org_id,
        "suborg_id": a.suborg_id,
        "user_id": a.user_id,
        "can_read": getattr(a, "can_read", True),
        "can_upload": getattr(a, "can_upload", False),
        "is_author": getattr(a, "is_author", False),
        "neural_cap": getattr(a, "neural_cap", None),
    }
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
def list_user_access(
    org_id:int,
    user_id: int,
    db: Session = Depends(get_db),
    
):
    """
    Admin-only: list which departments (suborganizations) this user has access to
    within the admin's organization.
    """
    # if current_user.user_type != UserType.ADMIN:
    #     raise HTTPException(status_code=403, detail="Only org admins can view access")

    # user = _ensure_user_exists(db, user_id)
    # if user.organization_id != current_user.organization_id:
    #     raise HTTPException(status_code=403, detail="User is not in your organization")

    rows = (
        db.query(UserDomainAccess)
        .join(
            SuborganizationModel,
            SuborganizationModel.id == UserDomainAccess.suborg_id,
        )
        .filter(
            SuborganizationModel.organization_id == org_id,
            UserDomainAccess.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r)['suborg_id'] for r in rows]



# @router.post("/ask", summary="Ask a question over allowed departments")
# def ask(
#     org_id: int,
#     user_id:int,
#     q: str = Query(..., description="Your question"),
#     top_k: int = 5,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
#     stream:bool=False
# ):
@router.post("/ask", summary="Ask a question over allowed departments")
def ask(
    data:AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    
):
    # if not _can_read(db, current_user, org_id, suborg_id):
    #     raise HTTPException(status_code=403, detail="No read access to this department")
    print("current user",current_user.id)
    user_allowed_suborg_ids=list_user_access(user_id=data.user_id,org_id=data.org_id,db=db)
    print("all sub org ids",user_allowed_suborg_ids)
    if not user_allowed_suborg_ids:
           raise HTTPException(status_code=403, detail="No acces to any department")
    retrieval_list=[]
    for suborg_id in user_allowed_suborg_ids:
        vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{data.org_id}\\dept\\{suborg_id}")
       # vectorStore.set_vector_store(docs=rows,embeddings=embeddings)
        rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=data.top_k)
        retrieval_list.append(rv)
        # docs=rv.get_relevant_document(query=query)
        # docs_list.extend(docs)
        
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=rvm.invoke(input=data.q)
    if data.stream:
    # answer=llm.generate_answer(context=docs_list,query=query)
       answer=llm.generate_stream_answer(context=docs_list,query=data.q)
       def generate(ans):
        for item in ans:
            yield str(item.content)

       return StreamingResponse(generate(answer),media_type='application/json')

    else :
       answer=llm.generate_answer(context=docs_list,query=data.q)
       return {
        "answer": answer.content,
        "snippets": docs_list,
       }

    # print("stream answer",stream_answer)

    # return answer,docs_list


# @router.post("/ask", summary="Ask a question over allowed departments")
# def ask(
#     org_id: int,
#     suborg_id: int,
#     q: str = Query(..., description="Your question"),
#     top_k: int = 5,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user)
# ):
#     if not _can_read(db, current_user, org_id, suborg_id):
#         raise HTTPException(status_code=403, detail="No read access to this department")

#     # Embed the question
#     [qvec] = embed_texts([q])

#     # Search FAISS for top-k chunk_ids
#     hits = _faiss.search(org_id, suborg_id, qvec, k=top_k)
#     if not hits:
#         return {"answer": "No relevant documents yet.", "snippets": []}

#     # Pull matching chunks (+ join to documents for any metadata you might want)
#     chunk_ids = [cid for cid, _ in hits]
#     rows = db.query(DocChunk, OrgDocument)\
#              .join(OrgDocument, OrgDocument.id == DocChunk.doc_id)\
#              .filter(DocChunk.id.in_(chunk_ids))\
#              .all()

#     # Build context
#     snippets = [chunk.text for (chunk, _doc) in rows]
#     context = "\n\n".join(f"Snippet {i+1}:\n{s}" for i, s in enumerate(snippets))

#     # Ask OpenAI for a precise, non-GPTy answer constrained to snippets
#     from openai import OpenAI
#     client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
#     system_msg = (
#         "Answer concisely using only the provided snippets. "
#         "If the answer is not in the snippets, say you don't know. "
#         "Avoid generic phrasing; sound like a precise human-written note."
#     )
#     completion = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[
#             {"role": "system", "content": system_msg},
#             {"role": "user", "content": f"Question: {q}\n\nContext:\n{context}"}
#         ],
#         temperature=0.2
#     )
#     answer = completion.choices[0].message.content.strip()

#     return {
#         "answer": answer,
#         "snippets": snippets[:top_k],
#     }
