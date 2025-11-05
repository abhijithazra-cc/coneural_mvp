import os
from dotenv import load_dotenv
from fastapi import FastAPI,File, UploadFile
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
# from SemanticSplitter import SemanticSplitter
load_dotenv()

app = FastAPI(title="Rag Implementation using Langchain")

#  CORS setup
origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "").split(",") if o.strip()] \
          or ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# splitter=SemanticSplitter(embeddings=embeddings)
# print(docs)

@app.get("/health")
async def health():
    """Simple health check endpoint"""
    return {"status": "ok"}


@app.get("/show_document")
async def get_document():
    "See Uploaded Document"
    return loader.get_document()
@app.get("/generate_vectorstore")
async def gen_store():
    "Geerate Vectorstore"
    chuncks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)
    vectorStore.set_vector_store(chuncks,embeddings=embeddings)
    return {"response":"vector store generated for perticular doc"}

# @app.post("/generte_retriever")
# async def gen_retriever():
#     "Generate Retriever"

#     retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type='')
    
#     return {"response":"retriever generated for perticular documents now you can query"}


@app.post("/query")
async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
    "Get Relevent Documents Chunk on basis of query"
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
    docs=retriever.get_relevant_document(query=query)
    docs=llm.generate_answer(context=docs,query=query)
    
    return docs
@app.post("/show_relevent_chunk")
async def get_relevant_documents_chunks(query:str="",search_type="similarity",top_n_chunks:int=1):
    "Get Relevent Documents Chunk on basis of query"
    retriever.set_retreiver(vector_store=vectorStore.get_vector_store(),search_type=search_type,top_n=top_n_chunks)
    docs=retriever.get_relevant_document(query=query)

    
    return docs

@app.get("/show_all_chunks")
async def get_chunks():
    "See Uploaded Document"
    chunks=splitter.split_documents(docs=loader.get_document(),chunk_size=1000,chunk_overlap=100)
    
    return  {"chunks":chunks,"chunks_len":len(chunks)}




@app.post("/upload")
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
    chuncks=splitter.split_documents(docs=loader.get_document(),chunk_size=100,chunk_overlap=50)
    vectorStore.set_vector_store(chuncks,embeddings=embeddings)
    e=time.monotonic()

    return {"filename": file.filename, "size": len(content),"message":"vectore store generated peform query","process_time":e-s}
 except :
     raise RuntimeError(content="Check your text file")


