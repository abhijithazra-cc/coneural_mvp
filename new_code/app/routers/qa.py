# app/routers/qa.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query,WebSocket
from app.schemas.request_schema import AskRequest
from sqlalchemy.orm import Session
from sqlalchemy import select
import os
from pydantic import BaseModel,Field
from app.database import get_db
from app.services.auth import get_current_active_user,get_current_active_socket_user
from app.models.user_model import User as UserModel, UserType
from app.models.access_model import UserDomainAccess
from app.models.suborganization_model import Suborganization as SuborganizationModel
from app.models.doc_models import DocChunk                   #  from doc_models
from app.models.org_document_model import OrgDocument       #  from org_document_model
from app.utils.embeddings import embed_texts
from app.models.user_thread_model import UserThreads
from fastapi.responses import StreamingResponse
# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings,llm,BASE_DIR,retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
from langchain_classic.text_splitter import CharacterTextSplitter
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
def list_user_threads(
    org_id:int,
    user_id: int,
    db: Session = Depends(get_db),
    
):
    """
   
    """
    # if current_user.user_type != UserType.ADMIN:
    #     raise HTTPException(status_code=403, detail="Only org admins can view access")

    # user = _ensure_user_exists(db, user_id)
    # if user.organization_id != current_user.organization_id:
    #     raise HTTPException(status_code=403, detail="User is not in your organization")

    rows = (
        db.query(UserThreads)

        .filter(
            UserThreads.organization_id == org_id,
            UserThreads.user_id == user_id,
        )
        .all()
    )
    return [_access_public(r) for r in rows]



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


class Answer(BaseModel):
      content:list[str] = Field(...,description="response from llm")
      citation:list[str] = Field(...,description="multiple file name in chunks put it into list")


class AnswerOutput(BaseModel):
      response:Answer=Field(...,description="Response from llm if data varies in various source give multiple answer")



import uuid



# class RequestModel(BaseModel):
#     selected: OptionEnum

def extract_list_of_user_threads(s:UserThreads)->Dict:
    return {"id":s.id}

import json
@router.post("/list_user_threads")
def list_threads(db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
 
):

   threads=db.query(UserThreads).filter(UserThreads.organization_id==current_user.organization_id,
                                UserThreads.user_id==current_user.id).all()
   threads=[u.id for u in threads]
   print(threads)
#    print(list)
#    list=extract_list_of_user_threads(list)
   return {"threads":threads}

@router.post("/get_thread_id",summary="Requesting new Thread ID")
def ask_thread(   
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)):
    user_thread=UserThreads(user_id=current_user.id,organization_id=current_user.organization_id)
    db.add(user_thread)
    db.commit()
   
    db.flush() 
    return {"thread_id":user_thread.id}
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage,HumanMessage,AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from dotenv import load_dotenv
import os
from pydantic import BaseModel,Field

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    total_token:int
    context:list
def chat_node(state: ChatState):
    messages = state['messages'][-1]
    context=state["context"]
    # print("context",context)
    
    response=llm.generate_answer(context=context,query=messages)
    # print("response",response.content)
    # response=llm.generate_answer_with_structure(context=context,query=messages,schema=AnswerOutput)
    # response={"response1":response.response1.content,"citation1":response.response1.citation,"response2":response.response2.content,"citation2":response.response2.citation}
    # response = llm.invoke(messages)
    # print("response",response)
    total_token=response.usage_metadata['total_tokens']
    return {"messages": [response],"total_token":total_token}


# checkpointer = InMemorySaver()

# checkpointer
# checkpointer.
# graph = StateGraph(ChatState)
# graph.add_node("chat_node", chat_node)
# graph.add_edge(START, "chat_node")
# graph.add_edge("chat_node", END)

# builder = graph.compile()

builder=(StateGraph(ChatState)
       .add_node("chat_node", chat_node)
       .add_edge(START, "chat_node")
       .add_edge("chat_node", END)
       .compile)

with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as cp:
     
     cp.setup()

def _allowed_thread_id(db,current_user,t_id):
    
   threads=db.query(UserThreads).filter(UserThreads.organization_id==current_user.organization_id,
                                UserThreads.user_id==current_user.id,UserThreads.id==t_id)
   
   threads=[u.id for u in threads]
   return threads



@router.websocket("/query")
async def stream_query(websocket:WebSocket, db: Session = Depends(get_db),current_user: UserModel = Depends(get_current_active_socket_user)
    ):
    await websocket.accept()
    
    print(current_user.username)
    data=await websocket.receive_json()
    
    print("data",data)
    user_allowed_suborg_ids=list_user_access(user_id=current_user.id,org_id=data['org_id'],db=db)
    print("all sub org ids",user_allowed_suborg_ids)
    if not user_allowed_suborg_ids:
           raise HTTPException(status_code=403, detail="No acces to any department")
    allowed=_allowed_thread_id(db=db,current_user=current_user,t_id=data['selected'])
    print("allowed thread",allowed)
    if not allowed:
       raise HTTPException(status_code=403, detail="Not valid thread for current user")
    retrieval_list=[]
    for suborg_id in user_allowed_suborg_ids:
        vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{data['org_id']}\\dept\\{suborg_id}")
       # vectorStore.set_vector_store(docs=rows,embeddings=embeddings)
        
        rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=data['top_k'])
        # chunks=rv.invoke(input=data['q'])
        # print("chunks",chunks)
        retrieval_list.append(rv)
        # docs=rv.get_relevant_document(query=query)
        # docs_list.extend(docs)
        
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=await rvm.ainvoke(input=data['q'])
    
    # print(docs_list)
    
    # print("data",data)
    query=data['q']
    thread_id=data['selected']

    with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
         
         chatbot=builder(checkpointer=checkpointer)
         config={"configurable":{"thread_id":thread_id}}
        #  print("context",docs_list)

         response =  chatbot.stream({"messages":query,"context":docs_list},config=config,stream_mode="messages")
         for chunk,metadata in response :
             await websocket.send_text(chunk.content)
    await websocket.close()
@router.post("/ask", summary="Ask a question over allowed departments")
def ask(

    data:AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    
):
    # if not _can_read(db, current_user, org_id, suborg_id):
    #     raise HTTPException(status_code=403, detail="No read access to this department")

    # user_allowed_suborg_ids=list_user_access(user_id=data.user_id,org_id=data.org_id,db=db)
    user_allowed_suborg_ids=list_user_access(user_id=current_user.id,org_id=data.org_id,db=db)
    print("all sub org ids",user_allowed_suborg_ids)
    if not user_allowed_suborg_ids:
           raise HTTPException(status_code=403, detail="No acces to any department")
    allowed=_allowed_thread_id(db=db,current_user=current_user,t_id=data.selected)
    print("allowed thread",allowed)
    if not allowed:
       raise HTTPException(status_code=403, detail="Not valid thread for current user")
    retrieval_list=[]
    for suborg_id in user_allowed_suborg_ids:
        vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{data.org_id}\\dept\\{suborg_id}")
       # vectorStore.set_vector_store(docs=rows,embeddings=embeddings)
        
        rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=data.top_k)
        chunks=rv.invoke(input=data.q)
        # print("chunks",chunks)
        retrieval_list.append(rv)
        # docs=rv.get_relevant_document(query=query)
        # docs_list.extend(docs)
        
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=rvm.invoke(input=data.q)
    # if data.stream:
    #     print("streaming")
    #     my_res=None
    #     checkpointer=PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL"))
    #     # checkpointer.__exit__=lambda *args, **kwargs: None
    # # answer=llm.generate_answer(context=docs_list,query=query)
    # #    answer=llm.generate_stream_answer(context=docs_list,query=data.q)
    # #    answer=llm.generate_stream_answer_with_structure(context=docs_list,query=data.q,schema=AnswerOutput)
    #    # with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
    #     chatbot=builder(checkpointer=checkpointer)
    #     config={"configurable":{"thread_id":data.selected}}
    #     response=chatbot.stream({"messages":data.q,"context":docs_list},config=config,stream_mode="messages") 
    #     my_res=response
    #     def generate(response):
    #              for chunk,metadata in response :
    #                    print(chunk.content)
    #                    yield str(chunk.constent)
    #     return StreamingResponse(generate(my_res),media_type='application/json')

            #  generate(my_res)
            #  answer=chatbot.invoke({"messages":data.q,"context":docs_list},config=config)
    #    def generate(ans):
    #     for item in ans:
    #         yield str(item.content)

        # return StreamingResponse(generate(my_res),media_type='application/json')

    # else :
    with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
             chatbot=builder(checkpointer=checkpointer)
             config={"configurable":{"thread_id":data.selected}}
    
             answer=chatbot.invoke({"messages":data.q,"context":docs_list},config=config)
       #answer = llm.generate_answer_with_structure(context=docs_list,query=data.q,schema=AnswerOutput)
    #   res=json.loads(answer.content)
        #  print("res",answer)
      #    answer=llm.generate_answer(context=docs_list,query=data.q)
    #    return {
    #     "answer": answer.content,
    #     "sources": docs_list,
    #    }
    return {"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list}

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
