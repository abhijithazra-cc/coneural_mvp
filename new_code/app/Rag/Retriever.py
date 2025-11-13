
class Retriever():
      def __init__(self):
           self.retriever=None

      def format_docs(self,docs):
          return "\n\n".join(doc.page_content for doc in docs)
      def get_retreiver(self,vector_store,search_type,top_n):
          retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n)})
          return retriever
      def get_documents(self,query):
           
           retrieved_docs = self.retriever.invoke(query)
        #    retrieved_docs=self.format_docs(retrieved_docs)
           return retrieved_docs
       