# app/utils/faiss_manager.py

import os
from typing import Dict, Tuple

import faiss
import numpy as np

from app.utils.embeddings import EMBED_DIM

# Where to store FAISS index files
INDEX_DIR = os.getenv("FAISS_INDEX_DIR", "faiss_indexes")
os.makedirs(INDEX_DIR, exist_ok=True)

# In-memory cache so we don't reload from disk every time
_index_cache: Dict[Tuple[int, int], faiss.Index] = {}


def _index_path(org_id: int, dept_id: int) -> str:
    return os.path.join(INDEX_DIR, f"org_{org_id}_sub_{dept_id}.index")


def _create_hnsw_index(dim: int) -> faiss.Index:
    """
    Create a HNSW index for inner product similarity.
    We’ll L2 normalize vectors before adding/searching.
    """
    m = 32  # number of neighbors in graph
    index = faiss.IndexHNSWFlat(dim, m, faiss.METRIC_INNER_PRODUCT)
    # Set some HNSW parameters
    index.hnsw.efConstruction = 128
    index.hnsw.efSearch = 64
    return index


def _load_or_create_index(org_id: int, dept_id: int) -> faiss.Index:
    key = (org_id, dept_id)
    if key in _index_cache:
        return _index_cache[key]

    path = _index_path(org_id, dept_id)
    if os.path.exists(path):
        index = faiss.read_index(path)
    else:
        index = _create_hnsw_index(EMBED_DIM)

    _index_cache[key] = index
    return index


def _save_index(org_id: int, dept_id: int, index: faiss.Index) -> None:
    path = _index_path(org_id, dept_id)
    faiss.write_index(index, path)


def add_vectors(org_id: int, dept_id: int, vectors: np.ndarray, ids: np.ndarray) -> None:
    """
    Add vectors to the FAISS HNSW index for a given (org_id, dept_id).

    - vectors: shape (N, EMBED_DIM), float32
    - ids: shape (N,), int64
    """
    if vectors.size == 0:
        return
    if vectors.shape[0] != ids.shape[0]:
        raise ValueError("vectors and ids must have same length")
    if vectors.shape[1] != EMBED_DIM:
        raise ValueError(f"Expected dim {EMBED_DIM}, got {vectors.shape[1]}")

    index = _load_or_create_index(org_id, dept_id)

    # Normalize for inner-product similarity
    faiss.normalize_L2(vectors)

    # Wrap in an ID index if not already
    if not isinstance(index, faiss.IndexIDMap2):
        # Convert existing index into IDMap2
        id_map = faiss.IndexIDMap2(index)
        index = id_map
        _index_cache[(org_id, dept_id)] = index

    index.add_with_ids(vectors, ids)
    _save_index(org_id, dept_id, index)
