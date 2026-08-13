# app/utils/chunking.py

import io
from typing import List

from pypdf import PdfReader
import docx  # python-docx
from app.Rag.text_splitters.CharacterSplitter import CharacterSplitter
from app.Rag.text_splitters.SemanticSplitter import SemanticSplitter
from app.Rag.utils import embeddings 
def extract_text_from_file(
    f: io.BytesIO,
    filename: str,
    mime_type: str,
) -> str:
    """
    Extract raw text from PDF / DOCX / TXT.
    You can extend this for more formats later.
    """
    name_lower = filename.lower()

    if name_lower.endswith(".pdf") or mime_type == "application/pdf":
        reader = PdfReader(f)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    if name_lower.endswith(".docx") or mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        doc = docx.Document(f)
        return "\n".join(p.text for p in doc.paragraphs)

    # fallback: treat as plain text
    data = f.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


# def chunk_text(text: str, max_tokens: int = 600, overlap: int = 120) -> List[str]:
#     """
#     Simple approximate chunking by characters.
#     For production, you can swap this out for a tokenizer-aware chunker.
#     """
#     if not text:
#         return []

#     # Very rough char→token approximation
#     approx_chars_per_token = 4
#     max_chars = max_tokens * approx_chars_per_token
#     overlap_chars = overlap * approx_chars_per_token

#     chunks = []
#     start = 0
#     length = len(text)

#     while start < length:
#         end = min(start + max_chars, length)
#         chunk = text[start:end].strip()
#         if chunk:
#             chunks.append(chunk)
#         if end >= length:
#             break
#         start = max(0, end - overlap_chars)

#     return chunks


def chunk_text(docs, max_tokens: int = 400, overlap: int = 50):
    # splitter=CharacterSplitter(embeddings=embeddings)
    splitter=SemanticSplitter(embeddings=embeddings)
    chunks=splitter.split_documents(docs=docs,chunk_size=max_tokens,chunk_overlap=overlap)
    return chunks