from app.Rag.abstractions.Idocloader import Idocloader
from langchain_community.document_loaders import TextLoader
class TxtLoader(Idocloader):
     def __init__(self):
          self.documents=""
     def load_document(self,file_path=""):
          loader=TextLoader(file_path)
          self.documents=loader.load()
          return self
     def get_document(self):
          return self.documents