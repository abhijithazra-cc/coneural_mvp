from Rag.abstractions.IdocumentSplitter import IdocumentSplitter

from langchain_text_splitters import RecursiveCharacterTextSplitter

class CharacterSplitter(IdocumentSplitter):
     def __init__(self,embeddings=None):
          
          self.embeddings=embeddings

     def split_documents(self,docs,chunk_size,chunk_overlap):
         text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=chunk_overlap)
     #     print(docs)
         
         return text_splitter.split_documents(docs)