import img2pdf
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
import fitz
import pytesseract
from PIL import Image
import io


# IMPORTANT (Windows): Set path to tesseract.exe
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
def encode_image(image_bytes: bytes):

    return base64.b64encode(image_bytes).decode("utf-8")


# Example


class ImageLoader(Idocloader):
    def __init__(self):
        self.documents = None

    def load_document(self, file: str | bytes, filename: str):

        if type(file) == str:
            print("file type", "str")
            docs = []

            self.documents = docs
            return docs

        else:
            print("bytes",type(file))
            docs = []
            # myfile = img2pdf.convert(file)
            # with open('temp.pdf', 'wb') as f:
            #     f.write(myfile)
            response = self.ocr(file)
            docs.append(Document(page_content=response, metadata={
                        "pages":  1, "filename": filename}))

            self.documents = docs
            return docs

    def ocr(self,image_bytes: bytes):
           image = Image.open(io.BytesIO(image_bytes))

           # OCR extraction
           response = pytesseract.image_to_string(image)
           print(response)
           return response

    def get_document(self):
            return self.documents

    def get_full_content(self):
            res = ""
            for item in self.documents:
                res += " "+item.page_content

            return res
# file_path = "./example_data/layout-parser-paper.pdf"
# loader = PyMuPDFLoader(file_path)
