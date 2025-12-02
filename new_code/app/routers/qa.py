# app/routers/qa.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query,WebSocket,BackgroundTasks
from app.schemas.request_schema import AskRequest,AskRequestOnDocument
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
# from app.models.org_document_model import OrgDocument       #  from org_document_model
from app.models.doc_models import OrgDocument
from app.utils.embeddings import embed_texts
from app.models.user_thread_model import UserThreads
from fastapi.responses import StreamingResponse
# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings,llm,BASE_DIR,retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
from langchain_classic.text_splitter import CharacterTextSplitter
from app.Rag.HighlightText import HighlightText
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



import time
import re
import base64
from app.Rag.PdfUploader import upload_pdf_to_github
def _get_doc_by_id(db:Session,current_user:UserModel,doc_id:int):
     docs=db.query(OrgDocument).filter(OrgDocument.org_id==current_user.organization_id,OrgDocument.id==doc_id)
     return [u.file_bytes for u in docs]
def filter_sources_by_citation(db,current_user,response_text, sources):
    # 1. Extract all filenames mentioned after "citation"
    # Example fragment: "citation1: virat kohli 4.pdf"
    cited_files = re.findall(r"([\w\s\-()]+\.(?:pdf|PDF))", response_text)

    # Normalize filenames
    cited_files = [f.strip() for f in cited_files]
    print(cited_files)
    result = {}

    # 2. Filter sources matching the cited filenames
    for src in sources:
        # print(src.metadata['filename'].lower())
        filename = src.metadata.get('filename')


        if filename in cited_files:
            doc_id = src.metadata["doc_id"]
            page_content = src.page_content
            print("doc_id",doc_id)
            if doc_id not in result:
                 result[doc_id] = {
                    "filename": filename,
                    "chunks": [],
                    "link":None
                }

            # Append page content to dict
            result[doc_id]["chunks"].append(page_content)
    # print(result)
    for doc_id,items in result.items():
            
            my_bytes=_get_doc_by_id(db,current_user,doc_id)
            # print(my_bytes)
            my_bytes=base64.b64decode(my_bytes[0])
            obj=HighlightText()
            my_bytes=obj.highlight_text(my_bytes,chunks=items['chunks'])
            # with open('my_pdf.pdf',mode='wb') as f:
            #       f.write(my_bytes)
            # my_bytes=base64.b64encode(my_bytes).decode()
            response=upload_pdf_to_github(file_name=items['filename'],owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer',pdf_bytes=my_bytes)
            # print(response)

            result[doc_id]['link']=response['link']
            # print(my_bytes)
    # print("result",result)
    return json.dumps(result)

def create_link_for_citation(db, current_user, citations, sources):
    """
    Input citations format:
    [
        ["virat kohli 1.pdf", 10],
        ["virat kohli 3.pdf", 8],
        ["virat kohli 4.pdf", 7]
    ]

    Output format (same style, now with link):
    [
        ["virat kohli 1.pdf", 10, "url"],
        ["virat kohli 3.pdf", 8, "url"],
        ["virat kohli 4.pdf", 7, "url"]
    ]
    """

    # Extract only filenames
    cited_files = {c[0]: c[1] for c in citations}

    # temp storage
    file_chunks = {fname: [] for fname in cited_files}

    # Collect chunks for all cited files
    for src in sources:
        filename = src.metadata.get("filename")
        if filename in file_chunks:
            file_chunks[filename].append({
                "doc_id": src.metadata["doc_id"],
                "content": src.page_content
            })

    final_output = []

    # Process each citation entry
    for filename, count in cited_files.items():

        chunks = file_chunks[filename]
        if not chunks:
            # still return with no link
            final_output.append([filename, count, None])
            continue

        # All chunks come from same PDF → get doc_id from first
        doc_id = chunks[0]["doc_id"]

        # get stored PDF bytes
        pdf_b64 = _get_doc_by_id(db, current_user, doc_id)
        pdf_bytes = base64.b64decode(pdf_b64[0])

        # highlight text
        highlighter = HighlightText()
        updated_pdf_bytes = highlighter.highlight_text(
            pdf_bytes, 
            chunks=[c["content"] for c in chunks]
        )

        # upload to github
        upload_res = upload_pdf_to_github(
            file_name=filename,
owner="rahulkumarcollectcent",token="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",
            folder="uploads",
            repo="pdf-viewer",
            pdf_bytes=updated_pdf_bytes
        )

        link = upload_res.get("link")

        # final array (same format as input)
        final_output.append([filename, count, link])

    return json.dumps({"citations": final_output}, indent=2)



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
        
        rv=retriever.get_retreiver(vector_store=vectorStore.get_vector_store(),search_type='mmr',top_n=data['top_k'])
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
         content=""
         chatbot=builder(checkpointer=checkpointer)
         config={"configurable":{"thread_id":thread_id}}
        #  print("context",docs_list)

        #  response =  chatbot.stream({"messages":query,"context":docs_list},config=config,stream_mode="messages")
         response =  chatbot.stream({"messages":query,"context":docs_list},config=config)
         for event in response:
               for item in event.values():
                    messages=item['messages']
                    last_message = messages[-1]
                    await websocket.send_text(json.dumps({"data":last_message.content,"type":"chunk"}))
        #  for chunk in response:
        #       print(chunk)
        #       await websocket.send_text(json.dumps({"data":"data","type":"chunk"}))
        #  for chunk,metadata in response :
        #     #  print(chunk)
        #      content+=chunk.content
        #      await websocket.send_text(json.dumps({"data":chunk.content,"type":"chunk"}))
            #  print(chunk)
            #  if metadata:
        #  print("chunks",docs_list) 
        #  print(content)
        #  output=filter_sources_by_citation(db,current_user,content,sources=docs_list)
        #  print("output",output)
         await websocket.send_text(json.dumps({"data":"output","type":"metadata"}))
            #        await websocket.send_text(json.dumps({"data":metadata,"extra":"metadata"}))
    await websocket.close()
import sys
@router.post("/ask", summary="Ask a question over allowed departments")
def ask(

    data:AskRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    
):
    s=time.monotonic()
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
        # chunks=rv.invoke(input=data.q)
        # print("chunks",chunks)
        retrieval_list.append(rv)
        # docs=rv.get_relevant_document(query=query)
        # docs_list.extend(docs)
        
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=rvm.invoke(input=data.q)
   
    with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
             chatbot=builder(checkpointer=checkpointer)
             config={"configurable":{"thread_id":data.selected}}
    
             answer=chatbot.invoke({"messages":data.q,"context":docs_list},config=config)

    e=time.monotonic()
    siz=sys.getsizeof(rvm)
    print("chunks",docs_list)
    output=json.loads(answer['messages'][-1].content)
    s1=time.monotonic()
    bt=BackgroundTasks()
    
    my_id=bt.add_task(create_link_for_citation,db,current_user,citations=output['citation'],sources=docs_list)
    print(bt.tasks)
    # cit=create_link_for_citation(db,current_user,citations=output['citation'],sources=docs_list)
    print("time",time.monotonic()-s1)
    # print(cit)
    return {"query_time":e-s,"response":output['response'],"citations":output['citation'],"total_token":answer['total_token']}
    # return {"query_time":e-s,"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list,"size":siz}


def _get_suborg_by_doc_id(db:Session,doc_id_list:list[int]):
     suborg_id=db.query(OrgDocument.id,OrgDocument.suborg_id).filter(OrgDocument.id.in_(doc_id_list)).all()
     return suborg_id


@router.post("/ask/doocuments", summary="Ask a question over allowed departments over perticular document")
def ask_by_id(

    data:AskRequestOnDocument,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
    
):
    s=time.monotonic()
    # if not _can_read(db, current_user, org_id, suborg_id):
    #     raise HTTPException(status_code=403, detail="No read access to this department")
    print(data.doc_id,data.selected)
    doc_suborg=_get_suborg_by_doc_id(db,data.doc_id)
    print(doc_suborg)
    retrieval_list=[]

    # user_allowed_suborg_ids=list_user_access(user_id=data.user_id,org_id=data.org_id,db=db)
    # user_allowed_suborg_ids=list_user_access(user_id=current_user.id,org_id=data.org_id,db=db)
    # print("all sub org ids",user_allowed_suborg_ids)
    # if not user_allowed_suborg_ids:
    #        raise HTTPException(status_code=403, detail="No acces to any department")
    allowed=_allowed_thread_id(db=db,current_user=current_user,t_id=data.selected)
    print("allowed thread",allowed)
    if not allowed:
       raise HTTPException(status_code=403, detail="Not valid thread for current user")
    for doc_id,suborg_id in doc_suborg:
         
        vectorStore=vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\\{data.org_id}\\dept\\{suborg_id}")
        rv=retriever.get_retreiver_by_doc_id(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=data.top_k,doc_id=doc_id)
        retrieval_list.append(rv)
    rvm= EnsembleRetriever(retrievers=retrieval_list)
    docs_list=rvm.invoke(input=data.q)
       
    with PyMySQLSaver.from_conn_string(conn_string=os.getenv("DATABASE_URL")) as checkpointer:
             chatbot=builder(checkpointer=checkpointer)
             config={"configurable":{"thread_id":data.selected}}
    
             answer=chatbot.invoke({"messages":data.q,"context":docs_list},config=config)

    e=time.monotonic()
    siz=sys.getsizeof(rv)
    return {"query_time":e-s,"response":answer['messages'][-1].content,"total_token":answer['total_token'],"sources":docs_list}

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
