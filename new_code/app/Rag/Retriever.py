
class Retriever():


      def format_docs(self,docs):
          return "\n\n".join(doc.page_content for doc in docs)
      def get_retreiver(self,vector_store,search_type,top_n):
          
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n)})
          return self.retriever
    #   def get_retreiver_by_document_id(self,vector_store,search_type,top_n,document_id):
    #       self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n), "filter": {"document_id": int(document_id)} })
    #       return self.retriever

      def get_retreiver_by_document_id(self, vector_store, search_type, top_n, document_id):
    # Handle both single id and list of ids
           if isinstance(document_id, list):
            filter_query = {"document_id": {"$in": [int(d) for d in document_id]}}
           else:
            filter_query = {"document_id": int(document_id)}

           self.retriever = vector_store.as_retriever(search_type=search_type,search_kwargs={
            "k": int(top_n),
            "filter": filter_query
            }
    )
           return self.retriever
      def get_retreiver_by_dept_id(self,vector_store,search_type,top_n,dept_id):
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n), "filter": {"dept_id": int(dept_id)} })
          return self.retriever
      def get_retreiver_by_department_id(self,vector_store,search_type,top_n,dept_id):
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n), "filter": {"dept_id": int(dept_id)} })
          return self.retriever
      def get_retreiver_by_department_ids(self,vector_store,search_type,top_n,dept_ids:list[int]):
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n), "filter": {"dept_id": {"$in": dept_ids}} })
          return self.retriever
      def get_relevant_document(self,query):
           
           retrieved_docs = self.retriever.invoke(input=query)
        #    retrieved_docs=self.format_docs(retrieved_docs)
           return retrieved_docs
       