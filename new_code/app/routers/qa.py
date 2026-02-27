# app/routers/qa.py

from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
from app.models.doc_models import DocChunk  #  from doc_models

# from app.models.org_document_model import OrgDocument       #  from org_document_model
from app.models.doc_models import OrgDocument, DocChunk
from app.utils.embeddings import embed_texts
from app.models.chat_thread_model import ChatThreads
from fastapi.responses import StreamingResponse
from langchain_community.retrievers import BM25Retriever

# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings, llm_openai,llm_gemini, BASE_DIR, retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
from langchain_classic.text_splitter import CharacterTextSplitter
from app.Rag.HighlightText import HighlightText
from app.models.chat_messages_model import ChatMessage
from app.models.doc_embedding_model import DocEmbedding

router = APIRouter(prefix="/qa", tags=["qa"])
# _faiss = FaissManager(dim=get_embed_dim())
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any
from rq import Queue
from redis import Redis
import time
from app.Rag.utils import extract_text_only_from_html

redis_conn = Redis()


# q = Queue(connection=redis_conn)
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
    # if current_user.user_type != UserType.ADMIN:
    #     raise HTTPException(status_code=403, detail="Only org admins can view access")

    # user = _ensure_user_exists(db, user_id)
    # if user.org_id != current_user.org_id:
    #     raise HTTPException(status_code=403, detail="User is not in your organization")

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
    """ """
    # if current_user.user_type != UserType.ADMIN:
    #     raise HTTPException(status_code=403, detail="Only org admins can view access")

    # user = _ensure_user_exists(db, user_id)
    # if user.org_id != current_user.org_id:
    #     raise HTTPException(status_code=403, detail="User is not in your organization")

    rows = (
        db.query(ChatThreads)
        .filter(
            ChatThreads.org_id == org_id,
            ChatThreads.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r) for r in rows]


# class CitationItem(BaseModel):
#     file: str = Field(..., description="Name of the PDF or source file used")
#     document_id: str = Field(
#         ..., description="Document id present in metadata with name document_id"
#     )


# class HtmlItem(BaseModel):
#     tag: str = Field(
#         ...,
#         description=(
#             "Semantic HTML tag chosen intentionally "
#             "(e.g., h1, h2, p, ul, li, table, tr, th, td, code, pre)"
#         ),
#     )
#     content: str = Field(
#         ..., description=("Content for this tag. " "Must match the purpose of the tag.")
#     )

# class SuggestedFollowUpQuestions(BaseModel):
#     """
#     Always include exactly 3 short and relevant follow-up questions.
#     Questions must relate to the same topic or documents.
#     Do not assume information outside the provided context.
#     Do not include answers.
#     """

#     tag: str = Field(
#         default="ul",
#         description="HTML container tag (example: ul, ol, div)"
#     )
#     content: str = Field(
#         ...,
#         min_items=3,
#         max_items=3,
#         description="Exactly 3 list items rendered as <li>"
#     )
# class RAGResponse(BaseModel):
#     title: str = Field(..., description="Title on basis of only user query it doesn't depend on context")
#     html_response: List[HtmlItem] = Field(
#         ...,
#         description=(
#             "Frontend-ready UI blocks. "
#             "LLM must design semantic structure, not just convert text. "
#             "Choose tables, lists, headings where appropriate."
#         ),
#     )
#     # response: str = Field(
#     #     ...,
#     #     description=(
#     #         "llm response of user query"
#     #     ),
#     # )
#     citation: List = Field(..., description="Files used for answering")
#     is_context_availale: Literal["True", "False"] = Field(
#         ..., description="Whether answer was generated from provided context"
#     )
#     suggested_follow_ups: SuggestedFollowUpQuestions = Field(..., description="ul tag must be there ,Three relevant follow-up questions")



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
    Must relate to based on query ,response and document mix.
    Do NOT include answers.
    """

    tag:  Literal["ul"] = Field(
        
        description="HTML container ul",
    )

    content: str = Field(
        ...,
        
        description="content like '<li>Question...</li>'   Return ONE <ul> block containing multiple <li> items.Do not create multiple ul tags.",
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

    # IMPORTANT: must be typed list (fixes your schema error)
    # citation: List[CitationItem] = Field(
    #     default_factory=list,
    #     description="List of files used for answering",
    # )
    citation: List = Field(..., description="Files used for answering")
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
    provider:str



def chat_node(state: ChatState):
    # messages = state["messages"][-1]
    messages = state["messages"]
    context = state["context"]
    provider=state.get("provider",None)


    


    # response = llm_openai.generate_stream_answer(
    #     context=context, query=messages
    # )

    # response = llm_openai.generate_stream_answer_with_structure(
    #     context=context, query=messages, schema=HtmlItem
    # )
    # response=""
    if provider=='openai':
       response = llm_openai.generate_answer_with_structure(
        context=context, query=messages, schema=RAGResponse
        )
    elif provider=='gemini':
        response = llm_gemini.generate_answer_with_structure(
        context=context, query=messages, schema=RAGResponse
        )
        
    # response = llm_openai.generate_answer_with_structure(
    #     context=context, query=messages, schema=RAGResponse
    #     )
    # print(response)
    with open(f"{provider}_chat_node.txt", "w") as f: 
       f.write("messages:\n")
       for msg in messages:
           if isinstance(msg, HumanMessage):
               f.write(f"Human: {msg.content}\n")
           elif isinstance(msg, AIMessage):
               f.write(f"AI: {msg.content}\n")
    total_token = response.usage_metadata["total_tokens"]
    return {"messages": [response], "total_token": total_token}


# checkpointer = InMemorySaver()

# checkpointer
# checkpointer.
# graph = StateGraph(ChatState)
# graph.add_node("chat_node", chat_node)
# graph.add_edge(START, "chat_node")
# graph.add_edge("chat_node", END)

# builder = graph.compile()

builder = (
    StateGraph(ChatState)
    .add_node("chat_node", chat_node)
    .add_edge(START, "chat_node")
    .add_edge("chat_node", END)
    .compile
)

with PyMySQLSaver.from_conn_string(
    conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
) as cp:

    cp.setup()


def _get_thread_provider(db: Session,current_user, thread_id: int) -> str:
    thread = db.query(ChatThreads).filter(        ChatThreads.org_id == current_user.org_id,
        ChatThreads.user_id == current_user.id,ChatThreads.id == thread_id).first()
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
    db: Session,
    org_id: int,
    user_id: int,
    chat_thread_id: int,
    description: str
) -> None:
    print(org_id,user_id,chat_thread_id,description)
    chat_thread = db.query(ChatThreads).filter(
            ChatThreads.id == chat_thread_id,
            ChatThreads.user_id==user_id,
            ChatThreads.org_id == org_id
        ).first()
    
    # print("chat_thread",type(chat_thread.description),(chat_thread.description))
    # thread not found → do nothing
    # if not chat_thread:
    #     print("true")
    #     return

    #  description already set → DO NOT overwrite
    if chat_thread and chat_thread.description :
        return
    # print("ggg",description)
    # only NULL → update
    chat_thread.description = description
    db.add(chat_thread)
    # print("updated description",chat_thread.description)
    db.commit()

import time
import re
import base64
from app.Rag.PdfUploader import upload_pdf_to_github
from app.Rag.TexttoPdf import text_to_pdf_bytes


from app.utils.celery_app import  celery_app ,filter_sources_by_citation
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


# def _is_org_admin(db: Session, user: UserModel, org_id: int) -> bool:
#     admin = db.query(UserModel).filter(
#             UserModel.id == user.id,
#             UserAccessDepartment.org_id == org_id,
#             UserAccessDepartment.user_type == UserType.ADMIN,
#         )   .first()
    
#     for adm in  admin:
#         print("admin",adm.id,adm.org_id,adm.user_type)
#     return admin
from app.models.user_access_department_model import UserAccessDepartment, UserType

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
):
    query = db.query(ChatThreads.id, ChatThreads.description).filter(
        ChatThreads.org_id == current_user.org_id,
        ChatThreads.user_id == current_user.id,
    )

    # If cursor exists → fetch older messages
    if next_id:
        query = query.filter(ChatThreads.id < next_id)

    messages = (
        query.order_by(ChatThreads.id.desc())
        .limit(limit + 1)  # +1 to check if more data exists
        .all()
    )
    # print(messages)

    has_more = len(messages) > limit
    messages = messages[:limit]
    print(messages)
    new_next_id = messages[-1].id if messages else None
    response = []
    for msg in messages:
        response.append(
            {
                "thread_id": msg.id,
                "title": msg.description or "",
            }
        )
    return {"messages": response, "next_id": new_next_id, "has_more": has_more}


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


    # return {

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
        db.query(ChatThreads).order_by(ChatThreads.id.desc()).filter(

            ChatThreads.org_id == current_user.org_id,
            ChatThreads.user_id == current_user.id,).first()
    )

    if not thread or not thread.llm_provider:
        # Default bootstrap behavior
        return LLMProvider.OPENAI

    current = thread.llm_provider.lower()

    if current == LLMProvider.OPENAI:
        return LLMProvider.GEMINI

    if current == LLMProvider.GEMINI:
        return LLMProvider.OPENAI

    # Safety fallback
    return LLMProvider.OPENAI


@router.get("/thread_id", summary="Requesting new Thread ID")
def ask_thread(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):  
    
    # provider=get_random_llm_provider()
    next_provider = get_next_llm_provider(db, current_user)
    user_thread = ChatThreads(
        user_id=current_user.id, org_id=current_user.org_id, description="",llm_provider=next_provider
    )
    db.add(user_thread)
    db.commit()

    db.flush()
    title = user_thread.description or ""

    return {"thread_id": user_thread.id, "title": title}


from fastapi.responses import StreamingResponse
import io
from app.models.user_access_department_model import UserAccessDepartment 
def _check_user_access_to_document(db: Session, current_user: UserModel, document_id: int):
    isadmin=db.query(UserAccessDepartment).filter(
        UserAccessDepartment.user_id==current_user.id,
        UserAccessDepartment.user_type==UserType.ADMIN
    ).first()
    if isadmin:
        return
    access=db.query(UserAccessDepartment).join(
        OrgDocument,
        UserAccessDepartment.dept_id == OrgDocument.dept_id
    ).filter(
        UserAccessDepartment.user_id == current_user.id,
        OrgDocument.id == document_id
    ).first()
    if not access:
        raise HTTPException(status_code=403, detail="No access to this document")


@router.get("/pdf/{id}", summary="Get citated link by id")
def cited(db: Session = Depends(get_db), current_user: UserModel=Depends(get_current_active_user), id: str = ""):
    job = AsyncResult(id, app=celery_app)
    while True:
        if job.status == "FAILURE":
          raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process the citation links.",
          )

        if job.state == "SUCCESS":
            break

        # ⏳ Keep connection open, do NOTHING
        time.sleep(1)
    if job.status == "SUCCESS":
        if job.result:
            doc_id=job.result['document_id']
            print("doc_id",doc_id)
            _check_user_access_to_document(db=db, current_user=current_user, document_id=doc_id)
            pdf_bytes=base64.b64decode(job.result['pdf'])
        return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",headers={"Content-Disposition": f"inline"})
    # return {
    #     "id": id,
    #     "status": job.status,
    #     "result": job.result,
    # }


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

import time
import random
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
# router = APIRouter()
from app.services.embedding_token import dept_license_and_token_update , user_license_and_token_update
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
    fallback = "gemini" if primary == "openai" else "gemini"

    last_err: Exception | None = None
    for provider in (primary, fallback):
        try:
            cfg = dict(base_config or {})
            cfg.setdefault("configurable", {})
            cfg["configurable"]["llm_provider"] = provider  # routing key for graph
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

# def unmask_html_list(html_list: list) -> list:
#     state=PiiMaskingState()
#     masking = Masking()
#     for item in html_list:
#         if isinstance(item, dict) and "content" in item:
#             item["content"] = masking.unmask_text(item["content"], state=state)
#     return html_list


#  - uses the same state that was built during masking
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

def safe_json_from_llm(text: str):
    s = text.strip()

    # remove code fences
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    # extract the first full JSON object (handles extra text before/after)
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")

    candidate = s[start:end+1].strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        # show nearby characters where it broke
        left = max(0, e.pos - 200)
        right = min(len(candidate), e.pos + 200)
        ctx = candidate[left:right]
        raise ValueError(
            f"Invalid JSON: {e}\n--- context around pos {e.pos} ---\n{ctx}\n-------------------------------"
        ) from e




import json

def extract_json_object(text: str) -> str:
    """Extract the outermost JSON object from a bigger string."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in text")
    return text[start:end+1]


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
        # returns True if s[pos] is escaped by odd number of backslashes before it
        backslashes = 0
        j = pos - 1
        while j >= 0 and s[j] == "\\":
            backslashes += 1
            j -= 1
        return (backslashes % 2) == 1

    while i < n:
        # detect `"content"` key
        if s.startswith('"content"', i):
            out.append('"content"')
            i += len('"content"')

            # copy whitespace + colon
            while i < n and s[i].isspace():
                out.append(s[i]); i += 1
            if i < n and s[i] == ":":
                out.append(":"); i += 1
            while i < n and s[i].isspace():
                out.append(s[i]); i += 1

            # now should be opening quote for the string value
            if i < n and s[i] == '"':
                out.append('"')
                i += 1

                # inside the content string until we reach its real closing quote
                while i < n:
                    ch = s[i]

                    if ch == '"' and not is_escaped(i):
                        # This quote could be:
                        # 1) the real end of the content string  -> followed by optional spaces then , or }
                        # 2) an inner quote like "gap"           -> should be escaped
                        j = i + 1
                        while j < n and s[j].isspace():
                            j += 1
                        if j < n and s[j] in [",", "}"]:
                            # real closing quote
                            out.append('"')
                            i += 1
                            break
                        else:
                            # inner quote in the content -> escape it
                            out.append('\\"')
                            i += 1
                            continue

                    out.append(ch)
                    i += 1

                continue

        # normal copy
        out.append(s[i])
        i += 1

    return "".join(out)


def parse_llm_like_json(text: str) -> dict:
    """Full pipeline: extract JSON -> repair content quotes -> json.loads -> dict"""
    obj = extract_json_object(text)
    repaired = escape_quotes_inside_content_fields(obj)
    return json.loads(repaired)





# @router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
# def ask(
#     thread_id: int,
#     data: AskRequest,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),
# ):
#     s = time.monotonic()
#     # if not _can_read(db, current_user, org_id, dept_id):
#     #     raise HTTPException(status_code=403, detail="No read access to this department")
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
#     print("all sub org ids", user_allowed_dept_ids,type(user_allowed_dept_ids))

#     allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
#     print("allowed thread", allowed)

#     if not allowed:
#         raise HTTPException(status_code=403, detail="Not valid thread for current user")
#     retrieval_list = []
#     # for dept_id in user_allowed_dept_ids:
#     #     vectorStore = vectorManager.get_store(
#     #         embeddings=embeddings,
#     #         persist_dir=f"{BASE_DIR}/{data.org_id}/dept/{dept_id}",
#     #     )
#     #     rv = retriever.get_retreiver(
#     #         vector_store=vectorStore.get_vector_store(),
#     #         search_type="similarity",
#     #         top_n=data.top_k,
#     #     )
#     #     retrieval_list.append(rv)
#     vectorStore = vectorManager.get_store(
#         embeddings=embeddings, persist_dir=f"{BASE_DIR}/{current_user.org_id}"
#     )
#     # rv = retriever.get_retreiver(
#     #     vector_store=vectorStore.get_vector_store(),
#     #     search_type="similarity",
#     #     top_n=data.top_k
#     # )
    
#     # rv = retriever.get_retreiver_by_document_id(
#     #     vector_store=vectorStore.get_vector_store(),
#     #     search_type="similarity",
#     #     top_n=data.top_k,
#     #     document_id=user_allowed_dept_ids[3],
#     # )
#     if admin:
#         rv = retriever.get_retreiver(
#         vector_store=vectorStore.get_vector_store(),
#         search_type="similarity",
#         top_n=data.top_k
#     )
#     else:
#       user_allowed_dept_ids.append("global")
#       rv = retriever.get_retreiver_by_department_ids(
#         vector_store=vectorStore.get_vector_store(),
#         search_type="similarity",
#         top_n=data.top_k,
#         dept_ids=user_allowed_dept_ids
#       )
#     retrieval_list.append(rv)
#     print("test time", time.monotonic() - s)
#     rvm = EnsembleRetriever(retrievers=retrieval_list)
#     docs_list = rvm.invoke(input=data.q)
 
#     print("context extracton time", time.monotonic() - s)
    
#     ss = time.monotonic()
#     masking_state = PiiMaskingState()
#     masking = Masking()
    
    
#     masked_docs = masking.mask_texts(docs_list, masking_state)
#     print("masking time", time.monotonic() - ss)
#     # print("org_docs_list", docs_list)
#     # print("mask_docs_list", masked_docs)
    
#     s1 = time.monotonic()
#     with PyMySQLSaver.from_conn_string(
#         conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
#     ) as checkpointer:
#         chatbot = builder(checkpointer=checkpointer)
#         print(type(thread_id), thread_id)
#         config = {"configurable": {"thread_id": thread_id}}
#         provider=_get_thread_provider(db,current_user, thread_id)
#         answer = chatbot.invoke(
#             {"messages": data.q, "context": masked_docs,"provider":provider}, config=config
#         )
#     #  print("answer",answer)

#     siz = sys.getsizeof(rvm)
#     # print("output",answer['messages'][-1].content)
#     import json, re

#     # print("output", answer['messages'][-1].content)
#     res = answer['messages'][-1].content
#     print("type of res", type(res))

    
#     # output = safe_json_from_llm(res)

#     e = time.monotonic()


#     # res=answer['messages'][-1].content
#     res=res.replace("```json","").replace("```","")
#     print("output after removing code fence",res)
#     output=parse_llm_like_json(res)
#     # output = json.loads(res)
#     e = time.monotonic()
#     # print("response time",e-s)
#     # print("output",output)
#     print("masked html_response",output['html_response'])

#     # s1=time.monotonic()
#     serialize_doc_list = documents_to_dicts(docs_list)
#     print("output citation",output['citation'])
#     my_link=filter_sources_by_citation(citations=output['citation'],org_id=current_user.org_id,sources=serialize_doc_list)
#     output['html_response']=unmask_html_list(output['html_response'])
#     print("unmasked html_response",output['html_response'])
#     print("time1", time.monotonic() - s1)
     
#     llm_response = extract_text_only_from_html(output["html_response"])
#     # print(type(llm_response),llm_response)
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

#     # 
#     # print(type(thread_id),type(data.org_id),type(output["title"]))
#     update_chat_thread_description(
#         db, current_user.org_id, current_user.id, thread_id, description=output["title"]
#     )
#     db.commit()
#     output['html_response'].append({
#         "tag":"h1",
#         "content":"Suggested Follow Up Questions"
#     })
#     output['html_response'].append(output['suggested_follow_ups'])
#     # dept_id=docs_list[0].metadata.get("dept_id",None)
#     # if dept_id is not None:
#     #     if dept_id=='global':
#     #         dept_id=0
  
#     # user_license_and_token_update(
#     #     db=db,
#     #     user_id=current_user.id,
#     #     dept_id=dept_id,
#     #     tokens_used=answer["total_token"],
     
#     # )
#     # dept_license_and_token_update(
#     #     db=db,
#     #     dept_id=dept_id ,
#     #     org_id=current_user.org_id,
#     #     tokens_used=answer["total_token"],
#     # )
#     # cit=create_link_for_citation(db,current_user,citations=output['citation'],sources=docs_list)
#     print("model response time", time.monotonic() - s1)
#     print("total time", time.monotonic() - s)
#     # print(cit)
#     return {
#         "query_time": e - s,
#         "html_response": output["html_response"],
#         "response": llm_response,
#         "citations": output["citation"],
#         "total_token": answer["total_token"],
     
#         "links": my_link,
#     }
#     # return {"query_time":e-s,"response":output['response'],"html_response":output['html_response'],"citations":output['citation'],"total_token":answer['total_token'],"is_context_available":output['is_context_availale']}
#     # return {"query_time":e-s,"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list,"size":siz}

# def _build_bm25_retriever(docs_list: list, top_k: int) -> BM25Retriever:
#     """
#     Build a BM25 keyword retriever from already-retrieved vector docs.
#     This helps surface formula chunks that semantic search misses because
#     math symbols (∑, α, F1) embed poorly.
#     """
#     bm25 = BM25Retriever.from_documents(docs_list)
#     bm25.k = top_k
#     return bm25

def _build_bm25_retriever(docs_list: list, top_k: int = 5) -> BM25Retriever:
    """
    Build a BM25 keyword retriever from already-retrieved vector docs.
    top_k is hardcoded to 5 — wide retrieval via vector search (top_n=20),
    but only 5 best chunks reach the LLM to control cost.
    """
    bm25 = BM25Retriever.from_documents(docs_list)
    bm25.k = top_k  # controls how many chunks go to EnsembleRetriever → LLM
    return bm25









from langchain_core.messages import HumanMessage  

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

    admin = _is_org_admin(db, current_user, current_user.org_id)
    if admin:
        print("is admin ?")
        user_allowed_dept_ids = _list_of_departments(db, current_user)
    else:
        user_allowed_dept_ids = list_user_access(
            user_id=current_user.id, org_id=current_user.org_id, db=db
        )
    print("all sub org ids", user_allowed_dept_ids, type(user_allowed_dept_ids))

    allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
    print("allowed thread", allowed)

    if not allowed:
        raise HTTPException(status_code=403, detail="Not valid thread for current user")

    retrieval_list = []
    vectorStore = vectorManager.get_store(
        embeddings=embeddings, persist_dir=f"{BASE_DIR}/{current_user.org_id}"
    )

    if admin:
        rv = retriever.get_retreiver(
            vector_store=vectorStore.get_vector_store(),
            search_type="similarity",
            top_n=data.top_k
        )
    else:
        user_allowed_dept_ids.append("global")
        rv = retriever.get_retreiver_by_department_ids(
            vector_store=vectorStore.get_vector_store(),
            search_type="similarity",
            top_n=data.top_k,
            dept_ids=user_allowed_dept_ids
        )

    retrieval_list.append(rv)
    print("test time", time.monotonic() - s)




    
    
    try:
        candidate_docs = rv.invoke(data.q)  # retrieves top_k=20 from swagger

        if candidate_docs:
            bm25_retriever = _build_bm25_retriever(
                candidate_docs,
                top_k=5   # ← always 5 to LLM, regardless of data.top_k
            )
            retrieval_list.append(bm25_retriever)
            print(f"BM25 retriever built with {len(candidate_docs)} candidate docs, sending 5 to LLM")
    except Exception as e:
        print(f"BM25 build skipped: {e}")
    # try:
    #     candidate_docs = rv.invoke(data.q)

    #     if candidate_docs:
    #         bm25_retriever = _build_bm25_retriever(candidate_docs, top_k=min(data.top_k, len(candidate_docs)))
    #         retrieval_list.append(bm25_retriever)
    #         print(f"BM25 retriever built with {len(candidate_docs)} candidate docs")
    # except Exception as e:
    #     # BM25 is best-effort — never block the main flow
    #     print(f"BM25 build skipped: {e}")
    # if len(retrieval_list) > 1:
    #     rvm = EnsembleRetriever(
    #         retrievers=retrieval_list,
    #         weights=[0.6, 0.4],   # 60% semantic, 40% keyword/BM25
    #     )
    # else:

    rvm = EnsembleRetriever(retrievers=retrieval_list)
    docs_list = rvm.invoke(input=data.q)

    # print("=== RETRIEVED CHUNKS ===")
    # for i, doc in enumerate(docs_list):
    #     print(f"\n--- Chunk {i+1} ---")
    #     print(doc.page_content[:500])
    #     print("Metadata:", doc.metadata)
    # print("=== END CHUNKS ===")
    
    

   

    print("context extracton time", time.monotonic() - s)

    ss = time.monotonic()
    masking_state = PiiMaskingState()
    masking = Masking()

    masked_docs = masking.mask_texts(docs_list, masking_state)



    print("=== CHUNKS SENT TO LLM ===")
    for i, doc in enumerate(masked_docs):
        print(f"\n--- Chunk {i+1} ---")
        print(doc.page_content)
    print("=== END ===")

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

        #  Send current query as HumanMessage so LangGraph appends to messages history
        answer = chatbot.invoke(
            {
                "messages": [HumanMessage(content=data.q)],  # IMPORTANT
                "context": masked_docs,
                #   "context": docs_list,
                "provider": provider,
            },
            config=config
        )
        # print
    

    siz = sys.getsizeof(rvm)
    import json, re

    res = answer['messages'][-1].content
    print("type of res", type(res))

    e = time.monotonic()

    res = res.replace("```json", "").replace("```", "")
    print("output after removing code fence", res)

    output = parse_llm_like_json(res)

    e = time.monotonic()
    print("masked html_response", output['html_response'])

    serialize_doc_list = documents_to_dicts(docs_list)
    print("output citation", output['citation'])

    my_link = filter_sources_by_citation(
        citations=output['citation'],
        org_id=current_user.org_id,
        sources=serialize_doc_list
    )

    # output['html_response'] = unmask_html_list(output['html_response'])
    # print("unmasked html_response", output['html_response'])
    output['html_response'] = unmask_html_list(output['html_response'], state=masking_state)
    print("unmasked html_response", output['html_response'])
    print("time1", time.monotonic() - s1)

    llm_response = extract_text_only_from_html(output["html_response"])

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

    update_chat_thread_description(
        db, current_user.org_id, current_user.id, thread_id, description=output["title"]
    )
    db.commit()

    output['html_response'].append({
        "tag": "h1",
        "content": "Suggested Follow Up Questions"
    })
    output['html_response'].append(output['suggested_follow_ups'])

    print("model response time", time.monotonic() - s1)
    print("total time", time.monotonic() - s)

    return {
        "query_time": e - s,
        "html_response": output["html_response"],
        "response": llm_response,
        "citations": output["citation"],
        "total_token": answer["total_token"],
        "links": my_link,
        "source":docs_list,
        "raw_answer":answer
         }
     
    return {"query_time":e-s,"response":output['response'],"html_response":output['html_response'],"citations":output['citation'],"total_token":answer['total_token'],"is_context_available":output['is_context_availale']}
    return {"query_time":e-s,"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list,"size":siz}





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
        # ChatMessage.user_id == current_user.id,
        # ChatMessage.org_id == current_user.org_id,
        ChatMessage.thread_id == thread_id,
    )

    # If cursor exists → fetch older messages
    if next_id:
        query = query.filter(ChatMessage.id < next_id)

    messages = (
        query.order_by(ChatMessage.id.desc())
        .limit(limit + 1)  # +1 to check if more data exists
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



@router.post(
    "/ask/{thread_id}/documents",
    summary="Ask a question over allowed departments over perticular document",
)
def ask_by_id(
    thread_id: int,
    data: AskRequestOnDocument,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    s = time.monotonic()
    # if not _can_read(db, current_user, org_id, dept_id):
    #     raise HTTPException(status_code=403, detail="No read access to this department")
    print(data.document_id, thread_id)
    doc_suborg = _get_suborg_by_document_id(db, data.document_id)
    print(doc_suborg)
    if not doc_suborg:
        raise HTTPException(
            status_code=403, detail="No departmetn found for given document"
        )
    retrieval_list = []

    # user_allowed_dept_ids=list_user_access(user_id=data.user_id,org_id=data.org_id,db=db)
    # user_allowed_dept_ids=list_user_access(user_id=current_user.id,org_id=data.org_id,db=db)
    # print("all sub org ids",user_allowed_dept_ids)
    # if not user_allowed_dept_ids:
    #        raise HTTPException(status_code=403, detail="No acces to any department")
    allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
    print("allowed thread", allowed)
    if not allowed:
        raise HTTPException(status_code=403, detail="Not valid thread for current user")
    # for document_id, dept_id in doc_suborg:

    #     vectorStore = vectorManager.get_store(
    #         embeddings=embeddings,
    #         persist_dir=f"{BASE_DIR}/{data.org_id}/dept/{dept_id}",
    #     )
    #     rv = retriever.get_retreiver_by_document_id(
    #         vector_store=vectorStore.get_vector_store(), 
    #         search_type="similarity",
    #         top_n=data.top_k,
    #         document_id=document_id,
    #     )
    #     retrieval_list.append(rv)
    vectorStore = vectorManager.get_store(
            embeddings=embeddings,
            persist_dir=f"{BASE_DIR}/{current_user.org_id}",
        )
    rv = retriever.get_retreiver_by_document_id(
            vector_store=vectorStore.get_vector_store(),
            search_type="similarity",
            top_n=data.top_k,
            document_ids=data.document_id,
        )
    # rvm = EnsembleRetriever(retrievers=[rv])
    docs_list = rv.invoke(input=data.q)

    # print("docs_list", docs_list)
    with PyMySQLSaver.from_conn_string(
        conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
    ) as checkpointer:
        chatbot = builder(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        answer = chatbot.invoke(
            {"messages": data.q, "context": docs_list}, config=config
        )

    e = time.monotonic()
    siz = sys.getsizeof(rv)
    return {
        "query_time": e - s,
        "response": answer["messages"][-1].content,
        "total_token": answer["total_token"],
        "sources": docs_list,
    }
