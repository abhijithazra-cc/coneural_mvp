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
import routers
from routers.bot import router as bot_router
# from SemanticSplitter import SemanticSplitter


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
app.include_router(router=bot_router)

@app.get("/health")
async def health():
    return {"response":"success"}
