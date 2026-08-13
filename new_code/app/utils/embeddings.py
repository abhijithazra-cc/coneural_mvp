# app/utils/embeddings.py

import os
from typing import List

import numpy as np
from openai import OpenAI

# Use env var; set in .env or server environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# Model & dimension: text-embedding-3-small → 1536 dims
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-large")
EMBED_DIM = 3072




def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Given a list of texts, return a numpy float32 array of shape (N, EMBED_DIM).
    """
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype="float32")

    # OpenAI API call
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )

    vectors = [item.embedding for item in resp.data]
    arr = np.array(vectors, dtype="float32")
    if arr.shape[1] != EMBED_DIM:
        # Adjust if you change model / dimension
        raise RuntimeError(f"Unexpected embedding dimension {arr.shape[1]} != {EMBED_DIM}")
    return arr
