from langchain_community.document_loaders import PyMuPDFLoader
from Rag.abstractions.Idocloader import Idocloader
import fitz  # PyMuPDF (best)
from io import BytesIO
from langchain_core.documents import Document
from typing import Optional
class PdfLoader(Idocloader):
     def __init__(self):
          self.documents=None

     def load_document(self,file:str | bytes,filename:str):
                
                if type(file)==str:
                    print("file type","str")
                    loader=PyMuPDFLoader(file)
                    self.documents=loader.load()
                else:
                    print("file type","bytes")
                    doc = fitz.open(stream=file, filetype="pdf")
                    docs=[]
                    for i,p in enumerate(doc):
                        docs.append(Document(page_content=p.get_text("text"),metadata={"pages":i+1,"filename":filename}))

                    self.documents=docs

     def get_document(self):
          return self.documents
     def get_full_content(self):
          res=""
          for item in self.documents:
              res+=" "+item.page_content

          return res
# file_path = "./example_data/layout-parser-paper.pdf"
# loader = PyMuPDFLoader(file_path)