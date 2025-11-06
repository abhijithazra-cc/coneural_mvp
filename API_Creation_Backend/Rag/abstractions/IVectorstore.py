from abc import ABC, abstractmethod
class IVectorstore(ABC):
      @abstractmethod
      def set_vector_store(docs,embeddings):
          pass
      @abstractmethod
      def get_vector_store():
          pass
      