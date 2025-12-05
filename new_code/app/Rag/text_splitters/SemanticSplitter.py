from abstractions.IdocumentSplitter import IdocumentSplitter
# from langchain_text_splitters import CharacterTextSplitter
from semantic_chunker_langchain.chunker import SemanticChunker, SimpleSemanticChunker
# from langchain.text_splitter import CharacterTextSplitter
class SemanticSplitter(IdocumentSplitter):
     def __init__(self,embeddings):
          
          self.embeddings=embeddings

     def split_documents(self,docs,chunk_size,chunk_overlap):
         text_splitter = SemanticChunker(max_tokens=chunk_size,overlap=chunk_overlap)

         return text_splitter.split_documents(docs)
    #  def split_documents(self,docs,chunk_size,chunk_overlap):
    #       splitter=SemanticChunker(
    # chunk_size=chunk_size,
    # chunk_overlap=chunk_overlap,
    # separator='')
    #       return splitter.split_documents(docs)