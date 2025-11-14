# utils/embeddings.py
import os
import math
import hashlib
from typing import List

from Rag.utils import embeddings ,splitter

# Embeddings

def generate_embedding(text:str) -> List[float]:
    """
    Generate an embedding for text.
    - Uses OpenAI API if available.
    - Falls back to a deterministic 256-dim pseudo-embedding (hash-based)
      for testing without an API key.
    """
    
    return embeddings.embed_query(text)


# Chunking Text
def chunk_text(docs, max_chars: int = 1200, overlap: int = 150):
    chunks=splitter.split_documents(docs=docs,chunk_size=max_chars,chunk_overlap=overlap)
    return chunks



# Optional OpenAI client

# try:
#     from openai import OpenAI
# except Exception:
#     OpenAI = None

# # Config
# _EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
# _api_key = os.getenv("OPENAI_API_KEY")

# _client = None
# if _api_key and OpenAI:
#     try:
#         _client = OpenAI(api_key=_api_key)
#     except Exception:
#         _client = None



# Helpers

# def _l2norm(v: List[float]) -> List[float]:
#     n = math.sqrt(sum(x * x for x in v)) or 1.0
#     return [x / n for x in v]



# def generate_embedding(text: str) -> List[float]:
#     """
#     Generate an embedding for text.
#     - Uses OpenAI API if available.
#     - Falls back to a deterministic 256-dim pseudo-embedding (hash-based)
#       for testing without an API key.
#     """
#     text = (text or "").strip()
#     if not text:
#         return []

#     # Use OpenAI if available
#     if _client:
#         r = _client.embeddings.create(model=_EMBED_MODEL, input=text)
#         return _l2norm(r.data[0].embedding)

#     # Fallback: 256-dim deterministic embedding
#     h = hashlib.sha256(text.encode("utf-8")).digest()
#     out = []
#     for i in range(256):
#         b = h[i % len(h)]
#         out.append((b - 128) / 128.0)
#     return _l2norm(out)



# Similarity

# def cosine(a: List[float], b: List[float]) -> float:
#     """
#     Cosine similarity between two vectors.
#     Returns 0.0 if vectors are empty.
#     """
#     if not a or not b:
#         return 0.0
#     sa = math.sqrt(sum(x * x for x in a)) or 1.0
#     sb = math.sqrt(sum(y * y for y in b)) or 1.0
#     return sum(x * y for x, y in zip(a, b)) / (sa * sb)



# Chunking

# def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
#     """
#     Simple sliding window chunker.
#     Produces ~1200-char chunks with 150-char overlaps.
#     """
#     if not text:
#         return []
#     text = text.replace("\r", " ")
#     parts, i, n = [], 0, len(text)
#     while i < n:
#         j = min(i + max_chars, n)
#         parts.append(text[i:j])
#         if j >= n:
#             break
#         i = max(j - overlap, 0)
#     return parts[:100]  # safety cap


