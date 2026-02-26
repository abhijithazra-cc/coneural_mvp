from abc import ABC, abstractmethod
class Idocloader(ABC):
      @abstractmethod
      def load_document(file,**args):
          pass
      @abstractmethod
      def get_document():
           pass
      @abstractmethod
      def get_full_content():
           pass