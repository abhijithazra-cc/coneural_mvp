from abstractions.IdocumentSplitter import IdocumentSplitter
# from langchain_text_splitters import CharacterTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
# from semantic_chunker_langchain.chunker import SemanticChunker, SimpleSemanticChunker
# from langchain.text_splitter import CharacterTextSplitter
class CharacterSplitter(IdocumentSplitter):
     def __init__(self,embeddings=None):
          
          self.embeddings=embeddings

     def split_documents(self,docs,chunk_size,chunk_overlap):
         text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=chunk_overlap)

         return text_splitter.split_documents(docs)