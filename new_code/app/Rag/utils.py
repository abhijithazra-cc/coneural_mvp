from langchain_openai.embeddings import OpenAIEmbeddings
from app.Rag.OpenaiModel import OpenaiModel
import os
from app.Rag.Retriever import Retriever
retriever=Retriever()
BASE_DIR="vectorstores\org"
embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'),model='text-embedding-3-small')
llm=OpenaiModel()
