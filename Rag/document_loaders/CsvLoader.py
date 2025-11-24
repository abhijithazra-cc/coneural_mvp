from langchain_community.document_loaders import PyMuPDFLoader
from Rag.abstractions.Idocloader import Idocloader
import fitz  # PyMuPDF (best)
from io import BytesIO
from langchain_core.documents import Document
from typing import Optional
import docx
from io import BytesIO
import pandas as pd

class CsvLoader(Idocloader):
     def __init__(self):
          self.documents=None

     def load_document(self,file:str | bytes,filename:str):
                
                if type(file)==str:
                    print("file type","str")
                    docs = []
                    df = pd.read_csv(file)
                    print("df")
                    

                    for _, row in df.iterrows():
                        text = row.to_json()
                        docs.append(Document(page_content=text, metadata={"row_index": int(_)}))
                    self.documents=docs
                    return docs

                else:
                    docs = []
                    df = pd.read_csv(BytesIO(file))
   

                    for _, row in df.iterrows():
                        text = row.to_json()
                        docs.append(Document(page_content=text, metadata={"row_index": int(_)}))
                    self.documents=docs
                    return docs

                 

     def get_document(self):
          return self.documents
     def get_full_content(self):
          res=""
          for item in self.documents:
              res+=" "+item.page_content

          return res
# file_path = "./example_data/layout-parser-paper.pdf"
# loader = PyMuPDFLoader(file_path)