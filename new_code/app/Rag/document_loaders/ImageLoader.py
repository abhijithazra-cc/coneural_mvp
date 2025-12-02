from langchain_community.document_loaders import PyMuPDFLoader
from Rag.abstractions.Idocloader import Idocloader
import fitz  # PyMuPDF (best)
from io import BytesIO
from langchain_core.documents import Document
from typing import Optional
import docx
from io import BytesIO
import pandas as pd
# import easyocr
import io
from PIL import Image
from Rag.OpenaiModel import OpenaiModel
# reader = easyocr.Reader(["en"])
from langchain_core.messages import HumanMessage
import base64

def encode_image(image_bytes: bytes):
 
        return base64.b64encode(image_bytes).decode("utf-8")

def ocr(image_bytes: bytes,filename:str):
    b64 = encode_image(image_bytes)
    type=filename.split('.')[1]
    print("file type",type)
    llm=OpenaiModel()
    llm=llm.get_llm()
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "Extract all text from this image."},
            {
                "type": "image_url",
                "image_url":{"url": f"data:image/{type};base64,{b64}"},
            },
        ]
    )

    response = llm.invoke([msg])
    print(response)
    return response


# Example

class ImageLoader(Idocloader):
     def __init__(self):
          self.documents=None

     def load_document(self,file:str | bytes,filename:str):
                
                if type(file)==str:
                    print("file type","str")
                    docs = []
                    

                    self.documents=docs
                    return docs

                else:
                    docs = []
                   
                    response=ocr(file,filename)
                    docs.append(Document(page_content=response.content,metadata={"id":response.id,"total_token":response.usage_metadata['total_tokens']}))
                     
                    self.documents=docs
                    return docs

                 

     def get_document(self):
          return self.documents
     def get_full_content(self):
          res=""
          for item in self.documents:
              res+=" "+item.page_content

          return res
