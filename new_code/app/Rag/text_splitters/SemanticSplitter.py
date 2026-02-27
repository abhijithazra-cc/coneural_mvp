from app.Rag.abstractions.IdocumentSplitter import IdocumentSplitter
# from langchain_text_splitters import CharacterTextSplitter
# from semantic_chunker_langchain.chunker import SemanticChunker, SimpleSemanticChunker
from langchain_experimental.text_splitter import SemanticChunker


class SemanticSplitter(IdocumentSplitter):
     def __init__(self,embeddings):
          
          self.embeddings=embeddings

     def split_documents(self,docs,chunk_size,chunk_overlap):
         text_splitter = SemanticChunker(embeddings=self.embeddings,min_chunk_size=chunk_size)

         return text_splitter.split_documents(docs)




# # app/Rag/text_splitters/SemanticSplitter.py

# from app.Rag.abstractions.IdocumentSplitter import IdocumentSplitter
# from langchain_experimental.text_splitter import SemanticChunker

# class SemanticSplitter(IdocumentSplitter):
#      def __init__(self, embeddings):
#           self.embeddings = embeddings

#      def split_documents(self, docs, chunk_size, chunk_overlap):
#          text_splitter = SemanticChunker(embeddings=self.embeddings, min_chunk_size=chunk_size)
#          return text_splitter.split_documents(docs)





