from fastapi import APIRouter, Depends, HTTPException, Query

import os
from dotenv import load_dotenv
from fastapi import FastAPI,File, UploadFile,Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import sys, os

from Rag.PdfLoader import PdfLoader
from langchain_openai.embeddings import OpenAIEmbeddings
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from Rag.TxtLoader import TxtLoader
from Rag.CharacterSplitter import CharacterSplitter
from Rag.FaissVectorstore import FaissVectorstore
from Rag.Retriever import Retriever
from Rag.OpenaiModel import OpenaiModel
import time
load_dotenv()
router = APIRouter(prefix="/bot", tags=["ChatBot"])

embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'),model='text-embedding-3-small')
# from langchain_community.document_loaders import TextLoader
# loader=TextLoader("sample.txt")
# documents=loader.load()
# loader=TxtLoader()
loader=PdfLoader()
splitter=CharacterSplitter()
vectorStore=FaissVectorstore()
retriever=Retriever()
llm=OpenaiModel()

# @router.get("/show_document")
# async def get_document():
#     "See Uploaded Document"
#     return loader.get_document()



# @router.post("/query")
# async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
#     "Get Relevent Documents Chunk on basis of query"
#     s=time.monotonic()
#     retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
#     docs=retriever.get_relevant_document(query=query)
#     docs=llm.generate_answer(context=docs,query=query)
#     e=time.monotonic()
#     return {"response":docs,"processing_time":e-s}



# @router.get("/stream")
# async def stream(query:str = Query(..., description="Your query text")):
#     retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type='similarity',top_n=5)
#     docs=retriever.get_relevant_document(query=query)
    
#     docs=llm.generate_stream_answer(context=docs,query=query)
  
#     def event_stream(docs):
#          for res in docs:
#                  print(res.content)
#                  yield res.content
#                  time.sleep(1)
#     return StreamingResponse(event_stream(docs), media_type="routerlication/json")
  

# @router.get("/query-stream")
# async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
#     "Get Relevent Documents Chunk on basis of query"
#     s=time.time()
#     retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
#     docs=retriever.get_relevant_document(query=query)
    
#     docs=llm.generate_stream_answer(context=docs,query=query)
    
#     llm.set_model_response(docs)
#     e=time.time()
    
#     return {"response":docs,"processing_time":e-s}

# @router.post("/show_relevent_chunk")
# async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
#     "Get Relevent Documents Chunk on basis of query"
#     retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
#     docs=retriever.get_relevant_document(query=query)

    
#     return docs

# @router.get("/show_all_chunks")
# async def get_chunks():
#     "See Uploaded Document"
#     chunks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)
    
#     return  {"chunks":chunks,"chunks_len":len(chunks)}




# @router.post("/upload")
# async def upload_file(file: UploadFile = File(...)):
#  try: 
#     s=time.monotonic()
#     # Read the file contents
    
#     content = await file.read()
    
#     # Optionally, save it to disk
#     with open(f"{file.filename}", "wb") as f:
#         f.write(content)
#     file_path=os.path.abspath(file.filename)
#     loader.load_document(file_path)
#     chuncks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)
#     vectorStore.set_vector_store(chuncks,embeddings=embeddings)
#     e=time.monotonic()

#     return {"filename": file.filename, "size": len(content),"message":"vectore store generated peform query","process_time":e-s}
#  except :
#      raise RuntimeError(content="Check your text file")

