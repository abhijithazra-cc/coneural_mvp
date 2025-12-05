from abc import ABC, abstractmethod
class IVectorstore(ABC):
      @abstractmethod
      def _load_or_create_store():
           pass
      @abstractmethod
      def add_documents(docs,doc_id):
           pass
      @abstractmethod
      def set_vector_store(docs,embeddings):
          pass
      @abstractmethod
      def get_vector_store():
          pass
      @abstractmethod
      def get_chunks_by_doc_id(doc_id):
           pass
      @abstractmethod
      def delete_document_by_id(doc_id):
           pass
      