from abc import ABC, abstractmethod
class Idocloader(ABC):
      @abstractmethod
      def load_document(file_path=""):
          pass
      @abstractmethod
      def get_document():
           pass