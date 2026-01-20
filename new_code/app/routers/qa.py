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

# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings, llm, BASE_DIR, retriever
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


def _can_read(db: Session, user: UserModel, org_id: int, dept_id: int) -> bool:
    # Org admin of same org can read everywhere in org
    if user.user_type == UserType.ADMIN and user.org_id == org_id:
        return True
    # Else must have read access on this department
    acc = (
        db.query(UserAccessDepartment)
        .filter(
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.dept_id == dept_id,
            UserAccessDepartment.user_id == user.id,
        )
        .first()
    )
    return bool(acc and acc.can_read)


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


class CitationItem(BaseModel):
    file: str = Field(..., description="Name of the PDF or source file used")
    document_id: str = Field(
        ..., description="Document id present in metadata with name document_id"
    )


class HtmlItem(BaseModel):
    tag: str = Field(
        ...,
        description=(
            "Semantic HTML tag chosen intentionally "
            "(e.g., h1, h2, p, ul, li, table, tr, th, td, code, pre)"
        ),
    )
    content: str = Field(
        ..., description=("Content for this tag. " "Must match the purpose of the tag.")
    )

class SuggestedFollowUpQuestions(BaseModel):
    """
    Always include exactly 3 short and relevant follow-up questions.
    Questions must relate to the same topic or documents.
    Do not assume information outside the provided context.
    Do not include answers.
    """

    tag: str = Field(
        default="ul",
        description="HTML container tag (example: ul, ol, div)"
    )
    content: str = Field(
        ...,
        min_items=3,
        max_items=3,
        description="Exactly 3 list items rendered as <li>"
    )
class RAGResponse(BaseModel):
    title: str = Field(..., description="Title of chat on basis of chat history")
    html_response: List[HtmlItem] = Field(
        ...,
        description=(
            "Frontend-ready UI blocks. "
            "LLM must design semantic structure, not just convert text. "
            "Choose tables, lists, headings where appropriate."
        ),
    )
    # response: str = Field(
    #     ...,
    #     description=(
    #         "llm response of user query"
    #     ),
    # )
    citation: List = Field(..., description="Files used for answering")
    is_context_availale: Literal["True", "False"] = Field(
        ..., description="Whether answer was generated from provided context"
    )
    suggested_follow_ups: SuggestedFollowUpQuestions = Field(..., description="Three relevant follow-up questions")


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


def chat_node(state: ChatState):
    messages = state["messages"][-1]
    context = state["context"]

    # response = llm.generate_stream_answer(
    #     context=context, query=messages
    # )

    # response = llm.generate_stream_answer_with_structure(
    #     context=context, query=messages, schema=HtmlItem
    # )

    response = llm.generate_answer_with_structure(
        context=context, query=messages, schema=RAGResponse
    )
    # print(response)
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
    
    print("chat_thread",type(chat_thread.description),(chat_thread.description))
    # thread not found → do nothing
    # if not chat_thread:
    #     print("true")
    #     return

    # 🔑 description already set → DO NOT overwrite
    if chat_thread.description :
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


from app.utils.celery_app import filter_sources_by_citation, celery_app
from celery.result import AsyncResult

# def filter_sources_by_citation(citations,org_id, sources):
#     # 1. Extract all filenames mentioned after "citation"
#     # Example fragment: "citation1: virat kohli 4.pdf"
#     # cited_files = re.findall(r"([\w\s\-()]+\.(?:pdf|PDF))", response_text)

#     # Normalize filenames
#     db = SessionLocal()
#     # current_user = get_current_active_user()
#     cited_files = [f.strip() for f in citations]
#     print(cited_files)
#     result = {}

#     # 2. Filter sources matching the cited filenames
#     for src in sources:
#         # print(src.metadata['filename'].lower())

#         filename = src['metadata'].get('filename')


#         if filename in cited_files:
#             document_id = src['metadata']["document_id"]
#             page_content = src['page_content']
#             print("document_id",document_id)
#             if document_id not in result:
#                  result[document_id] = {
#                     "filename": filename,
#                     "chunks": [],
#                     "link":None
#                 }

#             # Append page content to dict
#             result[document_id]["chunks"].append(page_content)
#     # print(result)

#     output=[]
#     for document_id,items in result.items():

#             my_bytes=_get_doc_by_id(db=db,org_id=org_id,document_id=document_id)
#             # docs=_get_doc_by_id(db,current_user,document_id)
#             # full_doc=""
#             # for doc in docs:
#             #      print("doc",doc)

#             #      full_doc+=doc
#             #full_doc=''.join(docs.page_content)
#             # print("my docs",docs)
#             # my_bytes=text_to_pdf_bytes(full_doc)
#             # print(my_bytes)
#             my_bytes=base64.b64decode(my_bytes[0])
#             obj=HighlightText()
#             my_bytes=obj.highlight_text(my_bytes,chunks=items['chunks'])
#             # with open('my_pdf.pdf',mode='wb') as f:
#             #       f.write(my_bytes)
#             # my_bytes=base64.b64encode(my_bytes).decode()
#             response=upload_pdf_to_github(file_name=items['filename'],owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer',pdf_bytes=my_bytes)
#             # print(response)

#             result[document_id]['link']=response['link']
#             output.append({"filename":result[document_id]['filename'],"link":result[document_id]['link'],"document_id":document_id})
#             # print(my_bytes)
#     # print("result",result)
#     return output


# @router.websocket("/query")
# async def stream_query(websocket:WebSocket, db: Session = Depends(get_db),current_user: UserModel = Depends(get_current_active_socket_user)
#     ):
#     await websocket.accept()

#     print(current_user.username)
#     data=await websocket.receive_json()

#     print("data",data)
#     user_allowed_dept_ids=list_user_access(user_id=current_user.id,org_id=data['org_id'],db=db)
#     print("all sub org ids",user_allowed_dept_ids)
#     if not user_allowed_dept_ids:
#            raise HTTPException(status_code=403, detail="No acces to any department")
#     allowed=_allowed_thread_id(db=db,current_user=current_user,t_id=data['selected'])
#     print("allowed thread",allowed)
#     if not allowed:
#        raise HTTPException(status_code=403, detail="Not valid thread for current user")
#     retrieval_list=[]
#     for dept_id in user_allowed_dept_ids:
#         vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{data['org_id']}\\dept\\{dept_id}")
#        # vectorStore.set_vector_store(docs=rows,embeddings=embeddings)

#         rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='mmr',top_n=data['top_k'])
#         # chunks=rv.invoke(input=data['q'])
#         # print("chunks",chunks)
#         retrieval_list.append(rv)
#         # docs=rv.get_relevant_document(query=query)
#         # docs_list.extend(docs)

#     rvm= EnsembleRetriever(retrievers=retrieval_list)
#     docs_list=await rvm.ainvoke(input=data['q'])

#     # print(docs_list)

#     # print("data",data)
#     query=data['q']
#     thread_id=data['selected']

#     with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
#          content=""
#          chatbot=builder(checkpointer=checkpointer)
#          config={"configurable":{"thread_id":thread_id}}
#         #  print("context",docs_list)

#         #  response =  chatbot.stream({"messages":query,"context":docs_list},config=config,stream_mode="messages")
#          response =  chatbot.stream({"messages":query,"context":docs_list},config=config)
#          for event in response:
#                for item in event.values():
#                     messages=item['messages']
#                     last_message = messages[-1]
#                     await websocket.send_text(json.dumps({"data":last_message.content,"type":"chunk"}))
#         #  for chunk in response:
#         #       print(chunk)
#         #       await websocket.send_text(json.dumps({"data":"data","type":"chunk"}))
#         #  for chunk,metadata in response :
#         #     #  print(chunk)
#         #      content+=chunk.content
#         #      await websocket.send_text(json.dumps({"data":chunk.content,"type":"chunk"}))
#             #  print(chunk)
#             #  if metadata:
#         #  print("chunks",docs_list)
#         #  print(content)
#         #  output=filter_sources_by_citation(db,current_user,content,sources=docs_list)
#         #  print("output",output)
#          await websocket.send_text(json.dumps({"data":"output","type":"metadata"}))
#             #        await websocket.send_text(json.dumps({"data":metadata,"extra":"metadata"}))
#     await websocket.close()
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
        db.query(UserModel)
        .filter(
            UserModel.id == user.id,
            UserAccessDepartment.org_id == org_id,
            UserAccessDepartment.user_type == UserType.ADMIN,
        )   
        .first()
    )
    return admin


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


# @router.get("/list_user_threads")
# def list_threads(db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user),

# ):

#    threads=db.query(ChatThreads).filter(ChatThreads.org_id==current_user.org_id,
#                                 ChatThreads.user_id==current_user.id).all()

#    threads=[{"thread_id":u.id,"title":u.description or ""} for u in threads]
#    threads.reverse()
#    print(threads)
#    return {"threads":threads}


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


@router.get("/document_content/{document_id}", summary="Get document content by id")
def get_document_content(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    document = (
        db.query(OrgDocument)
        .filter(
            
            OrgDocument.id == document_id,
            OrgDocument.org_id == current_user.org_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    pdf_bytes = base64.b64decode(document.file_bytes)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",headers={"Content-Disposition": f"inline"})
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

@router.get("/thread_id", summary="Requesting new Thread ID")
def ask_thread(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    user_thread = ChatThreads(
        user_id=current_user.id, org_id=current_user.org_id, description=""
    )
    db.add(user_thread)
    db.commit()

    db.flush()
    title = user_thread.description or ""

    return {"thread_id": user_thread.id, "title": title}


# @router.get("/chats/{thread_id}/messages")
# def get_chat_messages(
#     thread_id: int,
#     current_user:UserModel= Depends(get_current_active_user), # type: ignore
#     limit: int = Query(20, le=100),
#     cursor: Optional[int] = None,
#     db: Session = Depends(get_db),
# ):
#     query = db.query(ChatMessage).filter(
#         ChatMessage.user_id == current_user.id,
#         ChatMessage.org_id == current_user.org_id,
#         ChatMessage.thread_id == thread_id,
#     )

#     # If cursor exists → fetch older messages
#     if cursor:
#         query = query.filter(ChatMessage.id < cursor)

#     messages = (
#         query
#         .order_by(ChatMessage.id.desc())
#         .limit(limit + 1)   # +1 to check if more data exists
#         .all()
#     )

#     has_more = len(messages) > limit
#     messages = messages[:limit]

#     next_cursor = messages[-1].id if messages else None
#     response=[]
#     for msg in messages:
#          response.append({
#             "id":msg.id,
#             "query":msg.query,
#             "response":msg.response,

#          })
#     return {
#         "message": response,
#         "next_cursor": next_cursor,
#         "has_more": has_more
#     }
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


# def extract_content_from_html(html_response: List[HtmlItem]) -> str:
#     content = ""
#     for item in html_response:
#         content += item['content'] + " "
#     return content.strip()


def _is_org_exist(db: Session, org_id: int) -> bool:
    org = db.query(UserModel).filter(UserModel.org_id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")


from app.Rag.Masking import Masking, PiiMaskingState





@router.post("/ask/{thread_id}", summary="Ask a question over allowed departments")
def ask(
    thread_id: int,
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    s = time.monotonic()
    # if not _can_read(db, current_user, org_id, dept_id):
    #     raise HTTPException(status_code=403, detail="No read access to this department")
    _is_org_exist(db, org_id=data.org_id)
    print(data, thread_id, current_user.id, current_user.org_id)
    admin = _is_org_admin(db, current_user, data.org_id)
    if admin:
        user_allowed_dept_ids = _list_of_departments(db, current_user)
    else:
        user_allowed_dept_ids = list_user_access(
            user_id=current_user.id, org_id=data.org_id, db=db
        )
    print("all sub org ids", user_allowed_dept_ids,type(user_allowed_dept_ids))

    allowed = _allowed_thread_id(db=db, current_user=current_user, t_id=thread_id)
    print("allowed thread", allowed)

    if not allowed:
        raise HTTPException(status_code=403, detail="Not valid thread for current user")
    retrieval_list = []
    for dept_id in user_allowed_dept_ids:
        vectorStore = vectorManager.get_store(
            embeddings=embeddings,
            persist_dir=f"{BASE_DIR}/{data.org_id}/dept/{dept_id}",
        )
        rv = retriever.get_retreiver(
            vector_store=vectorStore.get_vector_store(),
            search_type="similarity",
            top_n=data.top_k,
        )
        retrieval_list.append(rv)
    vectorStore = vectorManager.get_store(
        embeddings=embeddings, persist_dir=f"{BASE_DIR}/{data.org_id}"
    )
    rv = retriever.get_retreiver(
        vector_store=vectorStore.get_vector_store(),
        search_type="similarity",
        top_n=data.top_k
    )
    
    # rv = retriever.get_retreiver_by_document_id(
    #     vector_store=vectorStore.get_vector_store(),
    #     search_type="similarity",
    #     top_n=data.top_k,
    #     document_id=user_allowed_dept_ids[3],
    # )
    # user_allowed_dept_ids.append('global')
    # rv = retriever.get_retreiver_by_department_ids(
    #     vector_store=vectorStore.get_vector_store(),
    #     search_type="similarity",
    #     top_n=data.top_k,
    #     dept_ids=user_allowed_dept_ids
    # )
    retrieval_list.append(rv)
    print("test time", time.monotonic() - s)
    rvm = EnsembleRetriever(retrievers=retrieval_list)
    docs_list = rvm.invoke(input=data.q)
 
    print("context extracton time", time.monotonic() - s)
    
    ss = time.monotonic()
    masking_state = PiiMaskingState()
    masking = Masking()
    masked_docs = masking.mask_texts(docs_list, masking_state)
    print("masking time", time.monotonic() - ss)
    print("org_docs_list", docs_list)
    # print("mask_docs_list", masked_docs)
    
    s1 = time.monotonic()
    with PyMySQLSaver.from_conn_string(
        conn_string=os.getenv("CHAT_HISTORY_DATABASE_URL")
    ) as checkpointer:
        chatbot = builder(checkpointer=checkpointer)
        print(type(thread_id), thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        answer = chatbot.invoke(
            {"messages": data.q, "context": docs_list}, config=config
        )
    #  print("answer",answer)

    siz = sys.getsizeof(rvm)
    print("output",answer['messages'][-1].content)
    output = json.loads(answer["messages"][-1].content)
    e = time.monotonic()
    # print("response time",e-s)
    # print("output",output)
    # s1=time.monotonic()
    serialize_doc_list = documents_to_dicts(docs_list)
    print("output citation",output['citation'])
    my_link=filter_sources_by_citation(citations=output['citation'],org_id=current_user.org_id,sources=serialize_doc_list)

    # print(my_link)
    # links = filter_sources_by_citation.delay(
    #     citations=output["citation"],
    #     org_id=current_user.org_id,
    #     sources=serialize_doc_list,
    # )
    # # links=q.enqueue(filter_sources_by_citation,citations=output['citation'],org_id=current_user.org_id,sources=serialize_doc_list)
    # # links=q.enqueue(hello,2,3)
    # print("links",links.id)
    # bt.add_task(create_link_for_citation,db,current_user,citations=output['citation'],sources=docs_list)
    print("time1", time.monotonic() - s1)
    llm_response = extract_text_only_from_html(output["html_response"])
    # print(type(llm_response),llm_response)
    if output["is_context_availale"] == "True":

        chat_message = ChatMessage(
            query=data.q,
            response=llm_response,
            thread_id=thread_id,
            user_id=current_user.id,
            org_id=data.org_id,
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
            user_id=current_user.id,
            org_id=data.org_id,
            tokens=answer["total_token"],
            citation=my_link,
            html_response=output["html_response"],  
            unanswer_query=True,
        )
    db.add(chat_message)

    # 
    print(type(thread_id),type(data.org_id),type(output["title"]))
    update_chat_thread_description(
        db, data.org_id, current_user.id, thread_id, description=output["title"]
    )
    db.commit()
    output['html_response'].append({
        "tag":"h1",
        "content":"Suggested Follow Up Questions"
    })
    output['html_response'].append(output['suggested_follow_ups'])
    # cit=create_link_for_citation(db,current_user,citations=output['citation'],sources=docs_list)
    print("model response time", time.monotonic() - s1)
    print("total time", time.monotonic() - s)
    # print(cit)
    return {
        "query_time": e - s,
        "html_response": output["html_response"],
        "response": llm_response,
        "citations": output["citation"],
        "total_token": answer["total_token"],
     
        "links": my_link,
    }
    # return {"query_time":e-s,"response":output['response'],"html_response":output['html_response'],"citations":output['citation'],"total_token":answer['total_token'],"is_context_available":output['is_context_availale']}
    # return {"query_time":e-s,"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list,"size":siz}


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
        ChatMessage.user_id == current_user.id,
        ChatMessage.org_id == current_user.org_id,
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


# @router.get("/chat_history/{thread_id}",summary="Get chat history by thread id")
# def get_chat_history(
#     thread_id:int,
#     db: Session = Depends(get_db),
#     current_user: UserModel = Depends(get_current_active_user)):
#     print("thread id",thread_id)
#     print("current user",current_user.id)
#     print("current org",current_user.org_id)
#     chat_history=db.query(ChatMessage).filter(ChatMessage.thread_id==thread_id,
#                                 ChatMessage.user_id==current_user.id,ChatMessage.org_id==current_user.org_id).all()
#     output=[]
#     for chat in chat_history:
#          print(chat.id)
#          output.append({
#             "id":chat.id,
#             "query":chat.query,
#             "response":chat.response,
#             "tokens":chat.tokens,
#             "citation":chat.citation,
#             "created_at":chat.created_at
#          })
#     return {"chat_history":output}


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
            persist_dir=f"{BASE_DIR}/{data.org_id}",
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
