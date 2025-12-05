
class Retriever():


      def format_docs(self,docs):
          return "\n\n".join(doc.page_content for doc in docs)
      def get_retreiver(self,vector_store,search_type,top_n):
          
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n)})
          return self.retriever
      def get_retreiver_by_doc_id(self,vector_store,search_type,top_n,doc_id):
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n), "filter": {"doc_id": int(doc_id)} })
          return self.retriever
      def get_relevant_document(self,query):
           
           retrieved_docs = self.retriever.invoke(input=query)
        #    retrieved_docs=self.format_docs(retrieved_docs)
           return retrieved_docs
       