from langchain_community.document_loaders import PyMuPDFLoader
from app.Rag.abstractions.Idocloader import Idocloader
import fitz  # PyMuPDF (best)

from langchain_core.documents import Document
import os
import fitz
import pytesseract
from PIL import Image
import io
from app.Rag.ocr.OpenaiOCR import OpenaiOCR
OCR=OpenaiOCR(api_key=os.getenv("OPENAI_API_KEY")) 

# IMPORTANT (Windows): Set path to tesseract.exe
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
#for linux
# pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

class PdfLoader(Idocloader):
    def __init__(self):
        self.documents = None

    def load_document(self, file: str | bytes, filename: str):
        if type(file) == str:
            print("file type", "str")
            loader = PyMuPDFLoader(file, extract_images=True)
            self.documents = loader.load()
            print(self.documents)
            print(len(self.documents))

        else:
            print("file type", "bytes")

            doc = fitz.open(stream=file, filetype="pdf")
            docs = []

            for i, p in enumerate(doc):
                # -----------------------------
                # 1. Extract normal PDF text
                # -----------------------------
                text_content = p.get_text("text") or ""

                # -----------------------------
                # 2. Extract images + OCR them
                # -----------------------------
                ocr_texts = []
                images = p.get_images(full=True)

                for img_index, img in enumerate(images):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)

                    # Convert pixmap to PNG bytes
                    if pix.n < 5:  # RGB or grayscale
                        img_bytes = pix.tobytes("png")
                    else:  # CMYK → convert to RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                        img_bytes = pix.tobytes("png")

                    # Load into PIL
                    # image = Image.open(io.BytesIO(img_bytes))

                    # OCR extraction
                    ocr_text = OCR.extract(img_bytes, filename)

                    # Store only if something meaningful extracted
                    if ocr_text.strip():
                        ocr_texts.append(
                            f"\n--- OCR IMAGE {img_index+1} ---\n{ocr_text.strip()}"
                        )

                # Combine text + OCR text
                full_page_text = text_content + "\n".join(ocr_texts)

                # Create LangChain Document
                docs.append(
                    Document(
                        page_content=full_page_text,
                        metadata={"pages": i + 1, "filename": filename},
                    )
                )

            self.documents = docs

    def get_document(self):
        return self.documents

    def get_full_content(self):
        res = ""
        for item in self.documents:
            res += " " + item.page_content
        return res

