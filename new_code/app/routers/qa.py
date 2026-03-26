# app/routers/qa.py

from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    status,
    Query,
    WebSocket,
    BackgroundTasks,
)


from app.schemas.request_schema import AskRequest, AskRequestOnDocument
from sqlalchemy.orm import Session
from sqlalchemy import select
import os
from pydantic import BaseModel, Field
from app.database import get_db
from app.services.auth import get_current_active_user, get_current_active_socket_user
from app.models.user_model import User as UserModel
from app.models.user_access_department_model import UserAccessDepartment, UserType
from app.models.department_model import Department as DepartmentModel
from app.models.doc_models import DocChunk, OrgDocument
from app.utils.embeddings import embed_texts
from app.models.chat_thread_model import ChatThreads
from fastapi.responses import StreamingResponse

from app.Rag.utils import embeddings, llm_openai, llm_gemini, BASE_DIR, retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
from langchain_classic.text_splitter import CharacterTextSplitter
from app.Rag.HighlightText import HighlightText
from app.models.chat_messages_model import ChatMessage
from app.models.doc_embedding_model import DocEmbedding

router = APIRouter(prefix="/qa", tags=["qa"])

from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any
from rq import Queue
from redis import Redis
import time
from app.Rag.utils import extract_text_only_from_html

redis_conn = Redis()
from flashrank import Ranker, RerankRequest

_cross_encoder_ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2")  # loaded once at module level

def _rerank_docs(query: str, docs: list, top_n: int = 5) -> list:
    """Rerank docs using FlashRank and return top_n most relevant."""
    if not docs:
        return docs

    passages = [{"id": i, "text": doc.page_content} for i, doc in enumerate(docs)]
    rerank_request = RerankRequest(query=query, passages=passages)
    results = _cross_encoder_ranker.rerank(rerank_request)

    top_results = sorted(results, key=lambda x: x["score"], reverse=True)[:top_n]
    return [docs[r["id"]] for r in top_results]









from langchain_core.messages import HumanMessage  

def _access_public(a: UserAccessDepartment) -> Dict:
    return {
        "id": a.id,
        "org_id": a.org_id,
        "dept_id": a.dept_id,
        "user_id": a.user_id,
        "can_read": getattr(a, "can_read", True),
        "can_upload": getattr(a, "can_upload", False),
        "is_author": getattr(a, "is_author", False),
        "neural_cap": getattr(a, "neural_cap", None),
    }


def list_user_access(
    org_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    """
    Admin-only: list which departments (Departments) this user has access to
    within the admin's organization.
    """
    rows = (
        db.query(UserAccessDepartment)
        .join(
            DepartmentModel,
            DepartmentModel.id == UserAccessDepartment.dept_id,
        )
        .filter(
            DepartmentModel.org_id == org_id,
            UserAccessDepartment.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r)["dept_id"] for r in rows]


def list_user_threads(
    org_id: int,
    user_id: int,
    db: Session = Depends(get_db),
):
    """List user threads by org_id and user_id"""
    rows = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.org_id == org_id,
            ChatThreads.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r) for r in rows]


class CitationItem(BaseModel):
    file: str = Field(..., description="Name of the PDF or source file used")
    document_id: str = Field(
        ..., description="Document id present in metadata with name document_id"
    )


# ─────────────────────────────────────────
# HTML BLOCK MODEL (for frontend rendering)
# ─────────────────────────────────────────
class HtmlItem(BaseModel):
    tag: str = Field(
        ...,
        description=(
            "Semantic HTML tag chosen intentionally "
            "(h1, h2, p, ul, li, table, tr, th, td, code, pre)"
        ),
    )

    content: str = Field(
        ...,
        description="Content for this tag. Must match the purpose of the tag.",
    )


# ─────────────────────────────────────────
# FOLLOW-UP QUESTIONS MODEL
# ─────────────────────────────────────────
class SuggestedFollowUpQuestions(BaseModel):
    """
    Always include relevant follow-up questions.
    Must relate to based on query, response and document mix.
    Do NOT include answers.
    """

    tag: Literal["ul"] = Field(
        description="HTML container ul",
    )
    content: str = Field(
        ...,
        description="content like '<li>Question...</li>' Return ONE <ul> block containing multiple <li> items. Do not create multiple ul tags.",
    )


# ─────────────────────────────────────────
# FINAL RAG RESPONSE MODEL
# ─────────────────────────────────────────
class RAGResponse(BaseModel):
    title: str = Field(
        ...,
        description="Short title based ONLY on user query (not dependent on context)",
    )

    html_response: List[HtmlItem] = Field(
        ...,
        description=(
            "Frontend-ready structured HTML blocks. "
            "Use semantic tags properly (h1, h2, p, table, ul, li etc)."
        ),
    )

    citation: List = Field(..., description="return filename only which is present in metadata of documents for cited sources otherwise return empty list")

    is_context_availale: Literal["True", "False"] = Field(
        ...,
        description="Whether answer was generated from provided context",
    )

    suggested_follow_ups: list[SuggestedFollowUpQuestions] = Field(
        ...,
        default_factory=list,
        min_length=3,
        max_length=3,
        description="Must contain ONE ul tag with exactly 3 li questions",
    )


import uuid


def extract_list_of_user_threads(s: ChatThreads) -> Dict:
    return {"id": s.id}


import json

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from dotenv import load_dotenv
import os
from pydantic import BaseModel, Field


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    total_token: int
    context: list
    provider: str


def chat_node(state: ChatState):
    messages = state["messages"]
    context = state["context"]
    provider = state.get("provider") or  "openai"

    if provider == "openai":
        response = llm_openai.generate_answer_with_structure(
            context=context, query=messages, schema=RAGResponse
        )
    elif provider == "gemini":
        response = llm_gemini.generate_answer_with_structure(
            context=context, query=messages, schema=RAGResponse
        )

    total_token = response.usage_metadata["total_tokens"]
    return {"messages": [response], "total_token": total_token}


# Don't compile yet - we'll compile with checkpointer in the functions
builder = (
    StateGraph(ChatState)
    .add_node("chat_node", chat_node)
    .add_edge(START, "chat_node")
    .add_edge("chat_node", END)
    .compile
)

# Initialize checkpointer
with PyMySQLSaver.from_conn_string(
    conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
) as cp:

    cp.setup()

def _get_thread_provider(db: Session, current_user, thread_id: int) -> str:
    thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
            ChatThreads.id == thread_id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread.llm_provider


def _allowed_thread_id(db, current_user, t_id):
    threads = db.query(ChatThreads).filter(
        ChatThreads.org_id == current_user.org_id,
        ChatThreads.user_id == current_user.id,
        ChatThreads.id == t_id,
    )
    threads = [u.id for u in threads]
    return threads


def update_chat_thread_description(
    db: Session, org_id: int, user_id: int, chat_thread_id: int, description: str
) -> None:
    chat_thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.id == chat_thread_id,
            ChatThreads.user_id == user_id,
            ChatThreads.org_id == org_id,
        )
        .first()
    )

    if chat_thread and chat_thread.description:
        return

    chat_thread.description = description
    db.add(chat_thread)
    db.commit()


import time
import re
import base64
from app.Rag.PdfUploader import upload_pdf_to_github
from app.Rag.TexttoPdf import text_to_pdf_bytes

from app.utils.celery_app import celery_app, filter_sources_by_citation
from celery.result import AsyncResult

import sys
from langchain_core.documents import Document


def document_to_dict(doc: Document) -> dict:
    return {"page_content": doc.page_content, "metadata": doc.metadata or {}}


def dict_to_document(data: dict) -> Document:
    return Document(
        page_content=data["page_content"], metadata=data.get("metadata", {})
    )


def documents_to_dicts(docs: list[Document]) -> list[dict]:
    return [document_to_dict(doc) for doc in docs]


def _is_org_admin(db: Session, user: UserModel, org_id: int) -> bool:
    admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user.id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )

    if admin:
        print("✅ USER IS ADMIN:", admin.user_id, admin.org_id)
        return True
    else:
        print("❌ USER IS NOT ADMIN")
        return False


@router.get("/list_user_threads")
def test_endpoint(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    next_id: Optional[int] = 0,
    limit: int = Query(20, le=100),
    name: Optional[str] = Query(None), 
):
    print("hello")
    query = db.query(ChatThreads.id, ChatThreads.description, ChatThreads.updated_at).filter(
        ChatThreads.org_id == current_user.org_id,
        ChatThreads.user_id == current_user.id,
    )
    if name and name.strip():
        query = query.filter(
            ChatThreads.description.ilike(f"%{name.strip()}%")
        )
    if next_id:
        query = query.filter(ChatThreads.id < next_id)

    messages = (
        query.order_by(ChatThreads.updated_at.desc())
        .limit(limit + 1)
        .all()
    )

    has_more = len(messages) > limit
    messages = messages[:limit]
    print(messages)
    new_next_id = messages[-1].id if messages else None
    response = []
    for msg in messages:
        # print(msg)
        response.append(
            {
                "thread_id": msg.id,
                "title": msg.description or "",
                
                "date":msg.updated_at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    # return HTTPException(status_code=500, detail="No threads found") 
    return {"messages": response, "next_id": new_next_id, "has_more": has_more}
    # return {"messages": response, "next_id": new_next_id, "has_more": has_more}


@router.delete("/delete_thread/{thread_id}", summary="Delete thread by id")
def delete_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.id == thread_id,
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"message": "Thread deleted successfully"}


@router.get("/title/{thread_id}", summary="Get thread title")
def get_description(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.id == thread_id,
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"title": thread.description or ""}


@router.put("/rename_title/{thread_id}", summary="Update thread title")
def update_description(
    thread_id: int,
    description: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.id == thread_id,
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread.description = description
    db.add(thread)
    db.commit()
    return {"message": "title updated successfully"}


from enum import Enum


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"


def get_next_llm_provider(
    db: Session,
    current_user: UserModel,
) -> LLMProvider:
    """
    Retrieve current LLM provider from chat_threads
    and return the toggled provider.

    openai → gemini
    gemini → openai
    """

    thread = (
        db.query(ChatThreads)
        .order_by(ChatThreads.id.desc())
        .filter(
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
        )
        .first()
    )

    if not thread or not thread.llm_provider:
        return LLMProvider.OPENAI

    current = thread.llm_provider.lower()

    if current == LLMProvider.OPENAI:
        return LLMProvider.GEMINI

    if current == LLMProvider.GEMINI:
        return LLMProvider.OPENAI

    return LLMProvider.OPENAI


@router.get("/thread_id", summary="Requesting new Thread ID")
def ask_thread(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    next_provider = get_next_llm_provider(db, current_user)
    user_thread = ChatThreads(
        user_id=current_user.id,
        org_id=current_user.org_id,
        description="",
        llm_provider=next_provider,
    )
    db.add(user_thread)
    db.commit()
    db.flush()
    title = user_thread.description or ""

    return {"thread_id": user_thread.id, "title": title}


from fastapi.responses import StreamingResponse
import io
from pathlib import Path


def _check_user_access_to_document(
    db: Session, current_user: UserModel, document_id: int
):
    isadmin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    if isadmin:
        return
    access = (
        db.query(UserAccessDepartment)
        .join(OrgDocument, UserAccessDepartment.dept_id == OrgDocument.dept_id)
        .filter(
            UserAccessDepartment.user_id == current_user.id,
            OrgDocument.id == document_id,
        )
        .first()
    )
    if not access:
        raise HTTPException(status_code=403, detail="No access to this document")


from urllib.request import urlopen


# @router.get("/pdf/{id}", summary="Get citated link by id")
# def cited(
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
#     id: str = "",
# ):
#     job = AsyncResult(id, app=celery_app)
#     while True:
#         if job.status == "FAILURE":
#             raise HTTPException(
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 detail="Failed to process the citation links.",
#             )

#         if job.state == "SUCCESS":
#             break

#         time.sleep(1)

#     if job.status == "SUCCESS":
#         if job.result:
#             doc_id = job.result["document_id"]
#             print("doc_id", doc_id)
#             _check_user_access_to_document(
#                 db=db, current_user=current_user, document_id=doc_id
#             )
#             pdf_bytes = base64.b64decode(job.result["pdf"])
#             pdf_url = job.result["link"]

#         return StreamingResponse(
#             io.BytesIO(pdf_bytes),
#             media_type="application/pdf",
#             headers={"Content-Disposition": "inline"},
#         )


@router.get("/pdf/{id}", summary="Get citated link by id")
def cited(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    id: str = "",
):
    # ✅ Check if PDF already written to disk by the task
    pdf_path = Path("app/citation_files") / f"{id}.pdf"

    if pdf_path.exists():
        return StreamingResponse(
            io.BytesIO(pdf_path.read_bytes()),
            media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )

    print("path not exists, falling back to celery job")

    # ✅ Fall back to Celery job with a 5s timeout
    job = AsyncResult(id, app=celery_app)
    elapsed = 0
    max_wait = 5  # seconds

    while elapsed < max_wait:
        if job.status == "FAILURE":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Task {id} failed: {str(job.result)}",
            )

        if job.state == "SUCCESS":
            break

        time.sleep(1)
        elapsed += 1
    else:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Document could not be shown. A problem occurred, please try again later.",
        )

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

    _check_user_access_to_document(
        db=db, current_user=current_user, document_id=doc_id
    )

    pdf_bytes = base64.b64decode(result["pdf"])

    # ✅ Write to disk so next request serves directly from path
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        print(f"PDF cached to disk at {pdf_path}")
    except Exception as e:
        print(f"Warning: could not write PDF to disk: {e}")  # non-fatal, still serve it

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )

from fastapi.responses import Response


@router.get("/pdf-download/{id}", summary="Get citated link by id")
def download(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    id: str = "",
):
    job = AsyncResult(id, app=celery_app)
    print(job.status)
    if job.status == "SUCCESS":
        if job.result:
            doc_id = job.result["document_id"]
            print("doc_id", doc_id)
            _check_user_access_to_document(
                db=db, current_user=current_user, document_id=doc_id
            )
            pdf_bytes = base64.b64decode(job.result["pdf"])
            pdf_url = job.result["link"]
            original_filename = job.result["filename"]
            filename_without_ext = Path(original_filename).stem

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename_without_ext}"
            },
        )


def _list_of_departments(db: Session, current_user: UserModel) -> Dict:
    departments = (
        db.query(DepartmentModel)
        .filter(DepartmentModel.org_id == current_user.org_id)
        .all()
    )
    return [s.id for s in departments]


def _is_org_exist(db: Session, org_id: int) -> bool:
    org = db.query(UserModel).filter(UserModel.org_id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")


from app.Rag.Masking import Masking, PiiMaskingState

import random
from typing import Any, Dict, Tuple

from app.services.embedding_token import (
    dept_license_and_token_update,
    user_license_and_token_update,
)


def get_random_llm_provider():
    """Return random LLM provider"""
    return "openai" if random.random() < 0.5 else "gemini"


def _invoke_chatbot_with_fallback(
    chatbot: Any,
    payload: Dict[str, Any],
    base_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """
    Picks 50/50 provider. If primary fails, falls back to the other provider.
    Returns (answer, provider_used).
    """
    primary = get_random_llm_provider()
    fallback = "gemini" if primary == "openai" else "openai"

    last_err: Exception | None = None
    for provider in (primary, fallback):
        try:
            cfg = dict(base_config or {})
            cfg.setdefault("configurable", {})
            cfg["configurable"]["llm_provider"] = provider
            ans = chatbot.invoke(payload, config=cfg)
            return ans, provider
        except Exception as e:
            last_err = e
            print(
                f" LLM failed [{provider}] => {repr(e)}. Trying fallback...", flush=True
            )
            time.sleep(0.2)

    raise HTTPException(
        status_code=502,
        detail=f"Both LLM providers failed. Last error: {repr(last_err)}",
    )


def unmask_html_list(html_list: list, state: PiiMaskingState) -> list:
    masking = Masking()
    for item in html_list:
        if isinstance(item, dict) and "content" in item:
            item["content"] = masking.unmask_text(item["content"], state=state)
        elif isinstance(item, list):
            # handle nested lists like suggested_follow_ups
            for nested in item:
                if isinstance(nested, dict) and "content" in nested:
                    nested["content"] = masking.unmask_text(nested["content"], state=state)
    return html_list

# def unmask_html_list(html_list: list) -> list:
#     state = PiiMaskingState()
#     masking = Masking()
#     for item in html_list:
#         if isinstance(item, dict) and "content" in item:
#             item["content"] = masking.unmask_text(item["content"], state=state)
#     return html_list


def safe_json_from_llm(text: str):
    s = text.strip()

    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")

    candidate = s[start : end + 1].strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        left = max(0, e.pos - 200)
        right = min(len(candidate), e.pos + 200)
        ctx = candidate[left:right]
        raise ValueError(
            f"Invalid JSON: {e}\n--- context around pos {e.pos} ---\n{ctx}\n-------------------------------"
        ) from e


def extract_json_object(text: str) -> str:
    """Extract the outermost JSON object from a bigger string."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in text")
    return text[start : end + 1]


def escape_quotes_inside_content_fields(raw: str) -> str:
    """
    Fix invalid JSON where inner quotes appear inside values of "content": " ... "
    Example: Liquidity is lowest in the "gap" between ...
    We convert those inner quotes to \"
    """
    s = raw
    out = []
    i = 0
    n = len(s)

    def is_escaped(pos: int) -> bool:
        backslashes = 0
        j = pos - 1
        while j >= 0 and s[j] == "\\":
            backslashes += 1
            j -= 1
        return (backslashes % 2) == 1

    while i < n:
        if s.startswith('"content"', i):
            out.append('"content"')
            i += len('"content"')

            while i < n and s[i].isspace():
                out.append(s[i])
                i += 1
            if i < n and s[i] == ":":
                out.append(":")
                i += 1
            while i < n and s[i].isspace():
                out.append(s[i])
                i += 1

            if i < n and s[i] == '"':
                out.append('"')
                i += 1

                while i < n:
                    ch = s[i]

                    if ch == '"' and not is_escaped(i):
                        j = i + 1
                        while j < n and s[j].isspace():
                            j += 1
                        if j < n and s[j] in [",", "}"]:
                            out.append('"')
                            i += 1
                            break
                        else:
                            out.append('\\"')
                            i += 1
                            continue

                    out.append(ch)
                    i += 1

                continue

        out.append(s[i])
        i += 1

    return "".join(out)


def parse_llm_like_json(text: str) -> dict:
    """Full pipeline: extract JSON -> repair content quotes -> json.loads -> dict"""
    obj = extract_json_object(text)
    repaired = escape_quotes_inside_content_fields(obj)
    return json.loads(repaired)


def format_followups(output: dict) -> str:
    """
    Convert suggested_follow_ups list into HTML <li> string.
    Returns empty string if not present.
    """

    try:
        followups = output.get("suggested_follow_ups", {}).get("content", [])

        if not followups or not isinstance(followups, list):
            return ""

        html_string = "".join([f"<li>{q}</li>" for q in followups if q])

        return html_string

    except Exception as e:
        print("Followup format error:", e)
        return ""


# @router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
# def ask(
#     thread_id: int,
#     data: AskRequest,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     s = time.monotonic()
#     _is_org_exist(db, org_id=current_user.org_id)
#     print(data, thread_id, current_user.id, current_user.org_id)
#     admin = _is_org_admin(db, current_user, current_user.org_id)
#     if admin:
#         print("is admin ?")
#         user_allowed_dept_ids = _list_of_departments(db, current_user)
#     else:
#         user_allowed_dept_ids = list_user_access(
#             user_id=current_user.id, org_id=current_user.org_id, db=db
#         )
#     print("all sub org ids", user_allowed_dept_ids, type(user_allowed_dept_ids))

#     allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
#     print("allowed thread", allowed)

#     if not allowed:
#         raise HTTPException(status_code=403, detail="Not valid thread for current user")

#     retrieval_list = []
#     vectorStore = vectorManager.get_store(
#         embeddings=embeddings, persist_dir=f"{BASE_DIR}/{current_user.org_id}"
#     )

#     if admin:
#         rv = retriever.get_retreiver(
#             vector_store=vectorStore.get_vector_store(),
#             search_type="similarity",
#             top_n=data.top_k,
#         )
#     else:
#         user_allowed_dept_ids.append("global")
#         rv = retriever.get_retreiver_by_department_ids(
#             vector_store=vectorStore.get_vector_store(),
#             search_type="similarity",
#             top_n=data.top_k,
#             dept_ids=user_allowed_dept_ids,
#         )

#     retrieval_list.append(rv)
#     print("test time", time.monotonic() - s)
#     rvm = EnsembleRetriever(retrievers=retrieval_list)
#     docs_list = rv.invoke(input=data.q)
#     # print("docs_list", docs_list)
#     docs_list = _rerank_docs(
#         query=data.q,
#         docs=docs_list,
#         top_n=5
#     )
#     print(f"Reranked to top {len(docs_list)} chunks via FlashRank")
#     print(docs_list)
#     print("context extracton time", time.monotonic() - s)

#     ss = time.monotonic()
#     masking_state = PiiMaskingState()
#     masking = Masking()

#     masked_docs = masking.mask_texts(docs_list, masking_state)
#     print("masking time", time.monotonic() - ss)

#     s1 = time.monotonic()
#     with PyMySQLSaver.from_conn_string(
#         conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
#     ) as checkpointer:
#         chatbot = builder(checkpointer=checkpointer)

#         #  Use a stable unique key per org+thread so it restores the same memory
#         # (Multi-tenant safe and avoids collision between orgs)
#         memory_thread_id = f"{current_user.org_id}:{thread_id}"

#         config = {"configurable": {"thread_id": str(memory_thread_id)}}
#         provider = _get_thread_provider(db, current_user, thread_id)
#         print("provider", provider)
#         answer = chatbot.invoke(
#             {
#                 "messages": [HumanMessage(content=data.q)],  # IMPORTANT
#                 "context": masked_docs,
#                 #   "context": docs_list,
#                 "provider": provider,
#             },
#             config=config
   
#         )

#     siz = sys.getsizeof(rvm)
#     import json, re

#     res = answer["messages"][-1].content
#     e = time.monotonic()

#     res = res.replace("```json", "").replace("```", "")
#     output = parse_llm_like_json(res)

#     print("masked html_response", output["html_response"])

#     serialize_doc_list = documents_to_dicts(docs_list)
#     print("output citation", output["citation"])
#     my_link = filter_sources_by_citation(
#         citations=output["citation"],
#         org_id=current_user.org_id,
#         sources=serialize_doc_list,
#     )
#     output["html_response"] = unmask_html_list(output["html_response"],state=masking_state)
#     print("time1", time.monotonic() - s1)

#     llm_response = extract_text_only_from_html(output["html_response"])

#     update_chat_thread_description(
#         db, current_user.org_id, current_user.id, thread_id, description=output["title"]
#     )

#     if output["is_context_availale"] == "True":
#         chat_message = ChatMessage(
#             query=data.q,
#             response=llm_response,
#             thread_id=thread_id,
#             tokens=answer["total_token"],
#             citation=my_link,
#             html_response=output["html_response"],
#             unanswer_query=False,
#         )
#     else:
#         chat_message = ChatMessage(
#             query=data.q,
#             response=llm_response,
#             thread_id=thread_id,
#             tokens=answer["total_token"],
#             citation=my_link,
#             html_response=output["html_response"],
#             unanswer_query=True,
#         )
#     db.add(chat_message)
#     db.commit()
#     db.flush()
#     db.query(ChatThreads).filter(ChatThreads.id == thread_id,ChatThreads.org_id == current_user.org_id,ChatThreads.user_id == current_user.id).update({"updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))})
#     db.commit()
#     # output["html_response"].append(
#     #     {"tag": "h1", "content": "Suggested Follow Up Questions"}
#     # )
#     # output["html_response"].append(output["suggested_follow_ups"][0])
    
#     items = re.findall(r'<li>(.*?)</li>', output["suggested_follow_ups"][0]['content'])
#     print("Suggested follow-up questions:", items)
#     print("model response time", time.monotonic() - s1)
#     print("total time", time.monotonic() - s)

#     return {
#         "query_time": e - s,
#         "html_response": output["html_response"],
#         "message_id": chat_message.id,
#         "response": llm_response,
#         "citations": output["citation"],
#         "total_token": answer["total_token"],
#         "suggested": items,
#         "links": my_link,
#     }



from langchain_core.messages import HumanMessage, RemoveMessage
@router.put("/ask/{thread_id}/edit/{message_id}", summary="Edit the latest chat message and rerun RAG")
def edit_message(
    thread_id: int,
    message_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):  
    s = time.monotonic()
    _is_org_exist(db, org_id=current_user.org_id)
 
    # --- Validate thread ownership ---
    allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="Not valid thread for current user")
 
    # --- Fetch the existing chat message row ---
    chat_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.thread_id == thread_id)
        .first()
    )
    if not chat_message:
        raise HTTPException(status_code=404, detail="Chat message not found")
 
    # --- Ensure it's the latest message in the thread ---
    latest_message = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.id.desc())
        .first()
    )
    if not latest_message or latest_message.id != message_id:
        raise HTTPException(status_code=403, detail="Only the latest message in a thread can be edited")
 
    # --- STEP 1: Open checkpointer, fetch and remove latest messages FIRST ---
    with PyMySQLSaver.from_conn_string(
        conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
    ) as checkpointer:
        chatbot = builder(checkpointer=checkpointer)
 
        memory_thread_id = f"{current_user.org_id}:{thread_id}"
        config = {"configurable": {"thread_id": str(memory_thread_id)}}
 
        provider = _get_thread_provider(db, current_user, thread_id)
 
        # Fetch current checkpoint state
        current_state = chatbot.get_state(config)
        if current_state and current_state.values.get("messages"):
            messages = current_state.values["messages"]
            messages_to_remove = messages[-2:] if len(messages) >= 2 else messages[-1:]
 
            # Print messages before removing
            print("=== MESSAGES TO BE REMOVED FROM CHECKPOINT ===")
            for m in messages_to_remove:
                print(f"Type: {type(m).__name__} | ID: {m.id} | Content: {m.content}")
            print("=== END ===")
 
            # Remove stale latest human + AI message pair
            chatbot.update_state(
                config,
                {"messages": [RemoveMessage(id=m.id) for m in messages_to_remove]}
            )
            print(f"Removed {len(messages_to_remove)} stale messages from checkpoint")
 
        # --- STEP 2: Determine department access ---
        admin = _is_org_admin(db, current_user, current_user.org_id)
        if admin:
            user_allowed_dept_ids = _list_of_departments(db, current_user)
        else:
            user_allowed_dept_ids = list_user_access(
                user_id=current_user.id, org_id=current_user.org_id, db=db
            )
 
        # --- STEP 3: Retrieval ---
        vectorStore = vectorManager.get_store(
            embeddings=embeddings, persist_dir=f"{BASE_DIR}/{current_user.org_id}"
        )
 
        if admin:
            rv = retriever.get_retreiver(
                vector_store=vectorStore.get_vector_store(),
                search_type="similarity",
                top_n=data.top_k,
            )
        else:
            user_allowed_dept_ids.append("global")
            rv = retriever.get_retreiver_by_department_ids(
                vector_store=vectorStore.get_vector_store(),
                search_type="similarity",
                top_n=data.top_k,
                dept_ids=user_allowed_dept_ids,
            )
 
        rvm = EnsembleRetriever(retrievers=[rv])
        docs_list = rvm.invoke(input=data.q)
        print(f"Vector retriever returned {len(docs_list)} chunks")
 
        # --- STEP 4: Rerank ---
        docs_list = _rerank_docs(query=data.q, docs=docs_list, top_n=5)
        print(f"Reranked to top {len(docs_list)} chunks via FlashRank")
 
        # --- STEP 5: PII Masking ---
        masking_state = PiiMaskingState()
        masking = Masking()
        masked_docs = masking.mask_texts(docs_list, masking_state)
 
        # --- STEP 6: Invoke with edited query — adds fresh messages into same thread ---
        answer = chatbot.invoke(
            {
                "messages": [HumanMessage(content=data.q)],
                "context": masked_docs,
                "provider": provider,
            },
            config=config,
        )
        print(f"Checkpoint updated with new edited messages under thread: {memory_thread_id}")
 
    e = time.monotonic()
 
    # --- Parse output ---
    res = answer["messages"][-1].content
    res = res.replace("json", "").replace("", "")
    output = parse_llm_like_json(res)
 
    output["html_response"] = unmask_html_list(output["html_response"], state=masking_state)
 
    serialize_doc_list = documents_to_dicts(docs_list)
    my_link = filter_sources_by_citation(
        citations=output["citation"],
        org_id=current_user.org_id,
        sources=serialize_doc_list,
    )
 
    llm_response = extract_text_only_from_html(output["html_response"])
 
    # --- Overwrite the existing ChatMessage row in DB ---
    chat_message.query = data.q
    chat_message.response = llm_response
    chat_message.tokens = answer["total_token"]
    chat_message.citation = my_link
    chat_message.html_response = output["html_response"]
    chat_message.unanswer_query = output["is_context_availale"] != "True"
 
    db.commit()
    db.refresh(chat_message)
    items = re.findall(r'<li>(.*?)</li>', output["suggested_follow_ups"][0]['content'])
    print("Suggested follow-up questions:", items)
    # --- Append suggested follow-ups ---
    # output["html_response"].append({"tag": "h1", "content": "Suggested Follow Up Questions"})
    # output["html_response"].append(output["suggested_follow_ups"])
 
    print("total edit time", time.monotonic() - s)
 
    return {
        "query_time": e - s,
        "html_response": output["html_response"],
        "response": llm_response,
        "citations": output["citation"],
        "total_token": answer["total_token"],
        "links": my_link,
        "suggested": items,
        "id": chat_message.id,
    }





def _get_suborg_by_document_id(db: Session, document_id_list: list[int]):
    dept_id = (
        db.query(OrgDocument.id, OrgDocument.dept_id)
        .filter(OrgDocument.id.in_(document_id_list))
        .all()
    )
    return dept_id


@router.get("/chat_history/{thread_id}", summary="Get chat history by thread id")
def get_chat_history(
    thread_id: int,
    limit: int = Query(20, le=100),
    next_id: Optional[int] = 0,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    query = db.query(ChatMessage).filter(
        ChatMessage.thread_id == thread_id,
    )

    if next_id:
        query = query.filter(ChatMessage.id < next_id)

    messages = (
        query.order_by(ChatMessage.id.desc())
        .limit(limit + 1)
        .all()
    )

    has_more = len(messages) > limit
    messages = messages[:limit]

    new_next_id = messages[-1].id if messages else None
    response = []
    for msg in messages:
        response.append(
            {
                "id": msg.id,
                "query": msg.query,
                "response": msg.response,
                "html_response": msg.html_response,
                "links": msg.citation,
            }
            
        )
    return {"message": response, "next_id": new_next_id, "has_more": has_more}



def _get_list_allowed_documents(db: Session, current_user: UserModel):
    # Documents belonging to departments the user has access to
    is_admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == current_user.org_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == "ADMIN"
        )
        .first()
    )

    # ── Admin: return all org documents regardless of department ─────────
    if is_admin:
        results = (
            db.query(OrgDocument.id)
            .filter(
                OrgDocument.org_id == current_user.org_id,
                OrgDocument.deleted_at.is_(None)
            )
            .all()
        )
        return [r.id for r in results]
    dept_docs = (
        db.query(OrgDocument.id)
        .join(UserAccessDepartment, OrgDocument.dept_id == UserAccessDepartment.dept_id)
        .filter(
            UserAccessDepartment.org_id == current_user.org_id,
            UserAccessDepartment.user_id == current_user.id,
            OrgDocument.deleted_at.is_(None)        # exclude soft-deleted
        )
    )

    # Global documents (dept_id is NULL)
    global_docs = (
        db.query(OrgDocument.id)
        .filter(
            OrgDocument.org_id == current_user.org_id,
            OrgDocument.dept_id.is_(None),
            OrgDocument.deleted_at.is_(None)        # exclude soft-deleted
        )
    )

    # Union both and return flat list of IDs
    results = dept_docs.union(global_docs).all()
    return [r.id for r in results]



@router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
def ask(
    thread_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    s = time.monotonic()
    _is_org_exist(db, org_id=current_user.org_id)
    print(data, thread_id, current_user.id, current_user.org_id)
    docs=_get_list_allowed_documents(db, current_user)
    print("allowed documents for user", docs)
    # print(data.q, data.top_k)
    data=AskRequestOnDocument(document_id=docs, q=data.q, top_k=20)
    return ask_by_id(thread_id=thread_id, data=data, db=db, current_user=current_user)
    







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
    s = time.monotonic()
    print(data.document_id, thread_id)
    doc_suborg = _get_suborg_by_document_id(db, data.document_id)
    print(doc_suborg)
    if not doc_suborg:
        raise HTTPException(
            status_code=403, detail="No department found for given document"
        )
    retrieval_list = []

    allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
    print("allowed thread", allowed)
    if not allowed:
        raise HTTPException(status_code=403, detail="Not valid thread for current user")

    vectorStore = vectorManager.get_store(
        embeddings=embeddings,
        persist_dir=f"{BASE_DIR}/{current_user.org_id}",
    )
    rv = retriever.get_retreiver_by_document_id(
        vector_store=vectorStore.get_vector_store(),
        search_type="similarity",
        top_n=data.top_k,
        document_id=data.document_id,
    )

    docs_list = rv.invoke(input=data.q)
    # print(docs_list)
    docs_list = _rerank_docs(
        query=data.q,
        docs=docs_list,
        top_n=5
    )
    print(f"Reranked to top {len(docs_list)} chunks via FlashRank")
    print(docs_list)
    print("context extracton time", time.monotonic() - s)

    ss = time.monotonic()
    masking_state = PiiMaskingState()
    masking = Masking()

    masked_docs = masking.mask_texts(docs_list, masking_state)
    print("masking time", time.monotonic() - ss)

    s1 = time.monotonic()
    with PyMySQLSaver.from_conn_string(
        conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
    ) as checkpointer:
        chatbot = builder(checkpointer=checkpointer)

        #  Use a stable unique key per org+thread so it restores the same memory
        # (Multi-tenant safe and avoids collision between orgs)
        memory_thread_id = f"{current_user.org_id}:{thread_id}"

        config = {"configurable": {"thread_id": str(memory_thread_id)}}
        provider = _get_thread_provider(db, current_user, thread_id)
        print("provider", provider)
        answer = chatbot.invoke(
            {
                "messages": [HumanMessage(content=data.q)],  # IMPORTANT
                "context": masked_docs,
                #   "context": docs_list,
                "provider": provider,
            },
            config=config
   
        )

    # siz = sys.getsizeof(rvm)
    import json, re

    res = answer["messages"][-1].content
    e = time.monotonic()

    res = res.replace("```json", "").replace("```", "")
    output = parse_llm_like_json(res)

    print("masked html_response", output["html_response"])

    serialize_doc_list = documents_to_dicts(docs_list)
    print("output citation", output["citation"])
    my_link = filter_sources_by_citation(
        citations=output["citation"],
        org_id=current_user.org_id,
        sources=serialize_doc_list,
    )
    output["html_response"] = unmask_html_list(output["html_response"],state=masking_state)
    print("time1", time.monotonic() - s1)

    llm_response = extract_text_only_from_html(output["html_response"])

    update_chat_thread_description(
        db, current_user.org_id, current_user.id, thread_id, description=output["title"]
    )

    if output["is_context_availale"] == "True":
        chat_message = ChatMessage(
            query=data.q,
            response=llm_response,
            thread_id=thread_id,
            tokens=answer["total_token"],
            citation=my_link,
            html_response=output["html_response"],
            unanswer_query=False,
        )
    else:
        chat_message = ChatMessage(
            query=data.q,
            response=llm_response,
            thread_id=thread_id,
            tokens=answer["total_token"],
            citation=my_link,
            html_response=output["html_response"],
            unanswer_query=True,
        )
    db.add(chat_message)
    db.commit()
    db.flush()
    db.query(ChatThreads).filter(ChatThreads.id == thread_id,ChatThreads.org_id == current_user.org_id,ChatThreads.user_id == current_user.id).update({"updated_at": datetime.now(ZoneInfo("Asia/Kolkata"))})
    db.commit()
    # output["html_response"].append(
    #     {"tag": "h1", "content": "Suggested Follow Up Questions"}
    # )
    # output["html_response"].append(output["suggested_follow_ups"][0])
    
    items = re.findall(r'<li>(.*?)</li>', output["suggested_follow_ups"][0]['content'])
    print("Suggested follow-up questions:", items)
    print("model response time", time.monotonic() - s1)
    print("total time", time.monotonic() - s)

    return {
        "query_time": e - s,
        "html_response": output["html_response"],
        "id": chat_message.id,
        "response": llm_response,
        "citations": output["citation"],
        "total_token": answer["total_token"],
        "suggested": items,
        "links": my_link,
    }
