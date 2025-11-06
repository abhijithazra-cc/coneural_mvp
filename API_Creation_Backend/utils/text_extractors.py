# utils/text_extractors.py
from typing import Optional
from Rag import *
import os
from Rag.ai import embeddings ,loader,splitter,vectorStore,retriever,llm

def extract_full_text(pages_data):
    """
    Combine page_content from all pages into a single text string.
    
    Args:
        pages_data (list): List of dictionaries (each with 'page_content' key)
    
    Returns:
        str: Combined text from all pages
    """
    if not isinstance(pages_data, list):
        raise ValueError("Input must be a list of page data objects.")
    
    res=""
    for item in pages_data:
        res+=" "+item.page_content

    return res

def extract_text(file_bytes: bytes, filename: str, mimetype: Optional[str]) -> str:
    """
    Extracts text from common file types: PDF, DOCX, TXT.
    Falls back to UTF-8 decode if extractors fail.
    """
    name = (filename or "").lower()
    mt = (mimetype or "").lower()

    try:
        # print("hi")
        with open(f"{name}", "wb") as f:
            f.write(file_bytes)
        file_path=os.path.abspath(name)
    
        loader.load_document(file_path)
        docs=loader.get_document()
        # print(docs)
        content=extract_full_text(docs)
        # print("content",content)
        return content,docs

    except Exception:
        return file_bytes.decode("utf-8", errors="ignore")
# def extract_text(file_bytes: bytes, filename: str, mimetype: Optional[str]) -> str:
#     """
#     Extracts text from common file types: PDF, DOCX, TXT.
#     Falls back to UTF-8 decode if extractors fail.
#     """
#     name = (filename or "").lower()
#     mt = (mimetype or "").lower()

#     try:
#         # PDF
#         if name.endswith(".pdf") or "pdf" in mt:
#             try:
#                 import fitz  # PyMuPDF (best)
#                 from io import BytesIO
#                 doc = fitz.open(stream=file_bytes, filetype="pdf")
#                 return "\n".join(p.get_text("text") for p in doc)
#             except Exception:
#                 try:
#                     from pypdf import PdfReader
#                     from io import BytesIO
#                     reader = PdfReader(BytesIO(file_bytes))
#                     return "\n".join((p.extract_text() or "") for p in reader.pages)
#                 except Exception:
#                     pass

#         # DOCX
#         if name.endswith(".docx") or "officedocument.wordprocessingml.document" in mt:
#             try:
#                 import docx
#                 from io import BytesIO
#                 d = docx.Document(BytesIO(file_bytes))
#                 return "\n".join(p.text for p in d.paragraphs)
#             except Exception:
#                 pass

#         # Plain text-like
#         return file_bytes.decode("utf-8", errors="ignore")

#     except Exception:
#         return file_bytes.decode("utf-8", errors="ignore")
