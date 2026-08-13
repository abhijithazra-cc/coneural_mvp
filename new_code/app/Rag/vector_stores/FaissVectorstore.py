"""
FaissVectorstore (LangChain-native)
=====================================
Same org_id isolation + method contract as the raw version, but hybrid
search now uses LangChain's OWN retriever primitives instead of a
hand-rolled BM25 formula:

  - langchain_community.vectorstores.FAISS        -> dense store
  - langchain_community.retrievers.BM25Retriever   -> in-memory BM25
  - langchain.retrievers.EnsembleRetriever         -> rank-based fusion
    (weighted RRF under the hood) that merges the two result lists

FAISS still has no native sparse index, so BM25Retriever is rebuilt from
the (filtered) in-memory docstore on every hybrid query — fine for small
to medium per-org corpora.

Interface contract (kept identical across Faiss/Qdrant/Pinecone):
  - get_vector_store() -> self
  - as_retriever(search_type, search_kwargs={"k":..., "filter": {...}}) -> object with .invoke(input=query)
  - search_chunks(query, k, dept_id=None, document_id=None, score_threshold=None) -> list[(doc, score)]
  - filter values may be a single value OR {"$in": [...]} OR a plain list — all three are honored.
"""

import os
import re
import shutil
from datetime import datetime

import faiss
from app.Rag.abstractions.IVectorstore import IVectorstore
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers.ensemble import EnsembleRetriever

class _BoundRetriever:
    """Tiny adapter so `.as_retriever(...)` returns something with the same
    `.invoke(input=...)` shape LangChain retrievers expose — keeps the
    app's Retriever() class unaware of which backend it's talking to."""

    def __init__(self, search_fn):
        self._search_fn = search_fn

    def invoke(self, input=None, query=None, **kwargs):
        q = input if input is not None else query
        return self._search_fn(q)


class FaissVectorstore(IVectorstore):

    def __init__(
        self,
        embeddings,
        org_id: str,
        base_dir: str = "vectorstores/orgs",
        embedding_dim: int = 1536,
        hnsw_m: int = 32,
        ef_construction: int = 200,
        ef_search: int = 64,
        score_threshold: float = 0.75,  # L2 distance ceiling (lower = stricter match)
        enable_bm25: bool = True,       # toggle BM25 + dense hybrid via EnsembleRetriever
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
    ):
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required — every FAISS store belongs to exactly one org")

        self.vectorstore_type = "faiss"
        self.org_id = org_id
        self.embeddings = embeddings
        self.embedding_dim = embedding_dim
        self.score_threshold = score_threshold
        self.enable_bm25 = enable_bm25
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight

        self.persist_dir = os.path.join(base_dir, self._sanitize(org_id))
        os.makedirs(self.persist_dir, exist_ok=True)

        self.vectorstore: FAISS | None = None
        self.hnsw_m = hnsw_m
        self.ef_construction = ef_construction
        self.ef_search = ef_search

    @staticmethod
    def _sanitize(org_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "-", org_id.strip().lower())

    def _load_or_create_store(self):
        if self.vectorstore is None and os.path.exists(os.path.join(self.persist_dir, "index.faiss")):
            self.vectorstore = FAISS.load_local(
                self.persist_dir, self.embeddings, allow_dangerous_deserialization=True,
            )
            self.vectorstore.index.hnsw.efSearch = self.ef_search
        elif self.vectorstore is None:
            index = faiss.IndexHNSWFlat(self.embedding_dim, self.hnsw_m)
            index.hnsw.efConstruction = self.ef_construction
            index.hnsw.efSearch = self.ef_search
            self.vectorstore = FAISS(
                embedding_function=self.embeddings,
                index=index,
                docstore=InMemoryDocstore(),
                index_to_docstore_id={},
            )
            self.vectorstore.save_local(self.persist_dir)
        return self.vectorstore

    def set_vector_store(self, docs, embeddings):
        self.vectorstore = self._load_or_create_store()

    def get_vector_store(self):
        return self

    def provision(self):
        self._load_or_create_store()
        print(f"✅ Provisioned FAISS store for org_id={self.org_id} at {self.persist_dir} (bm25={self.enable_bm25})")

    # ---------- Add documents ----------
    def add_documents(self, documents, document_id, dept_id):
        store = self._load_or_create_store()
        now = datetime.now()
        for c in documents:
            c.metadata.update({
                "document_id": document_id,
                "date_time": now.isoformat(),
                "dept_id": dept_id,
                "org_id": self.org_id,
            })
        store.add_documents(documents=documents)
        store.save_local(self.persist_dir)
        self.vectorstore = store
        print(f"✅ Added {len(documents)} chunks (org_id={self.org_id}, document_id={document_id})")

    def get_document_ids(self):
        store = self._load_or_create_store()
        return sorted({
            d.metadata.get("document_id")
            for d in store.docstore._dict.values()
            if d.metadata.get("document_id") is not None
        })

    # ---------- Similarity check ----------
    def is_similar_document(self, chunks) -> bool:
        store = self._load_or_create_store()
        if not chunks:
            return False
        sample = chunks[:3] + chunks[-2:] if len(chunks) > 5 else chunks
        full_doc = "\n".join(c.page_content for c in sample)
        matches = store.similarity_search_with_score(full_doc, k=1)
        if not matches:
            return False
        _, raw_l2 = matches[0]
        score = 1 / (1 + raw_l2)
        print(f"[is_similar_document] org_id={self.org_id} similarity score: {score:.4f}")
        return {"status": "duplicate", "score": score} if score > 0.85 else False

    # ---------- Filter helper: dict -> callable LangChain FAISS accepts ----------
    @staticmethod
    def _to_faiss_filter(filter_dict: dict):
        if not filter_dict:
            return None

        def _match(meta: dict) -> bool:
            for key, val in filter_dict.items():
                v = meta.get(key)
                if isinstance(val, dict) and "$in" in val:
                    if v not in val["$in"]:
                        return False
                elif isinstance(val, list):
                    if v not in val:
                        return False
                elif v != val:
                    return False
            return True

        return _match



    # ---------- LangChain-shaped retriever wrapper (SAME across all 3 backends) ----------
    def as_retriever(self, search_type: str = "similarity", search_kwargs: dict | None = None):
        search_kwargs = search_kwargs or {}
        k = int(search_kwargs.get("k", 5))
        raw_filter = search_kwargs.get("filter", {}) or {}
        document_id = raw_filter.get("document_id")
        dept_id = raw_filter.get("dept_id")

        def _search(query):
            results = self.search_chunks(query=query, k=k, dept_id=dept_id, document_id=document_id)
            return [doc for doc, _ in results]

        return _BoundRetriever(_search)

    # ---------- Fetch chunks for one document ----------
    def get_chunks_by_document_id(self, document_id: str):
        store = self._load_or_create_store()
        return [d for d in store.docstore._dict.values() if d.metadata.get("document_id") == document_id]

    # ---------- Delete document + its chunks ----------
    def delete_document_by_id(self, document_id: str):
        store = self._load_or_create_store()
        ids_to_delete = [
            did for did, d in store.docstore._dict.items()
            if d.metadata.get("document_id") == document_id
        ]
        if not ids_to_delete:
            print(f"⚠️ No chunks found for document_id={document_id}")
            return
        try:
            store.delete(ids=ids_to_delete)
            store.save_local(self.persist_dir)
            self.vectorstore = store
            print(f"🗑️ Deleted {len(ids_to_delete)} chunks for document_id={document_id}")
            return
        except RuntimeError as e:
            if "remove_ids not implemented" not in str(e):
                raise

        print("⚠️ HNSW does not support remove_ids — rebuilding index...")
        surviving = [d for did, d in store.docstore._dict.items() if did not in ids_to_delete]
        if not surviving:
            new_index = faiss.IndexHNSWFlat(self.embedding_dim, self.hnsw_m)
            new_index.hnsw.efConstruction = self.ef_construction
            new_index.hnsw.efSearch = self.ef_search
            self.vectorstore = FAISS(
                embedding_function=self.embeddings,
                index=new_index,
                docstore=InMemoryDocstore(),
                index_to_docstore_id={},
            )
        else:
            texts = [d.page_content for d in surviving]
            metadatas = [d.metadata for d in surviving]
            new_index = faiss.IndexHNSWFlat(self.embedding_dim, self.hnsw_m)
            new_index.hnsw.efConstruction = self.ef_construction
            new_index.hnsw.efSearch = self.ef_search
            self.vectorstore = FAISS.from_texts(texts=texts, embedding=self.embeddings, metadatas=metadatas)
            self.vectorstore.index = new_index

        self.vectorstore.save_local(self.persist_dir)
        print(f"🗑️ Rebuilt index — removed {len(ids_to_delete)} chunks for document_id={document_id}")

