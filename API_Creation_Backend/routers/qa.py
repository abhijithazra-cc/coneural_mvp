







# routers/qa.py
import os
from typing import List, Tuple
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from models import User, Domain, OrgDocument, UserDomainAccess, DocEmbedding
from schemas import AskRequest, AskResponse
from auth_dep import get_current_user
from utils.embeddings import generate_embedding, cosine
from Rag.ai import embeddings ,loader,splitter,vectorStore,retriever,llm
# from Rag.ai import *
# -------- OpenAI setup --------
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

router = APIRouter(prefix="/qa", tags=["qa"])



# Call OpenAI with wrapped hybrid prompt

def _call_openai(question: str, snippets: List[str]) -> str:
    ctx = "\n\n".join(f"Snippet {i+1}:\n{snip}" for i, snip in enumerate(snippets))

    system_prompt = (
        "You are an expert consultant.\n"
        "Ground your answer in the provided snippets but also use your own wider knowledge "
        "to enrich and clarify the explanation.\n"
        "Write in clear, natural language so it does not sound like AI output.\n"
        "Keep it concise, practical, and professional.\n"
        "Where possible, include a short example or analogy for clarity.\n"
        "If the snippets lack detail, combine what is available with your background knowledge "
        "instead of refusing outright."
    )

    user_prompt = f"Question:\n{question}\n\nRelevant snippets:\n{ctx}\n\nAnswer:"

    if not _openai_client:
        return (
            f"(Demo mode, no OpenAI key).\n\n"
            f"Snippets considered ({len(snippets)}):\n" + "\n---\n".join(snippets[:2])
        )

    resp = _openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
    )
    return resp.choices[0].message.content.strip()


# Get allowed domain_ids for a user

async def _allowed_domain_ids(session: AsyncSession, user: User, org_id: int, suborg_id: int) -> List[int]:
    role = (user.role or "").lower()
    if role == "org_admin":
        res = await session.execute(select(Domain.domain_id).where(Domain.org_id == org_id))
        return [r[0] for r in res.fetchall()]
    if role == "suborg_admin":
        res = await session.execute(
            select(Domain.domain_id).where(Domain.org_id == org_id, Domain.suborg_id == suborg_id)
        )
        return [r[0] for r in res.fetchall()]
    res = await session.execute(
        select(UserDomainAccess.domain_id).where(UserDomainAccess.user_id == user.user_id)
    )
    return [r[0] for r in res.fetchall()]



# Semantic search: compare embeddings

async def _semantic_search(
    session: AsyncSession,
    org_id: int,
    suborg_id: int,
    allowed_domains: List[int],
    query: str,
    top_k: int = 6,
) -> Tuple[List[str], List[int]]:
    if not allowed_domains:
        return [], []

    q = (
        select(
            DocEmbedding.chunk_text,
            DocEmbedding.embedding,

        )
        .join(OrgDocument, OrgDocument.doc_id == DocEmbedding.doc_id)
        .where(
            OrgDocument.org_id == org_id,
            OrgDocument.suborg_id == suborg_id,
            OrgDocument.domain_id.in_(allowed_domains),
        )
        .limit(3000)
    )
    rows = (await session.execute(q)).all()
    # print("rows",rows)
    if not rows:
        raise HTTPException(status_code=403, detail="You cannot query another suborg")
    # print("rows",rows,print(type(rows[0])))
    vectorStore.set_vector_store(docs=rows,embeddings=embeddings)
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=10)
    docs=retriever.get_relevant_document(query=query)
    answer=llm.generate_answer(context=docs,query=query)
    # print("answer")
    # scored: List[Tuple[float, int, str]] = []
    # for _eid, doc_id, chunk, emb, _dom in rows:
    #     if not emb:
    #         continue
    #     sim = cosine(query_emb, emb)
    #     scored.append((sim, doc_id, chunk))

    # scored.sort(key=lambda t: t[0], reverse=True)
    # top = scored[:top_k]
    # snippets = [c[:1500] for _, __, c in top]   # trimmed
    # sources = [doc_id for _, doc_id, __ in top]
    # return snippets, sources

    return answer.content


# async def _semantic_search(
#     session: AsyncSession,
#     org_id: int,
#     suborg_id: int,
#     allowed_domains: List[int],
#     query_emb: List[float],
#     top_k: int = 6,
# ) -> Tuple[List[str], List[int]]:
#     if not allowed_domains:
#         return [], []

#     q = (
#         select(

#             DocEmbedding.chunk_text,
#             DocEmbedding.embedding,

#         )
#         .join(OrgDocument, OrgDocument.doc_id == DocEmbedding.doc_id)
#         .where(
#             OrgDocument.org_id == org_id,
#             OrgDocument.suborg_id == suborg_id,
#             OrgDocument.domain_id.in_(allowed_domains),
#         )
#         .limit(3000)
#     )
#     rows = (await session.execute(q)).all()
#     print("rows",rows,print(type(rows[0])))
#     # scored: List[Tuple[float, int, str]] = []
#     # for _eid, doc_id, chunk, emb, _dom in rows:
#     #     if not emb:
#     #         continue
#     #     sim = cosine(query_emb, emb)
#     #     scored.append((sim, doc_id, chunk))

#     # scored.sort(key=lambda t: t[0], reverse=True)
#     # top = scored[:top_k]
#     # snippets = [c[:1500] for _, __, c in top]   # trimmed
#     # sources = [doc_id for _, doc_id, __ in top]
#     # return snippets, sources
#     snippets=""
#     sources=""
#     return snippets, sources


# Main /ask endpoint

@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # Org/suborg scope check
    if user.org_id != payload.org_id:
        raise HTTPException(status_code=403, detail="You cannot query another organization's data")
    if (
        user.suborg_id is not None
        and user.suborg_id != payload.suborg_id
        and (user.role or "").lower() != "org_admin"
    ):
        raise HTTPException(status_code=403, detail="You cannot query another suborg")

    # Domain access
    allowed = await _allowed_domain_ids(session, user, payload.org_id, payload.suborg_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="You have no domain access. Ask an admin to grant it.")
     
    # Embedding search
    # q_emb = generate_embedding(payload.query)
    answer = await _semantic_search(session, payload.org_id, payload.suborg_id, allowed, query=payload.query)
    # snippets, sources = await _semantic_search(session, payload.org_id, payload.suborg_id, allowed, query=payload.query)

    # if not snippets:
    #     return AskResponse(
    #         allowed_domains_used=allowed,
    #         sources=[],
    #         answer="I didn’t find relevant context in your documents, but you can still ask me general questions.",
    #     )

    # Answer via hybrid LLM
    # answer = _call_openai(payload.query, snippets)
    # return AskResponse(allowed_domains_used=allowed, sources=sources, answer=answer)
    return AskResponse(allowed_domains_used=allowed, sources=[], answer=answer)
