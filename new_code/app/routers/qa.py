# app/routers/qa.py
"""
QA / RAG chat routes.

Reusable, generic building blocks (schemas, the LangGraph chat graph,
reranking, masking helpers, JSON repair, NDJSON streaming utilities,
document/auth helpers, PDF caching helpers, etc.) live in
`app.services.qa_service`.

The actual `/ask` route behavior — retrieval, provider selection, streaming
the LLM response, saving chat history/citations — stays here since it's the
core logic of these endpoints.
"""

from langsmith import traceable

import base64
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from app.database import get_db
from app.Rag.Masking import Masking, PiiMaskingState
from app.Rag.StepTimer import StepTimer, logger
from app.Rag.utils import (
    BASE_DIR,
    embeddings,
    extract_text_only_from_html,
    llm_anthropic,
    llm_gemini,
    llm_openai,
    retriever,
)
from app.Rag.VectorManager import vectorManager
from app.models.chat_messages_model import ChatMessage
from app.models.chat_thread_model import ChatThreads
from app.models.user_model import User as UserModel
from app.schemas.request_schema import AskRequest, AskRequestOnDocument
from app.services import qa_service
from app.services.auth import get_current_active_user
from app.utils.celery_app import celery_app, filter_sources_by_citation
from app.repository.ChatThreadRepository import ChatThreadRepository
from app.repository.ChatMessageRepository import ChatMessageRepository


router = APIRouter(prefix="/qa", tags=["qa"])


# ─────────────────────────────────────────────────────────────
# Threads
# ─────────────────────────────────────────────────────────────


@router.get("/list_user_threads")
@traceable(name="list_user_threads", project="core", metadata={"description": "List user's threads created"},tags=["threads"])
def list_user_threads(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    next_id: Optional[int] = 0,
    limit: int = Query(20, le=100),
    name: Optional[str] = Query(None),
):
    chat_thread_obj = ChatThreadRepository(db)
    res = chat_thread_obj.list_user_threads(user_id=current_user.id,org_id=current_user.org_id, next_id=next_id, limit=limit, name=name)

    response = [
        {
            "thread_id": msg.id,
            "title": msg.description or "",
            "date": msg.updated_at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for msg in res.items
    ]
    return {"messages": response, "next_id": res.next_cursor, "has_more": res.has_more}


# @router.get("/list_user_threads")
# @traceable(name="list_user_threads", project="core", metadata={"description": "List user's threads created"},tags=["threads"])
# def list_user_threads(
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
#     next_id: Optional[int] = 0,
#     limit: int = Query(20, le=100),
#     name: Optional[str] = Query(None),
# ):
#     query = db.query(
#         ChatThreads.id, ChatThreads.description, ChatThreads.updated_at
#     ).filter(
#         ChatThreads.org_id == current_user.org_id,
#         ChatThreads.user_id == current_user.id,
#     )
#     if name and name.strip():
#         query = query.filter(ChatThreads.description.ilike(f"%{name.strip()}%"))
#     if next_id:
#         query = query.filter(ChatThreads.id < next_id)

#     messages = query.order_by(ChatThreads.updated_at.desc()).limit(limit + 1).all()

#     has_more = len(messages) > limit
#     messages = messages[:limit]
#     new_next_id = messages[-1].id if messages else None

#     response = [
#         {
#             "thread_id": msg.id,
#             "title": msg.description or "",
#             "date": msg.updated_at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S"),
#         }
#         for msg in messages
#     ]
#     return {"messages": response, "next_id": new_next_id, "has_more": has_more}


@router.delete("/delete_thread/{thread_id}", summary="Delete thread by id")
@traceable(name="delete_thread", project="core", metadata={"description": "Delete thread by id"}, tags=["threads"])
def delete_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    chat_thread_obj = ChatThreadRepository(db)
    chat_thread_obj.delete(id=thread_id)
    return {"message": "Thread deleted successfully"}
# @router.delete("/delete_thread/{thread_id}", summary="Delete thread by id")
# @traceable(name="delete_thread", project="core", metadata={"description": "Delete thread by id"}, tags=["threads"])
# def delete_thread(
#     thread_id: int,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     thread = (
#         db.query(ChatThreads)
#         .filter(
#             ChatThreads.id == thread_id,
#             ChatThreads.org_id == current_user.org_id,
#             ChatThreads.user_id == current_user.id,
#         )
#         .first()
#     )
#     if not thread:
#         raise HTTPException(status_code=404, detail="Thread not found")
#     db.delete(thread)
#     db.commit()
#     return {"message": "Thread deleted successfully"}


@router.get("/title/{thread_id}", summary="Get thread title")
@traceable(name="get_thread_title", project="core", metadata={"description": "Get thread title by id"}, tags=["threads"])
def get_description(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread=ChatThreadRepository(db).get_by_id(id=thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"title": thread.description or ""}
# @router.get("/title/{thread_id}", summary="Get thread title")
# @traceable(name="get_thread_title", project="core", metadata={"description": "Get thread title by id"}, tags=["threads"])
# def get_description(
#     thread_id: int,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     thread = (
#         db.query(ChatThreads)
#         .filter(
#             ChatThreads.id == thread_id,
#             ChatThreads.org_id == current_user.org_id,
#             ChatThreads.user_id == current_user.id,
#         )
#         .first()
#     )
#     if not thread:
#         raise HTTPException(status_code=404, detail="Thread not found")
#     return {"title": thread.description or ""}


@router.put("/rename_title/{thread_id}", summary="Update thread title")
@traceable(name="update_thread_title", project="core", metadata={"description": "Update thread title by id"}, tags=["threads"])
def update_description(
    thread_id: int,
    description: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread=ChatThreadRepository(db).update_chat_thread_description(thread_id=thread_id, description=description)
    if not thread:
        return HTTPException(status_code=404, detail="Thread not found")
    return {"message": "title updated successfully"}
# @router.put("/rename_title/{thread_id}", summary="Update thread title")
# @traceable(name="update_thread_title", project="core", metadata={"description": "Update thread title by id"}, tags=["threads"])
# def update_description(
#     thread_id: int,
#     description: str,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     thread = (
#         db.query(ChatThreads)
#         .filter(
#             ChatThreads.id == thread_id,
#             ChatThreads.org_id == current_user.org_id,
#             ChatThreads.user_id == current_user.id,
#         )
#         .first()
#     )
#     if not thread:
#         raise HTTPException(status_code=404, detail="Thread not found")
#     thread.description = description
#     db.add(thread)
#     db.commit()
#     return {"message": "title updated successfully"}



@router.get("/thread_id", summary="Requesting new Thread ID")
@traceable(name="ask_thread", project="core", metadata={"description": "Requesting new Thread ID"}, tags=["threads","users"])
def ask_thread(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    
    thread=ChatThreadRepository(db).create_thread(org_id=current_user.org_id, user_id=current_user.id)
    return {"thread_id": thread.id, "title": thread.description or ""}

# @router.get("/thread_id", summary="Requesting new Thread ID")
# @traceable(name="ask_thread", project="core", metadata={"description": "Requesting new Thread ID"}, tags=["threads","users"])
# def ask_thread(
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     next_provider = qa_service.get_next_llm_provider(db, current_user)
#     user_thread = ChatThreads(
#         user_id=current_user.id,
#         org_id=current_user.org_id,
#         description="",
#         llm_provider=next_provider,
#     )
#     db.add(user_thread)
#     db.commit()
#     db.flush()
#     return {"thread_id": user_thread.id, "title": user_thread.description or ""}


@router.get("/chat_history/{thread_id}", summary="Get chat history by thread id")
@traceable(name="get_chat_history", project="core", metadata={"description": "Get chat history by thread id"}, tags=["threads"])
def get_chat_history(
    thread_id: int,
    limit: int = Query(20, le=100),
    next_id: Optional[int] = 0,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)
    chat_repo_obj = ChatMessageRepository(db)
    res=chat_repo_obj.load_chat_history(thread_id=thread_id, limit=limit, next_id=next_id)
    print(res)
    response = [
        {
            "id": msg.id,
            "query": msg.query,
            "response": msg.response,
            "html_response": msg.html_response,
            "links": msg.citation,
        }
        for msg in res.items
    ]

    return {
        "message": response,
        "next_id": res.next_cursor,
        "has_more": res.has_more,
        "document_ids": document_ids.get("doc_ids", []) if isinstance(document_ids, dict) else document_ids,
    }
# @router.get("/chat_history/{thread_id}", summary="Get chat history by thread id")
# @traceable(name="get_chat_history", project="core", metadata={"description": "Get chat history by thread id"}, tags=["threads"])
# def get_chat_history(
#     thread_id: int,
#     limit: int = Query(20, le=100),
#     next_id: Optional[int] = 0,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     query = db.query(ChatMessage).filter(ChatMessage.thread_id == thread_id)
#     document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)

#     if next_id:
#         query = query.filter(ChatMessage.id < next_id)

#     messages = query.order_by(ChatMessage.id.desc()).limit(limit + 1).all()

#     has_more = len(messages) > limit
#     messages = messages[:limit]
#     new_next_id = messages[-1].id if messages else None

#     response = [
#         {
#             "id": msg.id,
#             "query": msg.query,
#             "response": msg.response,
#             "html_response": msg.html_response,
#             "links": msg.citation,
#         }
#         for msg in messages
#     ]

#     return {
#         "message": response,
#         "next_id": new_next_id,
#         "has_more": has_more,
#         "document_ids": document_ids.get("doc_ids", []) if isinstance(document_ids, dict) else document_ids,
#     }


# ─────────────────────────────────────────────────────────────
# Citation PDFs
# ─────────────────────────────────────────────────────────────

@router.get("/pdf/{id}", summary="Get citated link by id")
@traceable(name="get_citation_pdf", project="core", metadata={"description": "Get citated link by id"}, tags=["threads"])
def cited(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    id: str = "",
):
    cached = qa_service.find_cached_citation_pdf(id)
    if cached:
        pdf_path, pages_str = cached
        return Response(
            content=pdf_path.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline", "page": pages_str},
        )

    job = qa_service.wait_for_celery_pdf_job(id)
    result = job.result
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {id} completed but returned no result.",
        )

    doc_id = result.get("document_id")
    if not doc_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Task {id} result is missing document_id.",
        )

    qa_service.check_user_access_to_document(db=db, current_user=current_user, document_id=doc_id)

    pdf_bytes = base64.b64decode(result["pdf"])
    pages = result.get("pages", [])
    pages_str = "_".join(str(n) for n in pages)

    qa_service.cache_citation_pdf_to_disk(id, pages_str, pdf_bytes)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline", "page": pages_str},
    )


@router.get("/pdf-download/{id}", summary="Get citated link by id")
def download(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    id: str = "",
):
    job = AsyncResult(id, app=celery_app)
    if job.status == "SUCCESS" and job.result:
        doc_id = job.result["document_id"]
        qa_service.check_user_access_to_document(db=db, current_user=current_user, document_id=doc_id)

        pdf_bytes = base64.b64decode(job.result["pdf"])
        original_filename = job.result["filename"]
        filename_without_ext = Path(original_filename).stem

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_without_ext}"},
        )

    raise HTTPException(status_code=404, detail="PDF not ready or not found")


# ─────────────────────────────────────────────────────────────
# /ask/{thread_id} — RAG over all allowed departments/documents
# ─────────────────────────────────────────────────────────────

from fastapi import BackgroundTasks

@router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
def ask(
    thread_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
): 
    # query = data.q.strip()
    @traceable(name="user_query", project="core", metadata={"description": "Ask a question over allowed departments","response_type": "streaming","thread_id": thread_id,"user_id": current_user.id,"org_id": current_user.org_id}, tags=["threads","users"])
    def event_generator(query=data.q.strip()):
        timer = StepTimer(name=f"ask:{thread_id}")
        yield qa_service.json_line({"type": "stage", "value": "thinking"})
        print("organization id", current_user.org_id)
        try:
            qa_service.is_org_exist(db, org_id=current_user.org_id)
            timer.mark("org check")

            docs = qa_service.get_list_allowed_documents(db, current_user)
            timer.mark("allowed documents")

            allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
            timer.mark("thread validation")
            if not allowed:
                yield qa_service.json_line({
                    "type": "error",
                    "message": "Not valid thread for current user",
                })
                yield qa_service.json_line({"type": "done"})
                return

            # vector_store = vectorManager.get_store(
            #     embeddings=embeddings,
            #     persist_dir=f"{BASE_DIR}/{current_user.org_id}",
            # )
            vector_store = vectorManager.get_store(org_id=str(current_user.org_id))
            # print("vector store type", vector_store.vectorstore_type)
            timer.mark("vector store init")
            # print(docs)
            yield qa_service.json_line({"type": "stage", "value": "fetching relevant documents"})
            rv = retriever.get_retreiver_by_document_id(
                vector_store=vector_store.get_vector_store(),
                search_type="similarity",
                top_n=data.top_k,
                document_id=docs,
            )
            # store=vector_store.get_vector_store()
            # print("doc id",type(docs))
            # rs=store.search_chunks(query=data.q, document_id=docs)
            # print(rs)
            @traceable(name="fetch_docs", project="core", metadata={"description": "Fetch relevant documents for query"}, tags=["documents","users","threads"])
            def fetch_docs():
                return rv.invoke(input=data.q)
            docs_list = fetch_docs()
            # print("doc_list", docs_list)
            
            timer.mark("document retrieval")

            docs_list = qa_service.rerank_docs(query=data.q, docs=docs_list, top_n=5)
            timer.mark("reranking")

            masking_state = PiiMaskingState()
            timer.mark("masking state init")
            masking = Masking()
            timer.mark("masking init")
            yield qa_service.json_line({"type": "stage", "value": "masking sensitive information"})
            query, masked_docs = masking.mask_query_and_docs(data.q, docs_list, masking_state)
            timer.mark("masking")

            # ── Provider + memory config ───────────────────────────
            provider = qa_service.get_thread_provider(db, current_user, thread_id)
            timer.mark("get provider")

            memory_thread_id = f"{current_user.org_id}:{thread_id}"
            config = {"configurable": {"thread_id": str(memory_thread_id)}}

            # ── Load prior chat history for context ────────────────
            @traceable(name="load_chat_history", project="core", metadata={"description": "Load prior chat history for context"}, tags=["threads","users"])
            def load_chat_history():
                with qa_service.get_checkpointer() as checkpointer:
                    chatbot = qa_service.builder(checkpointer=checkpointer)
                    current_state = chatbot.get_state(config)
                    chat_history = []
                    if current_state and current_state.values.get("messages"):
                       chat_history = current_state.values["messages"]
                return chat_history
            chat_history=load_chat_history()
            timer.mark("load chat history")

            # ── Pick LLM based on provider ─────────────────────────
            llm_instance = {
                "openai": llm_openai,
                "gemini": llm_gemini,
                "anthropic": llm_anthropic,
            }.get(provider, llm_openai)
            print("provider",provider)
            # ── Create DB row FIRST so we can send message_id early ─
            chat_message = ChatMessage(
                query=data.q,
                response="",
                thread_id=thread_id,
                tokens=0,
                citation=[],
                html_response=[],
                unanswer_query=True,
            )
            db.add(chat_message)
            db.commit()
            db.flush()
            timer.mark("create chat message row")

            yield qa_service.json_line({"type": "message_id", "id": str(chat_message.id)})

            # ── Accumulators ───────────────────────────────────────
            collected_blocks = []   # only open-with-content blocks, for DB + memory
            my_link = []
            suggested = []
            title = None
            is_citation_required = False
            first_token_marked = False

            # ── Stream events straight from LLM ────────────────────
            for event in llm_instance.stream_blocks(
                context=masked_docs,
                query=query,
                original_query=data.q,
                chat_history=chat_history,
            ):
                etype = event.get("type")

                if not first_token_marked:
                    timer.mark("first stream token")
                    first_token_marked = True

                if etype == "block":
                    tag = str(event.get("tag", ""))
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        continue

                    if "content" in event:
                        event["content"] = masking.unmask_text(
                            event["content"], state=masking_state
                        )
                        collected_blocks.append(
                            {"tag": tag, "content": event["content"]}
                        )
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    is_citation_required = event.get("required", False)
                    if is_citation_required:
                        raw_links = event.get("links", []) or []
                        my_link = qa_service.normalize_citation_links(raw_links)

                elif etype == "suggested":
                    suggested = [
                        masking.unmask_text(q, state=masking_state)
                        for q in event.get("questions", [])
                    ]
                    yield qa_service.json_line({"type": "suggested", "questions": suggested})

                elif etype == "title":
                    title = event.get("content", None)

                elif etype == "stage":
                    yield qa_service.json_line(event)

                elif etype == "done":
                    break

            timer.mark("full LLM stream complete")



            # ── Build citations from retrieved docs' metadata ──────
            serialize_doc_list = qa_service.documents_to_dicts(docs_list)

            if is_citation_required:
                citation_filenames = []
                for d in serialize_doc_list:
                    meta = d.get("metadata") or {}
                    fname = (
                        meta.get("filename")
                        or meta.get("source")
                        or meta.get("file")
                        or meta.get("document_name")
                    )
                    if fname:
                        citation_filenames.append(fname)

                citation_filenames = list(dict.fromkeys(citation_filenames))

                my_link = filter_sources_by_citation(
                    citations=citation_filenames,
                    org_id=current_user.org_id,
                    sources=serialize_doc_list,
                )
            timer.mark("build citations")

            yield qa_service.json_line({"type": "citations", "links": my_link})
            yield qa_service.json_line({"type": "done"})
                # ── Save Q&A to LangGraph memory ───────────────────────
            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)
                chatbot.update_state(
                    config,
                    {"messages": [
                        HumanMessage(content=data.q),
                        AIMessage(content=json.dumps(collected_blocks)),
                    ]},
                )
            timer.mark("save langgraph memory")
            llm_response = extract_text_only_from_html(collected_blocks)

            qa_service.update_chat_thread_description(
                db, current_user.org_id, current_user.id, thread_id, description=title
            )

            # ── Update the DB row created earlier ──────────────────
            chat_message.response = llm_response
            chat_message.citation = my_link
            chat_message.html_response = collected_blocks
            chat_message.unanswer_query = False if collected_blocks else True
            db.commit()
            db.flush()

            db.query(ChatThreads).filter(
                ChatThreads.id == thread_id,
                ChatThreads.org_id == current_user.org_id,
                ChatThreads.user_id == current_user.id
            ).update({
                "updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))
            })
            db.commit()
            timer.mark("db update + commit")

            logger.info(timer.summary())

        except Exception:
            logger.exception("ask streaming error")
            yield qa_service.json_line({
                "type": "error",
                "message": "Something went wrong while generating the answer.",
            })
            yield qa_service.json_line({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────
# /ask/{thread_id}/edit/{message_id} — edit latest message, rerun RAG
# ─────────────────────────────────────────────────────────────

@router.put("/ask/{thread_id}/edit/{message_id}", summary="Edit the latest chat message and rerun RAG")
def edit_message(
    thread_id: int,
    message_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    @traceable(name="edit_message", project="core", metadata={"description": "Edit the latest chat message and rerun RAG","response_type": "streaming","thread_id": thread_id,"message_id": message_id,"user_id": current_user.id,"org_id": current_user.org_id,"message_id": message_id}, tags=["threads","users"])
    def event_generator(query=data.q.strip()):
        yield qa_service.json_line({"type": "stage", "value": "thinking"})

        try:
            s = time.monotonic()
            qa_service.is_org_exist(db, org_id=current_user.org_id)

            # --- Validate thread ownership ---
            allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
            if not allowed:
                yield qa_service.json_line({"type": "error", "message": "Not valid thread for current user"})
                yield qa_service.json_line({"type": "done"})
                return

            # --- Fetch the existing chat message row ---
            chat_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.id == message_id, ChatMessage.thread_id == thread_id)
                .first()
            )
            if not chat_message:
                yield qa_service.json_line({"type": "error", "message": "Chat message not found"})
                yield qa_service.json_line({"type": "done"})
                return

            # --- Ensure it's the latest message in the thread ---
            latest_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.thread_id == thread_id)
                .order_by(ChatMessage.id.desc())
                .first()
            )
            if not latest_message or latest_message.id != message_id:
                yield qa_service.json_line({
                    "type": "error",
                    "message": "Only the latest message in a thread can be edited",
                })
                yield qa_service.json_line({"type": "done"})
                return

            memory_thread_id = f"{current_user.org_id}:{thread_id}"
            config = {"configurable": {"thread_id": str(memory_thread_id)}}
            provider = qa_service.get_thread_provider(db, current_user, thread_id)

            # --- STEP 1: Remove stale latest human+AI messages from checkpoint ---
            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)

                current_state = chatbot.get_state(config)
                chat_history = []
                if current_state and current_state.values.get("messages"):
                    messages = current_state.values["messages"]
                    messages_to_remove = messages[-2:] if len(messages) >= 2 else messages[-1:]

                    print("=== MESSAGES TO BE REMOVED FROM CHECKPOINT ===")
                    for m in messages_to_remove:
                        print(f"Type: {type(m).__name__} | ID: {m.id} | Content: {m.content}")
                    print("=== END ===")

                    chatbot.update_state(
                        config,
                        {"messages": [RemoveMessage(id=m.id) for m in messages_to_remove]}
                    )
                    print(f"Removed {len(messages_to_remove)} stale messages from checkpoint")

                # Re-fetch history AFTER removal so the LLM sees the pruned context
                pruned_state = chatbot.get_state(config)
                if pruned_state and pruned_state.values.get("messages"):
                    chat_history = pruned_state.values["messages"]

            # --- STEP 2: Determine department access ---
            admin = qa_service.is_org_admin(db, current_user, current_user.org_id)
            if admin:
                user_allowed_dept_ids = qa_service.list_of_departments(db, current_user)
            else:
                user_allowed_dept_ids = qa_service.list_user_access(
                    user_id=current_user.id, org_id=current_user.org_id, db=db
                )

            # --- STEP 3: Check if this thread is a single-document chat ---
            document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)
            if isinstance(document_ids, dict):
                document_ids = document_ids.get("doc_ids", [])
            else:
                document_ids = document_ids or []
            print("document ids selected for thread", document_ids)

            vector_store = vectorManager.get_store(
                embeddings=embeddings,
                persist_dir=f"{BASE_DIR}/{current_user.org_id}"
            )

            # --- STEP 4: Retrieval — document-scoped if thread has pinned docs ---
            if document_ids:
                rv = retriever.get_retreiver_by_document_id(
                    vector_store=vector_store.get_vector_store(),
                    search_type="similarity",
                    top_n=data.top_k,
                    document_id=document_ids,
                )
                docs_list = rv.invoke(input=data.q)
            elif admin:
                rv = retriever.get_retreiver(
                    vector_store=vector_store.get_vector_store(),
                    search_type="similarity",
                    top_n=data.top_k,
                )
                rvm = EnsembleRetriever(retrievers=[rv])
                docs_list = rvm.invoke(input=data.q)
            else:
                user_allowed_dept_ids.append("global")
                rv = retriever.get_retreiver_by_department_ids(
                    vector_store=vector_store.get_vector_store(),
                    search_type="similarity",
                    top_n=data.top_k,
                    dept_ids=user_allowed_dept_ids,
                )
                rvm = EnsembleRetriever(retrievers=[rv])
                docs_list = rvm.invoke(input=data.q)

            print(f"Vector retriever returned {len(docs_list)} chunks")

            # --- STEP 5: Rerank ---
            docs_list = qa_service.rerank_docs(query=data.q, docs=docs_list, top_n=5)
            print(f"Reranked to top {len(docs_list)} chunks via FlashRank")

            # --- STEP 6: PII Masking ---
            masking_state = PiiMaskingState()
            masking = Masking()
            query, masked_docs = masking.mask_query_and_docs(data.q, docs_list, masking_state)

            # --- STEP 7: Pick LLM based on provider ---
            llm_instance = {
                "openai": llm_openai,
                "gemini": llm_gemini,
                "anthropic": llm_anthropic,
            }.get(provider, llm_openai)

            # Send message_id (reusing the edited row's id) right away
            yield qa_service.json_line({"type": "message_id", "id": str(chat_message.id)})

            # --- Accumulators ---
            collected_blocks = []
            my_link = []
            suggested = []

            # --- STEP 8: Stream events straight from LLM ---
            for event in llm_instance.stream_blocks(
                context=masked_docs,
                query=query,
                original_query=data.q,
                chat_history=chat_history,
            ):
                etype = event.get("type")

                if etype == "block":
                    tag = str(event.get("tag", ""))

                    # closing tag: forward as-is
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        continue

                    # opening tag with content: unmask then forward
                    if "content" in event:
                        event["content"] = masking.unmask_text(
                            event["content"], state=masking_state
                        )
                        collected_blocks.append(
                            {"tag": tag, "content": event["content"]}
                        )
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    raw_links = event.get("links", []) or []
                    my_link = qa_service.normalize_citation_links(raw_links)

                elif etype == "suggested":
                    suggested = [
                        masking.unmask_text(q, state=masking_state)
                        for q in event.get("questions", [])
                    ]

                elif etype == "done":
                    break

            e = time.monotonic()

            # --- Save fresh Q&A into the same thread's checkpoint ---
            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)
                chatbot.update_state(
                    config,
                    {"messages": [
                        HumanMessage(content=data.q),
                        AIMessage(content=json.dumps(collected_blocks)),
                    ]},
                )
            print(f"Checkpoint updated with new edited messages under thread: {memory_thread_id}")

            # --- Filter citations against actually-retrieved docs ---
            serialize_doc_list = qa_service.documents_to_dicts(docs_list)
            citation_filenames = [c.get("filename", "") for c in my_link]
            my_link = filter_sources_by_citation(
                citations=citation_filenames,
                org_id=current_user.org_id,
                sources=serialize_doc_list,
            )

            llm_response = extract_text_only_from_html(collected_blocks)

            # --- Overwrite the existing ChatMessage row in DB ---
            chat_message.query = data.q
            chat_message.response = llm_response
            chat_message.tokens = 0  # token count unavailable in stream mode
            chat_message.citation = my_link
            chat_message.html_response = collected_blocks
            chat_message.unanswer_query = False if collected_blocks else True

            db.commit()
            db.refresh(chat_message)

            print("total edit time", time.monotonic() - s)

            # --- Trailing metadata in exact format ---
            yield qa_service.json_line({"type": "citations", "links": my_link})
            yield qa_service.json_line({"type": "suggested", "questions": suggested})
            yield qa_service.json_line({"type": "done"})

        except Exception as e:
            print("edit_message streaming error:", repr(e))
            yield qa_service.json_line({
                "type": "error",
                "message": "Something went wrong while generating the answer.",
            })
            yield qa_service.json_line({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────
# /ask/{thread_id}/documents — RAG scoped to particular document ids
# ─────────────────────────────────────────────────────────────

@router.post(
    "/ask/{thread_id}/documents",
    summary="Ask a question over allowed departments over particular document",
)
def ask_by_id(
    thread_id: int,
    data: AskRequestOnDocument,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    @traceable(name="ask_over_selected_documents", project="core", metadata={"description": "Ask a question over allowed departments over particular document","response_type": "streaming","thread_id": thread_id,"user_id": current_user.id,"org_id": current_user.org_id}, tags=["threads","users"])
    def event_generator(query=data.q.strip()):
        yield qa_service.json_line({"type": "stage", "value": "thinking"})

        try:
            s = time.monotonic()
            print("organization id", current_user.org_id)
            print(data.document_id, thread_id)

            doc_suborg = qa_service.get_suborg_by_document_id(db, data.document_id)
            print(doc_suborg)

            if not doc_suborg:
                yield qa_service.json_line({
                    "type": "error",
                    "message": "No department found for given document",
                })
                yield qa_service.json_line({"type": "done"})
                return

            allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
            print("allowed thread", allowed)
            if not allowed:
                yield qa_service.json_line({
                    "type": "error",
                    "message": "Not valid thread for current user",
                })
                yield qa_service.json_line({"type": "done"})
                return

            document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)
            print("document ids selected for thread", document_ids)

            vector_store = vectorManager.get_store(
                embeddings=embeddings,
                persist_dir=f"{BASE_DIR}/{current_user.org_id}",
            )
            print("document id", data.document_id)
            rv = retriever.get_retreiver_by_document_id(
                vector_store=vector_store.get_vector_store(),
                search_type="similarity",
                top_n=data.top_k,
                document_id=data.document_id,
            )

            docs_list = rv.invoke(input=data.q)
            print("retrieved docs_list", docs_list)
            docs_list = qa_service.rerank_docs(query=data.q, docs=docs_list, top_n=5)

            print(f"Reranked to top {len(docs_list)} chunks via FlashRank")
            print("context extracton time", time.monotonic() - s)

            ss = time.monotonic()
            masking_state = PiiMaskingState()
            masking = Masking()

            query, masked_docs = masking.mask_query_and_docs(
                data.q,
                docs_list,
                masking_state
            )

            print("masking time", time.monotonic() - ss)

            # ── Provider + memory config ───────────────────────────
            provider = qa_service.get_thread_provider(db, current_user, thread_id)
            print("provider", provider)

            memory_thread_id = f"{current_user.org_id}:{thread_id}"
            config = {"configurable": {"thread_id": str(memory_thread_id)}}

            # ── Load prior chat history for context ────────────────
            @traceable(name="load_chat_history", project="core", metadata={"description": "Load prior chat history for context"}, tags=["threads","users"])
            def load_chat_history():
                with qa_service.get_checkpointer() as checkpointer:
                    chatbot = qa_service.builder(checkpointer=checkpointer)
                    current_state = chatbot.get_state(config)
                    chat_history = []
                    if current_state and current_state.values.get("messages"):
                       chat_history = current_state.values["messages"]
                return chat_history
            chat_history=load_chat_history()
            # ── Pick LLM based on provider ─────────────────────────
            llm_instance = {
                "openai": llm_openai,
                "gemini": llm_gemini,
                "anthropic": llm_anthropic,
            }.get(provider, llm_openai)

            # ── Create DB row FIRST so we can send message_id early ─
            chat_message = ChatMessage(
                query=data.q,
                response="",
                thread_id=thread_id,
                tokens=0,
                citation=[],
                html_response=[],
                unanswer_query=True,
            )
            db.add(chat_message)
            db.commit()
            db.flush()

            yield qa_service.json_line({"type": "message_id", "id": str(chat_message.id)})

            # ── Accumulators ───────────────────────────────────────
            collected_blocks = []   # only open-with-content blocks, for DB + memory
            my_link = []
            suggested = []
            llm_emitted_citations = False   # LLM signals doc-sourced answer

            # ── Stream events straight from LLM ────────────────────
            for event in llm_instance.stream_blocks(
                context=masked_docs,
                query=query,
                original_query=data.q,
                chat_history=chat_history,
            ):
                etype = event.get("type")

                if etype == "block":
                    tag = str(event.get("tag", ""))

                    # closing tag: forward as-is
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        continue

                    # opening tag with content: unmask then forward
                    if "content" in event:
                        event["content"] = masking.unmask_text(
                            event["content"], state=masking_state
                        )
                        collected_blocks.append(
                            {"tag": tag, "content": event["content"]}
                        )
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    # LLM decided the answer came from documents
                    if event.get("links"):
                        llm_emitted_citations = True

                elif etype == "suggested":
                    suggested = [
                        masking.unmask_text(q, state=masking_state)
                        for q in event.get("questions", [])
                    ]

                elif etype == "done":
                    break


            # ── Build citations only if the answer came from documents ──
            if llm_emitted_citations:
                serialize_doc_list = qa_service.documents_to_dicts(docs_list)
                citation_filenames = []
                for d in serialize_doc_list:
                    meta = d.get("metadata") or {}
                    fname = meta.get("filename") or meta.get("source", "")
                    if fname:
                        citation_filenames.append(fname)
                citation_filenames = list(dict.fromkeys(citation_filenames))
                print("citation filenames from docs_list:", citation_filenames)

                my_link = filter_sources_by_citation(
                    citations=citation_filenames,
                    org_id=current_user.org_id,
                    sources=serialize_doc_list,
                )
            else:
                # web / general knowledge / not-in-docs → no citations
                my_link = []
                print("no citations — answer not from documents")

            llm_response = extract_text_only_from_html(collected_blocks)
            yield qa_service.json_line({"type": "citations", "links": my_link})
            yield qa_service.json_line({"type": "suggested", "questions": suggested})
            yield qa_service.json_line({"type": "done"})
            # first block content is a reasonable title fallback
            title = collected_blocks[0]["content"] if collected_blocks else data.q
            qa_service.update_chat_thread_description(
                db, current_user.org_id, current_user.id, thread_id, description=title
            )
            
            # ── Save Q&A to LangGraph memory ───────────────────────
            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)
                chatbot.update_state(
                    config,
                    {"messages": [
                        HumanMessage(content=data.q),
                        AIMessage(content=json.dumps(collected_blocks)),
                    ]},
                )

            # ── Update the DB row created earlier ──────────────────
            chat_message.response = llm_response
            chat_message.citation = my_link
            chat_message.html_response = collected_blocks
            chat_message.unanswer_query = False if collected_blocks else True
            db.commit()
            db.flush()

            db.query(ChatThreads).filter(
                ChatThreads.id == thread_id,
                ChatThreads.org_id == current_user.org_id,
                ChatThreads.user_id == current_user.id
            ).update({
                "updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))
            })
            db.commit()

            if not document_ids:
                db.query(ChatThreads).filter(
                    ChatThreads.id == thread_id,
                    ChatThreads.org_id == current_user.org_id,
                    ChatThreads.user_id == current_user.id
                ).update({
                    "document_ids": {"doc_ids": list(set(data.document_id))}
                })
                db.commit()

            # ── Trailing metadata in exact format ──────────────────


            print("total time", time.monotonic() - s)

        except Exception as e:
            print("ask_by_id streaming error:", repr(e))
            yield qa_service.json_line({
                "type": "error",
                "message": "Something went wrong while generating the answer.",
            })
            yield qa_service.json_line({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )