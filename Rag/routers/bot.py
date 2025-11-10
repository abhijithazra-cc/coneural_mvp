from fastapi import APIRouter, Depends, HTTPException, Query

import os
from dotenv import load_dotenv
from fastapi import FastAPI,File, UploadFile,Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import sys, os
from PdfLoader import PdfLoader
from langchain_openai.embeddings import OpenAIEmbeddings
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from TxtLoader import TxtLoader
from CharacterSplitter import CharacterSplitter
from FaissVectorstore import FaissVectorstore
from Retriever import Retriever
from OpenaiModel import OpenaiModel
import time
from ChromadbVectorstore import ChromadbVectorstore
from fastapi import BackgroundTasks
load_dotenv()
router = APIRouter(prefix="/bot", tags=["ChatBot"])

embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'),model='text-embedding-3-small')
# from langchain_community.document_loaders import TextLoader
# loader=TextLoader("sample.txt")
# documents=loader.load()
# loader=TxtLoader()
loader=PdfLoader()
splitter=CharacterSplitter()
# vectorStore=ChromadbVectorstore(embeddings=embeddings)
vectorStore=FaissVectorstore(embeddings=embeddings)
vectorStore._load_or_create_store()
retriever=Retriever()
llm=OpenaiModel()

@router.get("/show_document")
async def get_document():
    "See Uploaded Document"
    return loader.get_document()



@router.post("/query")
async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
    "Get Relevent Documents Chunk on basis of query"
    s=time.monotonic()
    emd=embeddings.embed_query(query)
    print(emd)
    print("*****",type(emd),"*****")
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
    docs=retriever.get_relevant_document(query=query)
    docs=llm.generate_answer(context=docs,query=query)
    e=time.monotonic()
    return {"response":docs,"processing_time":e-s}



@router.get("/stream")
async def stream(query:str = Query(..., description="Your query text")):
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=5)
    docs=retriever.get_relevant_document(query=query)
    
    docs=llm.generate_stream_answer(context=docs,query=query)
  
    def event_stream(docs):
         for res in docs:
                 print(res.content)
                 yield res.content
                 time.sleep(1)
    return StreamingResponse(event_stream(docs), media_type="routerlication/json")
  

@router.get("/query-stream")
async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
    "Get Relevent Documents Chunk on basis of query"
    s=time.time()
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
    docs=retriever.get_relevant_document(query=query)
    
    docs=llm.generate_stream_answer(context=docs,query=query)
    
    llm.set_model_response(docs)
    e=time.time()
    
    return {"response":docs,"processing_time":e-s}

@router.post("/show_relevent_chunk")
async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
    "Get Relevent Documents Chunk on basis of query"
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
    docs=retriever.get_relevant_document(query=query)

    
    return docs
@router.get("/show_all_doc_id")
async def get_all_doc_ids():
    ids=vectorStore.get_document_ids()
    return {"ids":ids}
@router.get("/show_chunk_by_id/{doc_id}")
async def get_chunk(doc_id):
    c=vectorStore.get_chunks_by_doc_id(doc_id=doc_id)
    return c
@router.get("/delete_chunk_by_id/{doc_id}")
async def get_chunk(doc_id):
    vectorStore.delete_by_doc_id(doc_id=doc_id)
    return {"response":f"chunk deleted belongs to docs {doc_id}"}
   
@router.get("/show_all_chunks")
async def get_chunks():
    "See Uploaded Document"
    chunks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)

    
    return  {"chunks":chunks,"chunks_len":len(chunks)}




@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
 try: 
    s=time.monotonic()
    # Read the file contents
    
    content = await file.read()
    
    # Optionally, save it to disk
    with open(f"{file.filename}", "wb") as f:
        f.write(content)
    file_path=os.path.abspath(file.filename)
    
    loader.load_document(file_path)
    chuncks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)
    # BackgroundTasks.add_task(vectorStore.set_vector_store,chuncks)
    vectorStore.add_documents(docs=chuncks,doc_id=1)
    # vectorStore.set_vector_store(chuncks)
    e=time.monotonic()

    return {"filename": file.filename, "size": len(content),"message":"vectore store generated peform query","process_time":e-s}
 except :
     raise RuntimeError(content="Check your text file")

