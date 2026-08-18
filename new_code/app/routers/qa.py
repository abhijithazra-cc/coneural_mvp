# app/routers/qa.py
"""
QA / RAG chat routes.

Reusable, generic building blocks (schemas, reranking, masking helpers,
JSON repair, NDJSON streaming utilities, document/auth helpers, PDF caching
helpers, etc.) live in `app.services.qa_service`.

`/ask/{thread_id}` is driven by a LangGraph `StateGraph`:

    validate -> analyse_query -> (retrieve_document | web_search)
             -> mask_content -> prepare_llm -> augment_with_search -> llm_call

A single `qa_app.stream(..., stream_mode=["updates", "messages"])` call
drives the whole thing: "updates" events map to the stage/message_id lines
the frontend already expects, "messages" events are raw LLM tokens (filtered
to the llm_call node) that get buffered and parsed as NDJSON exactly like
the old `stream_blocks` generator used to do — just moved to where the graph
is consumed instead of living inside the provider class.

`edit_message` and `ask_by_id` are left as they were for now — they share a
lot of this same shape (retrieval -> mask -> stream -> persist) and would
benefit from the same treatment, but that's a separate pass.
"""

from langsmith import traceable

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TypedDict
from zoneinfo import ZoneInfo

import base64
from celery.result import AsyncResult
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from langgraph.graph import END, START, StateGraph
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage

from app.database import get_db, SessionLocal  # TODO: confirm SessionLocal is exported here
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
   # TODO: fix this import if it doesn't actually live in app.Rag.utils
)
from app.Rag.VectorManager import vectorManager
from app.models.chat_messages_model import ChatMessage
from app.models.chat_thread_model import ChatThreads
from app.models.user_model import User as UserModel
from app.routers.search import GeminiSearchNode
from app.schemas.request_schema import AskRequest, AskRequestOnDocument
from app.services import qa_service
from app.services.auth import get_current_active_user
from app.utils.celery_app import celery_app, filter_sources_by_citation
from app.repository.ChatThreadRepository import ChatThreadRepository
from app.repository.ChatMessageRepository import ChatMessageRepository

from app.Rag.prompts import BLOCK_STREAM_PROMPT 
router = APIRouter(prefix="/qa", tags=["qa"])


def _context_to_text(context) -> str:
    """
    Stand-in for whatever `_context_to_text` your stream_blocks used
    internally. Replace with the real one (or import it) if it does more —
    e.g. interleaving filename/page metadata per chunk into the text.
    """
    if isinstance(context, str):
        return context
    parts = []
    for item in context or []:
        if hasattr(item, "page_content"):
            parts.append(item.page_content)
        elif isinstance(item, dict):
            parts.append(item.get("page_content") or item.get("content") or str(item))
        else:
            parts.append(str(item))
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Threads
# ─────────────────────────────────────────────────────────────


@router.get("/list_user_threads")
@traceable(name="list_user_threads", project="core", metadata={"description": "List user's threads created"}, tags=["threads"])
def list_user_threads(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    next_id: Optional[int] = 0,
    limit: int = Query(20, le=100),
    name: Optional[str] = Query(None),
):
    chat_thread_obj = ChatThreadRepository(db)
    res = chat_thread_obj.list_user_threads(user_id=current_user.id, org_id=current_user.org_id, next_id=next_id, limit=limit, name=name)

    response = [
        {
            "thread_id": msg.id,
            "title": msg.description or "",
            "date": msg.updated_at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for msg in res.items
    ]
    return {"messages": response, "next_id": res.next_cursor, "has_more": res.has_more}


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


@router.get("/title/{thread_id}", summary="Get thread title")
@traceable(name="get_thread_title", project="core", metadata={"description": "Get thread title by id"}, tags=["threads"])
def get_description(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = ChatThreadRepository(db).get_by_id(id=thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"title": thread.description or ""}


@router.put("/rename_title/{thread_id}", summary="Update thread title")
@traceable(name="update_thread_title", project="core", metadata={"description": "Update thread title by id"}, tags=["threads"])
def update_description(
    thread_id: int,
    description: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = ChatThreadRepository(db).update_chat_thread_description(thread_id=thread_id, description=description)
    if not thread:
        return HTTPException(status_code=404, detail="Thread not found")
    return {"message": "title updated successfully"}


@router.get("/thread_id", summary="Requesting new Thread ID")
@traceable(name="ask_thread", project="core", metadata={"description": "Requesting new Thread ID"}, tags=["threads", "users"])
def ask_thread(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = ChatThreadRepository(db).create_thread(org_id=current_user.org_id, user_id=current_user.id)
    return {"thread_id": thread.id, "title": thread.description or ""}


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
    res = chat_repo_obj.load_chat_history(thread_id=thread_id, limit=limit, next_id=next_id)
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
# LangGraph-driven /ask
# ─────────────────────────────────────────────────────────────

# ── 0. Checkpointer/chatbot: created once, reused across requests ──────
# Lazily initialized on first use rather than opened fresh per request.
# Better home for this is a FastAPI lifespan hook in main.py (so it's ready
# before the first request and torn down cleanly on shutdown) — this
# module-level lazy singleton is the pragmatic version that doesn't require
# touching main.py.
_checkpointer_cm = None
_checkpointer = None
_chatbot = None


def _get_chatbot():
    global _checkpointer_cm, _checkpointer, _chatbot
    if _chatbot is None:
        _checkpointer_cm = qa_service.get_checkpointer()
        _checkpointer = _checkpointer_cm.__enter__()
        _chatbot = qa_service.builder(checkpointer=_checkpointer)
    return _chatbot


# ── 1. State — kept small and JSON-friendly. db/current_user/chatbot are
# runtime dependencies passed via config["configurable"], not state. ────
class QAState(TypedDict, total=False):
    thread_id: int
    query: str
    top_k: int

    retrieval_required: bool
    route: str

    docs: list
    docs_list: list
    source_type: str

    masking: object
    masking_state: object
    masked_query: str
    masked_docs: list

    provider: str
    llm_instance: object
    chat_history: list
    chat_message_id: int

    search_results: str
    error: Optional[str]

from langchain_core.runnables import RunnableConfig

# ── 2. Nodes ─────────────────────────────────────────────────────────
def validate(state: QAState, config: RunnableConfig) -> dict:
    ctx = config["configurable"]
    db = ctx["db"]
    current_user = ctx["current_user"]

    qa_service.is_org_exist(db, org_id=current_user.org_id)

    allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=state["thread_id"])
    if not allowed:
        return {"error": "Not valid thread for current user"}

    docs = qa_service.get_list_allowed_documents(db, current_user)
    return {"docs": docs}


def route_after_validate(state: QAState) -> str:
    return "stop" if state.get("error") else "continue"


def analyse_query(state: QAState) -> dict:
    """
    Cheap classifier: does this need the org's internal documents, or is it
    a general query that just needs live web search? Uses llm_openai (via
    its underlying .llm_stream) regardless of the thread's configured
    provider — swap for a smaller/faster model if you have one, since this
    sits directly on the critical path before any retrieval happens.
    """
    classification_prompt = (
     "You decide whether a user question should be answered using the "
     "organization's internal knowledge base or a live web search.\n\n"
     "Default to 'internal' — most questions are about company documents, "
     "policies, product info, or historical/static knowledge, and should "
     "stay internal.\n\n"
     "Only choose 'web' if the question clearly requires real-time or "
     "recently-changing information that a static knowledge base cannot "
     "have, such as:\n"
     "- current news or events\n"
     "- weather\n"
     "- stock prices / market data\n"
     "- sports scores or live results\n"
     "- 'today', 'latest', 'current', 'right now', or similar time-sensitive phrasing\n"
     "- facts about the outside world that change frequently\n\n"
     "If the question is ambiguous, or could plausibly be answered from "
     "internal documents, choose 'internal'.\n\n"
     "Reply with exactly one word: 'internal' or 'web'. No punctuation, "
     "no explanation.\n\n"
    f"Question: {state['query']}"
    )
    response = llm_openai.llm_stream.invoke(classification_prompt)
    raw = getattr(response, "content", "") or ""
    if isinstance(raw, list):
        text = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
    else:
        text = raw
    retrieval_required = text.strip().lower().startswith("internal")

    return {"retrieval_required": retrieval_required}


def route_after_analyse(state: QAState) -> str:
    return "retrieve_document" if state["retrieval_required"] else "web_search"


def retrieve_document(state: QAState, config: RunnableConfig) -> dict:
    current_user = config["configurable"]["current_user"]
    vector_store = vectorManager.get_store(org_id=str(current_user.org_id))

    rv = retriever.get_retreiver_by_document_id(
        vector_store=vector_store.get_vector_store(),
        search_type="similarity",
        top_n=state["top_k"],
        document_id=state["docs"],
    )

    @traceable(
        name="fetch_docs",
        project="core",
        metadata={"description": "Fetch relevant documents for query"},
        tags=["documents", "users", "threads"],
    )
    def fetch_docs():
        return rv.invoke(input=state["query"])

    docs_list = fetch_docs()
    docs_list = qa_service.rerank_docs(query=state["query"], docs=docs_list, top_n=5)

    return {"docs_list": docs_list, "source_type": "internal", "route": "retrieve_document"}

from langchain_core.documents import Document
search_web=GeminiSearchNode()
import inspect
import asyncio
def web_search(state: QAState) -> dict:
    """
    TODO: wire up a real web search provider here. Keep the return shape
    close to what retrieve_document produces (something with `.metadata` /
    a "metadata" dict key) so masking + citation building downstream stay
    branch-agnostic.
    """
    raw_results =  search_web.search(query=state["query"], num_results=5)  # implement this
    if inspect.isawaitable(raw_results):
        raw_results = asyncio.run(raw_results)
    # print("raw_results", raw_results)
    docs = []

    # Add the Gemini synthesized answer as a document.
    if raw_results.get("answer"):
        docs.append(
            Document(
                page_content=raw_results["answer"],
                metadata={
                    "source": "web_search",
                    "title": "Web Search Answer",
                },
            )
        )
    return {"docs_list": docs, "source_type": "web", "route": "web_search"}


def mask_content(state: QAState) -> dict:
    masking_state = PiiMaskingState()
    masking = Masking()
    query, masked_docs = masking.mask_query_and_docs(state["query"], state["docs_list"], masking_state)
    return {
        "masking": masking,
        "masking_state": masking_state,
        "masked_query": query,
        "masked_docs": masked_docs,
    }


def prepare_llm(state: QAState, config: RunnableConfig) -> dict:
    ctx = config["configurable"]
    db = ctx["db"]
    current_user = ctx["current_user"]
    chatbot = ctx["chatbot"]
    thread_id = state["thread_id"]

    provider = qa_service.get_thread_provider(db, current_user, thread_id)
    llm_instance = {
        "openai": llm_openai,
        "gemini": llm_gemini,
        "anthropic": llm_anthropic,
    }.get(provider, llm_openai)

    memory_thread_id = f"{current_user.org_id}:{thread_id}"
    memory_config = {"configurable": {"thread_id": str(memory_thread_id)}}

    @traceable(
        name="load_chat_history",
        project="core",
        metadata={"description": "Load prior chat history for context"},
        tags=["threads", "users"],
    )
    def load_chat_history():
        current_state = chatbot.get_state(memory_config)
        chat_history = []
        if current_state and current_state.values.get("messages"):
            chat_history = current_state.values["messages"]
        return chat_history

    chat_history = load_chat_history()

    chat_message = ChatMessage(
        query=state["query"],
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

    return {
        "provider": provider,
        "llm_instance": llm_instance,
        "chat_history": chat_history,
        "chat_message_id": chat_message.id,
    }


def augment_with_search(state: QAState) -> dict:
    """
    Same live-internet-search step your old stream_blocks ran on every
    turn, keyed off the ORIGINAL (unmasked) query — regardless of which
    branch supplied the doc context. Gate with
    `if state["source_type"] == "web": ...` if you only want this on the
    general-query path.
    """
    llm_instance = state["llm_instance"]
    original_query = state["query"]
    search_results = ""
    search_node = getattr(llm_instance, "search_node", None)
    if original_query and search_node:
        search_results = search_node.search(original_query)
    return {"search_results": search_results}


def llm_call(state: QAState) -> dict:
    """
    Builds the final prompt and calls the model. Deliberately `.invoke()`,
    not `.stream()` — LangGraph's `stream_mode="messages"` captures the
    underlying token stream via callbacks either way, same as your sample
    (which also just does `llm.invoke(prompt)` inside the node). All the
    NDJSON line-buffering/parsing that used to happen inside stream_blocks
    now happens where `qa_app.stream()` is consumed, in `ask()` below —
    this node's job is just "produce the response", not "parse it".
    """
    llm_instance = state["llm_instance"]
    context_text = _context_to_text(state["masked_docs"])
 
    human_prompt = f"""<context>
{context_text}
</context>
 
<question>
{state["masked_query"]}
</question>
 
<internet_search_results>
{state.get("search_results", "")}
</internet_search_results>
"""
 
    messages = [SystemMessage(content=BLOCK_STREAM_PROMPT)]
    if state.get("chat_history"):
        messages.extend(state["chat_history"])
    messages.append(HumanMessage(content=human_prompt))
 
    llm_instance.llm_stream.invoke(messages)   # tokens captured via stream_mode="messages"
    return {}



# ── 3. Graph ─────────────────────────────────────────────────────────
# qa_graph = StateGraph(QAState)

# qa_graph.add_node("validate", validate)
# qa_graph.add_node("analyse_query", analyse_query)
# qa_graph.add_node("retrieve_document", retrieve_document)
# qa_graph.add_node("web_search", web_search)
# qa_graph.add_node("mask_content", mask_content)
# qa_graph.add_node("prepare_llm", prepare_llm)
# qa_graph.add_node("augment_with_search", augment_with_search)
# qa_graph.add_node("llm_call", llm_call)

# qa_graph.add_edge(START, "validate")
# qa_graph.add_conditional_edges("validate", route_after_validate, {"continue": "analyse_query", "stop": END})
# qa_graph.add_conditional_edges(
#     "analyse_query",
#     route_after_analyse,
#     {"retrieve_document": "retrieve_document", "web_search": "web_search"},
# )
# qa_graph.add_edge("retrieve_document", "mask_content")
# qa_graph.add_edge("web_search", "mask_content")
# qa_graph.add_edge("mask_content", "prepare_llm")
# qa_graph.add_edge("prepare_llm", "augment_with_search")
# qa_graph.add_edge("augment_with_search", "llm_call")
# qa_graph.add_edge("llm_call", END)

# qa_app = qa_graph.compile()


qa_graph = StateGraph(QAState)
qa_graph.add_node("validate", validate)
qa_graph.add_node("analyse_query", analyse_query)
qa_graph.add_node("retrieve_document", retrieve_document)
qa_graph.add_node("web_search", web_search)
qa_graph.add_node("mask_content", mask_content)
qa_graph.add_node("prepare_llm", prepare_llm)
qa_graph.add_node("augment_with_search", augment_with_search)
qa_graph.add_node("llm_call", llm_call)

qa_graph.add_edge(START, "validate")
qa_graph.add_conditional_edges("validate", route_after_validate, {"continue": "retrieve_document", "stop": END})
# qa_graph.add_conditional_edges(
#     "analyse_query",
#     route_after_analyse,
#     {"retrieve_document": "retrieve_document", "web_search": "web_search"},
# )
qa_graph.add_edge("retrieve_document", "mask_content")
# qa_graph.add_edge("web_search", "mask_content")
qa_graph.add_edge("mask_content", "prepare_llm")
qa_graph.add_edge("prepare_llm", "augment_with_search")
qa_graph.add_edge("augment_with_search", "llm_call")
qa_graph.add_edge("llm_call", END)

qa_app = qa_graph.compile()

STAGE_MESSAGES = {
    "analyse_query": "thinking",
    "retrieve_document": "fetching relevant documents",
    "web_search": "searching the web",
    "mask_content": "masking sensitive information",
    "augment_with_search": "finalizing the answer",
}


def persist_qa_result(
    *,
    org_id: int,
    user_id: int,
    thread_id: int,
    chat_message_id: int,
    query: str,
    collected_blocks: list,
    my_link: list,
    title: Optional[str],
    memory_thread_id: str,
):
    """
    Runs AFTER the streaming response has been fully sent — commits here
    never add latency to the stream. Opens its own db session since
    FastAPI's `Depends(get_db)` session may already be torn down by the
    time a background task actually runs.
    """
    db = SessionLocal()
    try:
        chatbot = _get_chatbot()
        memory_config = {"configurable": {"thread_id": memory_thread_id}}
        chatbot.update_state(
            memory_config,
            {
                "messages": [
                    HumanMessage(content=query),
                    AIMessage(content=json.dumps(collected_blocks)),
                ]
            },
        )

        llm_response = extract_text_only_from_html(collected_blocks)
        qa_service.update_chat_thread_description(db, org_id, user_id, thread_id, description=title)

        chat_message = db.query(ChatMessage).get(chat_message_id)
        chat_message.response = llm_response
        chat_message.citation = my_link
        chat_message.html_response = collected_blocks
        chat_message.unanswer_query = False if collected_blocks else True
        db.commit()

        db.query(ChatThreads).filter(
            ChatThreads.id == thread_id,
            ChatThreads.org_id == org_id,
            ChatThreads.user_id == user_id,
        ).update({"updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))})
        db.commit()
    except Exception:
        logger.exception("ask persistence (background) failed for chat_message_id=%s", chat_message_id)
        db.rollback()
    finally:
        db.close()


@router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
def ask(
    thread_id: int,
    data: AskRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    @traceable(
        name="user_query",
        project="core",
        metadata={
            "description": "Ask a question over allowed departments",
            "response_type": "streaming",
            "thread_id": thread_id,
            "user_id": current_user.id,
            "org_id": current_user.org_id,
        },
        tags=["threads", "users"],
    )
    def event_generator():
        timer = StepTimer(name=f"ask:{thread_id}")
        yield qa_service.json_line({"type": "stage", "value": "thinking"})

        try:
            initial_state: QAState = {
                "thread_id": thread_id,
                "query": data.q.strip(),
                "top_k": data.top_k,
            }
            run_config = {
                "configurable": {
                    "db": db,
                    "current_user": current_user,
                    "chatbot": _get_chatbot(),
                }
            }

            final_state: QAState = dict(initial_state)  # type: ignore

            collected_blocks = []
            my_link = []
            suggested = []
            title = None
            is_citation_required = False
            first_token_marked = False
            token_buffer = ""
            stop_streaming = False

            def handle_ndjson_event(event: dict):
                nonlocal is_citation_required, my_link, title, stop_streaming

                etype = event.get("type")

                if etype == "block":
                    tag = str(event.get("tag", ""))
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        return
                    if "content" in event:
                        event["content"] = final_state["masking"].unmask_text(
                            event["content"], state=final_state["masking_state"]
                        )
                        collected_blocks.append({"tag": tag, "content": event["content"]})
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    is_citation_required = event.get("required", False)
                    if is_citation_required:
                        raw_links = event.get("links", []) or []
                        my_link = qa_service.normalize_citation_links(raw_links)

                elif etype == "suggested":
                    questions = [
                        final_state["masking"].unmask_text(q, state=final_state["masking_state"])
                        for q in event.get("questions", [])
                    ]
                    suggested[:] = questions
                    yield qa_service.json_line({"type": "suggested", "questions": questions})

                elif etype == "title":
                    title = event.get("content", None)

                elif etype == "stage":
                    yield qa_service.json_line(event)

                elif etype == "done":
                    stop_streaming = True

            for stream_type, payload in qa_app.stream(
                initial_state, config=run_config, stream_mode=["updates", "messages"]
            ):
                if stream_type == "updates":
                    node_name, node_output = next(iter(payload.items()))

                    if node_output is None:
                       node_output = {}

                    final_state = {
                     **final_state,
                     **node_output,
                   }

                    timer.mark(node_name)

                    if node_name == "validate" and final_state.get("error"):
                        yield qa_service.json_line({"type": "error", "message": final_state["error"]})
                        yield qa_service.json_line({"type": "done"})
                        return

                    if node_name in STAGE_MESSAGES:
                        yield qa_service.json_line({"type": "stage", "value": STAGE_MESSAGES[node_name]})

                    if node_name == "prepare_llm":
                        yield qa_service.json_line({"type": "message_id", "id": str(final_state["chat_message_id"])})
                        yield qa_service.json_line({"type": "stage", "value": "extracting information from internet"})
                    continue

                chunk, metadata = payload
                if metadata.get("langgraph_node") != "llm_call":
                    continue

                if not first_token_marked:
                    timer.mark("first stream token")
                    first_token_marked = True

                raw_content = getattr(chunk, "content", "") or ""
                if isinstance(raw_content, list):
                    text_piece = "".join(part.get("text", "") for part in raw_content if isinstance(part, dict))
                else:
                    text_piece = raw_content

                if not text_piece:
                    continue

                token_buffer += text_piece
                while "\n" in token_buffer:
                    line, token_buffer = token_buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        token_buffer = line + "\n" + token_buffer
                        break
                    yield from handle_ndjson_event(event)
                    if stop_streaming:
                        break

                if stop_streaming:
                    break

            remaining = token_buffer.strip()
            if remaining and not stop_streaming:
                try:
                    yield from handle_ndjson_event(json.loads(remaining))
                except json.JSONDecodeError:
                    pass

            timer.mark("full LLM stream complete")

            # ── Citations ────────────────────────────────────────
            serialize_doc_list = qa_service.documents_to_dicts(final_state["docs_list"])
            if is_citation_required:
                citation_filenames = []
                for d in serialize_doc_list:
                    meta = d.get("metadata") or {}
                    fname = meta.get("filename") or meta.get("source") or meta.get("file") or meta.get("document_name")
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
            timer.mark("stream complete, handing off to background persistence")
            logger.info(timer.summary())

            # ── Persist (background — doesn't block the client) ────
            background_tasks.add_task(
                persist_qa_result,
                org_id=current_user.org_id,
                user_id=current_user.id,
                thread_id=thread_id,
                chat_message_id=final_state["chat_message_id"],
                query=data.q,
                collected_blocks=collected_blocks,
                my_link=my_link,
                title=title,
                memory_thread_id=f"{current_user.org_id}:{thread_id}",
            )

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
        background=background_tasks,
    )


# ─────────────────────────────────────────────────────────────
# /ask/{thread_id}/edit/{message_id} — edit latest message, rerun RAG
# Left unchanged — same "retrieve -> mask -> stream -> persist" shape as
# the old /ask, and would benefit from the same graph treatment, but that's
# a separate pass from this one.
# ─────────────────────────────────────────────────────────────

@router.put("/ask/{thread_id}/edit/{message_id}", summary="Edit the latest chat message and rerun RAG")
def edit_message(
    thread_id: int,
    message_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    @traceable(name="edit_message", project="core", metadata={"description": "Edit the latest chat message and rerun RAG", "response_type": "streaming", "thread_id": thread_id, "message_id": message_id, "user_id": current_user.id, "org_id": current_user.org_id}, tags=["threads", "users"])
    def event_generator(query=data.q.strip()):
        yield qa_service.json_line({"type": "stage", "value": "thinking"})

        try:
            s = time.monotonic()
            qa_service.is_org_exist(db, org_id=current_user.org_id)

            allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
            if not allowed:
                yield qa_service.json_line({"type": "error", "message": "Not valid thread for current user"})
                yield qa_service.json_line({"type": "done"})
                return

            chat_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.id == message_id, ChatMessage.thread_id == thread_id)
                .first()
            )
            if not chat_message:
                yield qa_service.json_line({"type": "error", "message": "Chat message not found"})
                yield qa_service.json_line({"type": "done"})
                return

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

            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)

                current_state = chatbot.get_state(config)
                chat_history = []
                if current_state and current_state.values.get("messages"):
                    messages = current_state.values["messages"]
                    messages_to_remove = messages[-2:] if len(messages) >= 2 else messages[-1:]

                    chatbot.update_state(
                        config,
                        {"messages": [RemoveMessage(id=m.id) for m in messages_to_remove]}
                    )

                pruned_state = chatbot.get_state(config)
                if pruned_state and pruned_state.values.get("messages"):
                    chat_history = pruned_state.values["messages"]

            admin = qa_service.is_org_admin(db, current_user, current_user.org_id)
            if admin:
                user_allowed_dept_ids = qa_service.list_of_departments(db, current_user)
            else:
                user_allowed_dept_ids = qa_service.list_user_access(
                    user_id=current_user.id, org_id=current_user.org_id, db=db
                )

            document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)
            if isinstance(document_ids, dict):
                document_ids = document_ids.get("doc_ids", [])
            else:
                document_ids = document_ids or []

            vector_store = vectorManager.get_store(
                embeddings=embeddings,
                persist_dir=f"{BASE_DIR}/{current_user.org_id}"
            )

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

            docs_list = qa_service.rerank_docs(query=data.q, docs=docs_list, top_n=5)

            masking_state = PiiMaskingState()
            masking = Masking()
            query, masked_docs = masking.mask_query_and_docs(data.q, docs_list, masking_state)

            llm_instance = {
                "openai": llm_openai,
                "gemini": llm_gemini,
                "anthropic": llm_anthropic,
            }.get(provider, llm_openai)

            yield qa_service.json_line({"type": "message_id", "id": str(chat_message.id)})

            collected_blocks = []
            my_link = []
            suggested = []

            for event in llm_instance.stream_blocks(
                context=masked_docs,
                query=query,
                original_query=data.q,
                chat_history=chat_history,
            ):
                etype = event.get("type")

                if etype == "block":
                    tag = str(event.get("tag", ""))
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        continue
                    if "content" in event:
                        event["content"] = masking.unmask_text(event["content"], state=masking_state)
                        collected_blocks.append({"tag": tag, "content": event["content"]})
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    raw_links = event.get("links", []) or []
                    my_link = qa_service.normalize_citation_links(raw_links)

                elif etype == "suggested":
                    suggested = [masking.unmask_text(q, state=masking_state) for q in event.get("questions", [])]

                elif etype == "done":
                    break

            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)
                chatbot.update_state(
                    config,
                    {"messages": [
                        HumanMessage(content=data.q),
                        AIMessage(content=json.dumps(collected_blocks)),
                    ]},
                )

            serialize_doc_list = qa_service.documents_to_dicts(docs_list)
            citation_filenames = [c.get("filename", "") for c in my_link]
            my_link = filter_sources_by_citation(
                citations=citation_filenames,
                org_id=current_user.org_id,
                sources=serialize_doc_list,
            )

            llm_response = extract_text_only_from_html(collected_blocks)

            chat_message.query = data.q
            chat_message.response = llm_response
            chat_message.tokens = 0
            chat_message.citation = my_link
            chat_message.html_response = collected_blocks
            chat_message.unanswer_query = False if collected_blocks else True

            db.commit()
            db.refresh(chat_message)

            yield qa_service.json_line({"type": "citations", "links": my_link})
            yield qa_service.json_line({"type": "suggested", "questions": suggested})
            yield qa_service.json_line({"type": "done"})

        except Exception:
            logger.exception("edit_message streaming error")
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
# Left unchanged for the same reason as edit_message above.
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
    @traceable(name="ask_over_selected_documents", project="core", metadata={"description": "Ask a question over allowed departments over particular document", "response_type": "streaming", "thread_id": thread_id, "user_id": current_user.id, "org_id": current_user.org_id}, tags=["threads", "users"])
    def event_generator(query=data.q.strip()):
        yield qa_service.json_line({"type": "stage", "value": "thinking"})

        try:
            s = time.monotonic()

            doc_suborg = qa_service.get_suborg_by_document_id(db, data.document_id)
            if not doc_suborg:
                yield qa_service.json_line({"type": "error", "message": "No department found for given document"})
                yield qa_service.json_line({"type": "done"})
                return

            allowed = qa_service.allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
            if not allowed:
                yield qa_service.json_line({"type": "error", "message": "Not valid thread for current user"})
                yield qa_service.json_line({"type": "done"})
                return

            document_ids = qa_service.get_selected_docs_ids_by_thread_id(db, thread_id)

            vector_store = vectorManager.get_store(
                embeddings=embeddings,
                persist_dir=f"{BASE_DIR}/{current_user.org_id}",
            )
            rv = retriever.get_retreiver_by_document_id(
                vector_store=vector_store.get_vector_store(),
                search_type="similarity",
                top_n=data.top_k,
                document_id=data.document_id,
            )

            docs_list = rv.invoke(input=data.q)
            docs_list = qa_service.rerank_docs(query=data.q, docs=docs_list, top_n=5)

            masking_state = PiiMaskingState()
            masking = Masking()
            query, masked_docs = masking.mask_query_and_docs(data.q, docs_list, masking_state)

            provider = qa_service.get_thread_provider(db, current_user, thread_id)

            memory_thread_id = f"{current_user.org_id}:{thread_id}"
            config = {"configurable": {"thread_id": str(memory_thread_id)}}

            @traceable(name="load_chat_history", project="core", metadata={"description": "Load prior chat history for context"}, tags=["threads", "users"])
            def load_chat_history():
                with qa_service.get_checkpointer() as checkpointer:
                    chatbot = qa_service.builder(checkpointer=checkpointer)
                    current_state = chatbot.get_state(config)
                    chat_history = []
                    if current_state and current_state.values.get("messages"):
                        chat_history = current_state.values["messages"]
                return chat_history

            chat_history = load_chat_history()

            llm_instance = {
                "openai": llm_openai,
                "gemini": llm_gemini,
                "anthropic": llm_anthropic,
            }.get(provider, llm_openai)

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

            collected_blocks = []
            my_link = []
            suggested = []
            llm_emitted_citations = False

            for event in llm_instance.stream_blocks(
                context=masked_docs,
                query=query,
                original_query=data.q,
                chat_history=chat_history,
            ):
                etype = event.get("type")

                if etype == "block":
                    tag = str(event.get("tag", ""))
                    if tag.startswith("/"):
                        yield qa_service.json_line(event)
                        continue
                    if "content" in event:
                        event["content"] = masking.unmask_text(event["content"], state=masking_state)
                        collected_blocks.append({"tag": tag, "content": event["content"]})
                    yield qa_service.json_line(event)

                elif etype == "citations":
                    if event.get("links"):
                        llm_emitted_citations = True

                elif etype == "suggested":
                    suggested = [masking.unmask_text(q, state=masking_state) for q in event.get("questions", [])]

                elif etype == "done":
                    break

            if llm_emitted_citations:
                serialize_doc_list = qa_service.documents_to_dicts(docs_list)
                citation_filenames = []
                for d in serialize_doc_list:
                    meta = d.get("metadata") or {}
                    fname = meta.get("filename") or meta.get("source", "")
                    if fname:
                        citation_filenames.append(fname)
                citation_filenames = list(dict.fromkeys(citation_filenames))

                my_link = filter_sources_by_citation(
                    citations=citation_filenames,
                    org_id=current_user.org_id,
                    sources=serialize_doc_list,
                )
            else:
                my_link = []

            llm_response = extract_text_only_from_html(collected_blocks)
            yield qa_service.json_line({"type": "citations", "links": my_link})
            yield qa_service.json_line({"type": "suggested", "questions": suggested})
            yield qa_service.json_line({"type": "done"})

            title = collected_blocks[0]["content"] if collected_blocks else data.q
            qa_service.update_chat_thread_description(
                db, current_user.org_id, current_user.id, thread_id, description=title
            )

            with qa_service.get_checkpointer() as checkpointer:
                chatbot = qa_service.builder(checkpointer=checkpointer)
                chatbot.update_state(
                    config,
                    {"messages": [
                        HumanMessage(content=data.q),
                        AIMessage(content=json.dumps(collected_blocks)),
                    ]},
                )

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
            ).update({"updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))})
            db.commit()

            if not document_ids:
                db.query(ChatThreads).filter(
                    ChatThreads.id == thread_id,
                    ChatThreads.org_id == current_user.org_id,
                    ChatThreads.user_id == current_user.id
                ).update({"document_ids": {"doc_ids": list(set(data.document_id))}})
                db.commit()

        except Exception:
            logger.exception("ask_by_id streaming error")
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