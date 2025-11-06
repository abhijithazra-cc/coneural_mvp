from Rag.abstractions.IVectorstore import IVectorstore
from langchain_community.vectorstores import FAISS
class FaissVectorstore(IVectorstore):
     def __init__(self):
          self.vectorstre=None

     def set_vector_store(self,docs,embeddings):
          # self.vectorstore = FAISS.from_documents(docs, embeddings)
          self.vectorstore = FAISS.from_embeddings(text_embeddings=docs, embedding= embeddings)
        #   val=self.vectorstore.as_retriever()
        #   val._get_relevant_documents()
     def get_vector_store(self):
          return self.vectorstore
          