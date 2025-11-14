# routers/qa.py
import os
from typing import List, Tuple
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_session
from fastapi.responses import StreamingResponse
from models import User, Domain, OrgDocument, UserDomainAccess, DocEmbedding
from schemas import AskRequest, AskResponse
from auth_dep import get_current_user
# from utils.embeddings import generate_embedding, cosine
from Rag.utils import embeddings ,loader,splitter,retriever,llm,BASE_DIR
from Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever

# from Rag.ai import *
# -------- OpenAI setup --------
# from openai import OpenAI
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# _openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

router = APIRouter(prefix="/qa", tags=["qa"])



# Call OpenAI with wrapped hybrid prompt

# def _call_openai(question: str, snippets: List[str]) -> str:
#     ctx = "\n\n".join(f"Snippet {i+1}:\n{snip}" for i, snip in enumerate(snippets))

#     system_prompt = (
#         "You are an expert consultant.\n"
#         "Ground your answer in the provided snippets but also use your own wider knowledge "
#         "to enrich and clarify the explanation.\n"
#         "Write in clear, natural language so it does not sound like AI output.\n"
#         "Keep it concise, practical, and professional.\n"
#         "Where possible, include a short example or analogy for clarity.\n"
#         "If the snippets lack detail, combine what is available with your background knowledge "
#         "instead of refusing outright."
#     )

#     user_prompt = f"Question:\n{question}\n\nRelevant snippets:\n{ctx}\n\nAnswer:"

#     if not _openai_client:
#         return (
#             f"(Demo mode, no OpenAI key).\n\n"
#             f"Snippets considered ({len(snippets)}):\n" + "\n---\n".join(snippets[:2])
#         )

#     resp = _openai_client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_prompt},
#         ],
#         temperature=0.5,
#     )
#     return resp.choices[0].message.content.strip()


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
    stream: bool=True
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
    
    if not rows:
        raise HTTPException(status_code=403, detail="You cannot query another suborg")


    retrieval_list=[]
    for dom_id in allowed_domains:

        vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{org_id}\\dept\\{dom_id}")
       # vectorStore.set_vector_store(docs=rows,embeddings=embeddings)
        rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=10)
        retrieval_list.append(rv)
        # docs=rv.get_relevant_document(query=query)
        # docs_list.extend(docs)
        
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=rvm.invoke(input=query)
    if stream:
    # answer=llm.generate_answer(context=docs_list,query=query)
       answer=llm.generate_stream_answer(context=docs_list,query=query)
    else :
       answer=llm.generate_answer(context=docs_list,query=query)
    # print("stream answer",stream_answer)

    return answer,docs_list
    # return answer.content,docs_list


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
#             DocEmbedding.embed_id,
#             DocEmbedding.doc_id,
#             DocEmbedding.chunk_text,
#             DocEmbedding.embedding,
#             OrgDocument.domain_id,
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

#     scored: List[Tuple[float, int, str]] = []
#     for _eid, doc_id, chunk, emb, _dom in rows:
#         if not emb:
#             continue
#         sim = cosine(query_emb, emb)
#         scored.append((sim, doc_id, chunk))

#     scored.sort(key=lambda t: t[0], reverse=True)
#     top = scored[:top_k]
#     snippets = [c[:1500] for _, __, c in top]   # trimmed
#     sources = [doc_id for _, doc_id, __ in top]
#     return snippets, sources


# Main /ask endpoint
import time
@router.post("/ask-stream", response_model=AskResponse)
async def ask_stream(
    payload: AskRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # Org/suborg scope check
    s=time.monotonic()
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
    print("allowed domain ids",allowed)
    if not allowed:
        raise HTTPException(status_code=403, detail="You have no domain access. Ask an admin to grant it.")
     
    # query search

    answer ,doc_list= await _semantic_search(session, payload.org_id, payload.suborg_id, allowed, query=payload.query)

    def generate(ans):
        for item in ans:
            yield str(item.content)

    return StreamingResponse(generate(answer),media_type='application/json')
    # print("time take for query",time.monotonic()-s)
    # return {"response":answer}
    # return AskResponse(allowed_domains_used=allowed, sources=sources, answer=answer)
    # return AskResponse(allowed_domains_used=allowed, sources=doc_list, answer=answer)

import time
@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # Org/suborg scope check
    s=time.monotonic()
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
    print("allowed domain ids",allowed)
    if not allowed:
        raise HTTPException(status_code=403, detail="You have no domain access. Ask an admin to grant it.")
     
    # query search

    answer ,doc_list= await _semantic_search(session, payload.org_id, payload.suborg_id, allowed, query=payload.query)


    print("time take for query",time.monotonic()-s)

    # return AskResponse(allowed_domains_used=allowed, sources=sources, answer=answer)
    return AskResponse(allowed_domains_used=allowed, sources=doc_list, answer=answer)




# @router.post("/ask", response_model=AskResponse)
# async def ask(
#     payload: AskRequest,
#     session: AsyncSession = Depends(get_session),
#     user: User = Depends(get_current_user),
# ):
#     # Org/suborg scope check
#     if user.org_id != payload.org_id:
#         raise HTTPException(status_code=403, detail="You cannot query another organization's data")
#     if (
#         user.suborg_id is not None
#         and user.suborg_id != payload.suborg_id
#         and (user.role or "").lower() != "org_admin"
#     ):
#         raise HTTPException(status_code=403, detail="You cannot query another suborg")

#     # Domain access
#     allowed = await _allowed_domain_ids(session, user, payload.org_id, payload.suborg_id)
#     if not allowed:
#         raise HTTPException(status_code=403, detail="You have no domain access. Ask an admin to grant it.")

#     # Embedding search
#     q_emb = generate_embedding(payload.query)
#     snippets, sources = await _semantic_search(session, payload.org_id, payload.suborg_id, allowed, q_emb)

#     if not snippets:
#         return AskResponse(
#             allowed_domains_used=allowed,
#             sources=[],
#             answer="I didn’t find relevant context in your documents, but you can still ask me general questions.",
#         )

#     # Answer via hybrid LLM
#     answer = _call_openai(payload.query, snippets)
#     return AskResponse(allowed_domains_used=allowed, sources=sources, answer=answer)