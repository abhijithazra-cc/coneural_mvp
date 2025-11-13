from langchain_community.document_loaders import PyMuPDFLoader
from app.Rag.abstractions.Idocloader import Idocloader

class PdfLoader(Idocloader):
     def __init__(self):
          self.documents=""
     def load_document(self,file_path=""):
          loader=PyMuPDFLoader(file_path)
          self.documents=loader.load()
          return self
     def get_document(self):
          return self.documents
# file_path = "./example_data/layout-parser-paper.pdf"
# loader = PyMuPDFLoader(file_path)