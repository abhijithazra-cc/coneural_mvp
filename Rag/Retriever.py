
class Retriever():
      def __init__(self):
           self.retriever=None

        
      def set_retreiver(self,vector_store,search_type,top_n):
          self.retriever  = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": int(top_n)})
          
      def get_relevant_document(self,query):
           retrieved_docs = self.retriever._get_relevant_documents(query,run_manager=None)
           return retrieved_docs
       