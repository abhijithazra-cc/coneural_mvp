from langchain_openai.embeddings import OpenAIEmbeddings
from app.Rag.OpenaiModel import OpenaiModel
# from app.Rag.GeminiModel import GeminiFlashModel
import os
from app.Rag.Retriever import Retriever
from app.Rag.GeminiModel import GeminiFlashModel
retriever=Retriever()
BASE_DIR="vectorstores/org"
embeddings=OpenAIEmbeddings(api_key=os.getenv('OPENAI_API_KEY'),model='text-embedding-3-small')
llm_openai=OpenaiModel()
llm_gemini=GeminiFlashModel()
# file_utils.py
from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md",
    ".mp3", ".wav", ".aac",
    ".avif", ".bmp", ".gif", ".ico", ".jp2",
    ".png", ".webp", ".tif", ".tiff",
    ".heic", ".heif", ".jpeg", ".jpg", ".jpe"
}

MIME_MAP = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jp2": "image/jp2",
}

import os

def validate_upload_file(file: UploadFile):
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed."
        )

    # expected_mime = MIME_MAP.get(ext)

    # if expected_mime and expected_mime not in file.content_type:
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Invalid MIME type '{file.content_type}'. Expected '{expected_mime}'."
    #     )

    return True
from html.parser import HTMLParser
from typing import List

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.texts.append(text)

def extract_text_only_from_html(html_response: List[dict]) -> str:
    result = []

    for item in html_response:
        parser = TextExtractor()
        parser.feed(item["content"])
        result.append(" ".join(parser.texts))

    return " ".join(result)
