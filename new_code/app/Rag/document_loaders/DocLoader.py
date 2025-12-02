from langchain_community.document_loaders import PyMuPDFLoader
from app.Rag.abstractions.Idocloader import Idocloader
import fitz  # PyMuPDF (best)
from io import BytesIO
from langchain_core.documents import Document
from typing import Optional
import docx
from io import BytesIO
class DocLoader(Idocloader):
     def __init__(self):
          self.documents=None

     def load_document(self,file:str | bytes,filename:str,id=None):
                
                if type(file)==str:
                    print("file type","str")
                    docs=[]

                    doc = docx.Document(BytesIO(file))
                    for i,p in enumerate(doc):
                        docs.append(Document(page_content=p.get_text("text"),metadata={"pages":i+1,"filename":filename}))

                    self.documents=docs
                else:
                    print("file type","bytes")
                    docs=[]
                    doc = docx.Document(file)
                    for i,p in enumerate(doc):
                        docs.append(Document(page_content=p.get_text("text"),id=id,metadata={"pages":i+1,"filename":filename}))

                    self.documents=docs
                    print("my docs",docs)

     def get_document(self):
          return self.documents
     def get_full_content(self):
          res=""
          for item in self.documents:
              res+=" "+item.page_content

          return res
