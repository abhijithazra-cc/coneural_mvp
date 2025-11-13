from abc import ABC, abstractmethod
class IdocumentSplitter(ABC):
      @abstractmethod
      def split_documents(docs,chunk_size,chunk_overlap):
          pass