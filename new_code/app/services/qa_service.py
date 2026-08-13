# app/services/qa_service.py
"""
Service layer for the QA / RAG chat feature.

Everything that is *not* a FastAPI route lives here: Pydantic/LLM schemas,
the LangGraph chat graph, retrieval/reranking/masking helpers, citation and
HTML-streaming utilities, and the actual generator functions that back the
streaming `/ask` endpoints.

`app/routers/qa.py` should only contain route declarations that call into
this module.
"""

from __future__ import annotations
from langsmith import traceable
import json
import os
import random
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

from flashrank import Ranker, RerankRequest
from redis import Redis
from celery.result import AsyncResult

from app.Rag.Masking import Masking, PiiMaskingState
from app.Rag.utils import llm_anthropic, llm_gemini, llm_openai
from app.models.chat_thread_model import ChatThreads
from app.models.department_model import Department as DepartmentModel
from app.models.doc_models import OrgDocument
from app.models.user_access_department_model import UserAccessDepartment, UserType
from app.models.user_model import User as UserModel
from app.utils.celery_app import celery_app
from langsmith import traceable
# ─────────────────────────────────────────────────────────────
# Infra singletons
# ─────────────────────────────────────────────────────────────
redis_conn = Redis()

# FlashRank cross-encoder reranker, loaded once at module level.
_cross_encoder_ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2")

CITATION_DIR = Path("app/citation_files")


# ─────────────────────────────────────────────────────────────
# Reranking
# ─────────────────────────────────────────────────────────────
@traceable(name="rerank_docs", project="core", metadata={"description": "Rerank documents using FlashRank"}, tags=["rerank","documents"])
def rerank_docs(query: str, docs: list, top_n: int = 5) -> list:
    """Rerank docs using FlashRank and return the top_n most relevant."""
    if not docs:
        return docs

    passages = [{"id": i, "text": doc.page_content} for i, doc in enumerate(docs)]
    rerank_request = RerankRequest(query=query, passages=passages)
    results = _cross_encoder_ranker.rerank(rerank_request)

    top_results = sorted(results, key=lambda x: x["score"], reverse=True)[:top_n]
    return [docs[r["id"]] for r in top_results]


# ─────────────────────────────────────────────────────────────
# Access / listing helpers
# ─────────────────────────────────────────────────────────────
def access_public(a: UserAccessDepartment) -> Dict:
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


def list_user_access(org_id: int, user_id: int, db: Session) -> List:
    """
    Admin-only: list which departments this user has access to within the
    admin's organization.
    """
    rows = (
        db.query(UserAccessDepartment)
        .join(DepartmentModel, DepartmentModel.id == UserAccessDepartment.dept_id)
        .filter(
            DepartmentModel.org_id == org_id,
            UserAccessDepartment.user_id == user_id,
        )
        .all()
    )
    return [access_public(r)["dept_id"] for r in rows]


def list_user_threads(org_id: int, user_id: int, db: Session) -> List:
    """List user threads by org_id and user_id."""
    rows = (
        db.query(ChatThreads)
        .filter(ChatThreads.org_id == org_id, ChatThreads.user_id == user_id)
        .all()
    )
    return [access_public(r) for r in rows]


def extract_list_of_user_threads(s: ChatThreads) -> Dict:
    return {"id": s.id}


# ─────────────────────────────────────────────────────────────
# Pydantic schemas for structured LLM output
# ─────────────────────────────────────────────────────────────
class CitationItem(BaseModel):
    file: str = Field(..., description="Name of the PDF or source file used")
    document_id: str = Field(
        ..., description="Document id present in metadata with name document_id"
    )


class HtmlItem(BaseModel):
    """Semantic HTML block used for frontend rendering."""

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


class SuggestedFollowUpQuestions(BaseModel):
    """
    Always include relevant follow-up questions.
    Must relate to the query, response, and document mix.
    Do NOT include answers.
    """

    tag: Literal["ul"] = Field(description="HTML container ul")
    content: str = Field(
        ...,
        description=(
            "content like '<li>Question...</li>' Return ONE <ul> block "
            "containing multiple <li> items. Do not create multiple ul tags."
        ),
    )


class RAGResponse(BaseModel):
    title: str = Field(
        ..., description="Short title based ONLY on user query (not dependent on context)"
    )
    html_response: List[HtmlItem] = Field(
        ...,
        description=(
            "Frontend-ready structured HTML blocks. "
            "Use semantic tags properly (h1, h2, p, table, ul, li etc)."
        ),
    )
    citation: List = Field(
        ...,
        description="return filename only which is present in metadata of documents for cited sources otherwise return empty list",
    )
    is_context_availale: Literal["True", "False"] = Field(
        ..., description="Whether answer was generated from provided context"
    )
    suggested_follow_ups: list[SuggestedFollowUpQuestions] = Field(
        ...,
        default_factory=list,
        min_length=3,
        max_length=3,
        description="Must contain ONE ul tag with exactly 3 li questions",
    )


# ─────────────────────────────────────────────────────────────
# LangGraph chat graph
# ─────────────────────────────────────────────────────────────
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    total_token: int
    context: list
    original_query: str
    provider: str


def chat_node(state: ChatState):
    messages = state["messages"]
    context = state["context"]
    provider = state.get("provider") or "openai"
    original_query = state.get("original_query") or ""

    if provider == "openai":
        response = llm_openai.generate_answer_with_structure(
            context=context, query=messages, original_query=original_query, schema=RAGResponse
        )
    elif provider == "gemini":
        response = llm_gemini.generate_answer_with_structure(
            context=context, query=messages, schema=RAGResponse
        )
    elif provider == "anthropic":
        response = llm_anthropic.generate_answer_with_structure(
            context=context, query=messages, schema=RAGResponse, original_query=original_query
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

    total_token = response.usage_metadata["total_tokens"]
    return {"messages": [response], "total_token": total_token}


# Don't compile yet - we compile with a checkpointer where needed.
builder = (
    StateGraph(ChatState)
    .add_node("chat_node", chat_node)
    .add_edge(START, "chat_node")
    .add_edge("chat_node", END)
    .compile
)

# Warm up / migrate the checkpoint DB schema once at import time.
with PyMySQLSaver.from_conn_string(conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")) as _cp:
    _cp.setup()


def get_checkpointer():
    """Context-manager factory for a fresh PyMySQLSaver connection."""
    return PyMySQLSaver.from_conn_string(conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL"))


# ─────────────────────────────────────────────────────────────
# Thread / provider helpers
# ─────────────────────────────────────────────────────────────
class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


def get_next_llm_provider(db: Session, current_user: UserModel) -> LLMProvider:
    cycle = {
        LLMProvider.OPENAI: LLMProvider.GEMINI,
        LLMProvider.GEMINI: LLMProvider.ANTHROPIC,
        LLMProvider.ANTHROPIC: LLMProvider.OPENAI,
    }

    thread = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,
        )
        .order_by(ChatThreads.id.desc())
        .first()
    )

    if not thread or not thread.llm_provider:
        return LLMProvider.OPENAI

    try:
        current = LLMProvider(thread.llm_provider.lower())
    except ValueError:
        return LLMProvider.OPENAI

    return cycle.get(current, LLMProvider.OPENAI)


def get_thread_provider(db: Session, current_user: UserModel, thread_id: int) -> str:
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

@traceable(name="allowed_thread_id", project="core", metadata={"description": "Get allowed thread IDs for user"}, tags=["threads","users"])
def allowed_thread_id(db: Session, current_user: UserModel, t_id: int) -> List[int]:
    threads = db.query(ChatThreads).filter(
        ChatThreads.org_id == current_user.org_id,
        ChatThreads.user_id == current_user.id,
        ChatThreads.id == t_id,
    )
    return [u.id for u in threads]


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


# ─────────────────────────────────────────────────────────────
# Document conversion helpers
# ─────────────────────────────────────────────────────────────
def document_to_dict(doc: Document) -> dict:
    return {"page_content": doc.page_content, "metadata": doc.metadata or {}}


def dict_to_document(data: dict) -> Document:
    return Document(page_content=data["page_content"], metadata=data.get("metadata", {}))


def documents_to_dicts(docs: list[Document]) -> list[dict]:
    return [document_to_dict(doc) for doc in docs]


# ─────────────────────────────────────────────────────────────
# Authorization helpers
# ─────────────────────────────────────────────────────────────
def is_org_admin(db: Session, user: UserModel, org_id: int) -> bool:
    admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.user_id == user.id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )
        .first()
    )
    return admin is not None


def check_user_access_to_document(db: Session, current_user: UserModel, document_id: int) -> None:
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


def list_of_departments(db: Session, current_user: UserModel) -> List:
    departments = (
        db.query(DepartmentModel).filter(DepartmentModel.org_id == current_user.org_id).all()
    )
    return [s.id for s in departments]


@traceable(name="is_org_exist", project="core", metadata={"description": "Check if organization exists"}, tags=["organizations"])
def is_org_exist(db: Session, org_id: int) -> None:
    org = db.query(UserModel).filter(UserModel.org_id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

@traceable(name="get_list_allowed_documents", project="core", metadata={"description": "Get list of allowed documents for user"}, tags=["documents","users"])
def get_list_allowed_documents(db: Session, current_user: UserModel) -> List[int]:
    """Documents belonging to departments the user has access to (+ global docs)."""
    is_admin = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == current_user.org_id,
            UserAccessDepartment.user_id == current_user.id,
            UserAccessDepartment.user_type == "ADMIN",
        )
        .first()
    )

    if is_admin:
        results = (
            db.query(OrgDocument.id)
            .filter(
                OrgDocument.org_id == current_user.org_id,
                OrgDocument.deleted_at.is_(None),
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
            OrgDocument.deleted_at.is_(None),
        )
    )

    global_docs = (
        db.query(OrgDocument.id)
        .filter(
            OrgDocument.org_id == current_user.org_id,
            OrgDocument.dept_id.is_(None),
            OrgDocument.deleted_at.is_(None),
        )
    )

    results = dept_docs.union(global_docs).all()
    return [r.id for r in results]



@traceable(name="get_suborg_by_document_id", project="core", metadata={"description": "Get suborganization by document ID"}, tags=["documents"])
def get_suborg_by_document_id(db: Session, document_id_list: list[int]):
    return (
        db.query(OrgDocument.id, OrgDocument.dept_id)
        .filter(OrgDocument.id.in_(document_id_list))
        .all()
    )


def get_selected_docs_ids_by_thread_id(db: Session, thread_id: int):
    docs = db.query(ChatThreads.document_ids).filter(ChatThreads.id == thread_id).first()
    return docs.document_ids if docs and docs.document_ids else []


# ─────────────────────────────────────────────────────────────
# Random / fallback provider selection (currently unused by routes,
# kept available for A/B or resiliency experiments)
# ─────────────────────────────────────────────────────────────
def get_random_llm_provider() -> str:
    """Return a random LLM provider."""
    return "openai" if random.random() < 0.5 else "gemini"


def invoke_chatbot_with_fallback(
    chatbot: Any,
    payload: Dict[str, Any],
    base_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """
    Picks a 50/50 provider. If the primary fails, falls back to the other.
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
            print(f" LLM failed [{provider}] => {repr(e)}. Trying fallback...", flush=True)
            time.sleep(0.2)

    raise HTTPException(
        status_code=502,
        detail=f"Both LLM providers failed. Last error: {repr(last_err)}",
    )


# ─────────────────────────────────────────────────────────────
# PII unmasking helper
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# JSON parsing helpers (LLM output can be malformed JSON)
# ─────────────────────────────────────────────────────────────
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
    Fix invalid JSON where inner quotes appear inside values of "content": "..."
    by escaping those inner quotes.
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
    """Full pipeline: extract JSON -> repair content quotes -> json.loads -> dict."""
    obj = extract_json_object(text)
    repaired = escape_quotes_inside_content_fields(obj)
    return json.loads(repaired)


def format_followups(output: dict) -> str:
    """
    Convert a suggested_follow_ups list into an HTML <li> string.
    Returns empty string if not present.
    """
    try:
        followups = output.get("suggested_follow_ups", {}).get("content", [])
        if not followups or not isinstance(followups, list):
            return ""
        return "".join([f"<li>{q}</li>" for q in followups if q])
    except Exception as e:
        print("Followup format error:", e)
        return ""


# ─────────────────────────────────────────────────────────────
# NDJSON streaming helpers
# ─────────────────────────────────────────────────────────────
@traceable(name="streaming_json_output", project="core", metadata={"description": "Create a JSON line for streaming"}, tags=["streaming","json","output","users","threads"])
def json_line(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


def strip_html(text: Any) -> str:
    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


def normalize_citation_links(links: list) -> list[dict]:
    result = []
    for item in links or []:
        if isinstance(item, dict):
            result.append(
                {
                    "filename": item.get("filename")
                    or item.get("file")
                    or item.get("name")
                    or item.get("title")
                    or "",
                    "link": item.get("link")
                    or item.get("url")
                    or item.get("href")
                    or item.get("pdf_url")
                    or "",
                }
            )
    return result


def stream_html_blocks(html_response: list):
    for item in html_response or []:
        if not isinstance(item, dict):
            continue

        tag = str(item.get("tag", "")).strip().strip("<>").replace("/", "")
        content = item.get("content", "")

        if not tag:
            continue

        if tag == "ul":
            yield json_line({"type": "block", "tag": "ul"})

            li_items = re.findall(
                r"<li[^>]*>(.*?)</li>",
                str(content or ""),
                flags=re.IGNORECASE | re.DOTALL,
            )

            for li in li_items:
                yield json_line({"type": "block", "tag": "li", "content": strip_html(li)})
                yield json_line({"type": "block", "tag": "/li"})

            yield json_line({"type": "block", "tag": "/ul"})
            continue

        yield json_line({"type": "block", "tag": tag, "content": str(content or "")})
        yield json_line({"type": "block", "tag": f"/{tag}"})


def stream_chat_response(
    message_id: int,
    html_response: list,
    links: list,
    suggested_questions: list,
):
    yield json_line({"type": "message_id", "id": str(message_id)})
    yield from stream_html_blocks(html_response)
    yield json_line({"type": "citations", "links": normalize_citation_links(links)})
    yield json_line({"type": "suggested", "questions": suggested_questions or []})
    yield json_line({"type": "done"})


def make_stream_response(
    message_id: int,
    html_response: list,
    links: list,
    suggested_questions: list,
):
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        stream_chat_response(
            message_id=message_id,
            html_response=html_response,
            links=links,
            suggested_questions=suggested_questions,
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def make_live_stream_response(process_func):
    from fastapi.responses import StreamingResponse

    def event_generator():
        yield json_line({"type": "stage", "value": "thinking"})
        try:
            result = process_func()
            yield from stream_chat_response(
                message_id=result["message_id"],
                html_response=result["html_response"],
                links=result["links"],
                suggested_questions=result["suggested_questions"],
            )
        except Exception as e:
            print("Streaming error:", repr(e))
            yield json_line({"type": "error", "message": "Something went wrong while generating the answer."})
            yield json_line({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────
# PDF citation retrieval (used by /qa/pdf/{id} and /qa/pdf-download/{id})
# ─────────────────────────────────────────────────────────────
def find_cached_citation_pdf(citation_id: str) -> Optional[Tuple[Path, str]]:
    """Return (path, pages_str) for a cached citation PDF on disk, if any."""
    matches = list(CITATION_DIR.glob(f"{citation_id}@*.pdf"))
    if not matches:
        return None
    pdf_path = matches[0]
    pages_str = pdf_path.stem.split("@", 1)[1]
    return pdf_path, pages_str


def wait_for_celery_pdf_job(job_id: str, max_wait: int = 5):
    """Poll a celery job for up to max_wait seconds and return it once resolved."""
    job = AsyncResult(job_id, app=celery_app)
    elapsed = 0

    while elapsed < max_wait:
        if job.status == "FAILURE":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Task {job_id} failed: {str(job.result)}",
            )
        if job.state == "SUCCESS":
            return job
        time.sleep(1)
        elapsed += 1

    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Document could not be shown. A problem occurred, please try again later.",
    )


def cache_citation_pdf_to_disk(citation_id: str, pages_str: str, pdf_bytes: bytes) -> None:
    try:
        pdf_path = CITATION_DIR / f"{citation_id}@{pages_str}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        print(f"PDF cached to disk at {pdf_path}")
    except Exception as e:
        print(f"Warning: could not write PDF to disk: {e}")