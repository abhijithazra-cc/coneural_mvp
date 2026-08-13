"""
PineconeVectorstore (pure pinecone-client — no langchain_pinecone)
====================================================================
`langchain_pinecone` split dense (`PineconeVectorStore`) and sparse
(`PineconeSparseEmbeddings` / `PineconeSparseVectorStore`) into separate,
unrelated classes with no built-in fusion — unlike Qdrant's
`RetrievalMode.HYBRID`, there's no single LangChain wrapper that does
dense+sparse hybrid Pinecone search in one call.

The raw `pinecone` SDK, on the other hand, already supports this natively
at the index level: a single `dotproduct` index stores BOTH `values`
(dense) and `sparse_values` (sparse) per record, and a single `index.query()`
call can search both at once. That's the actual "single implementation"
equivalent to Qdrant here — so this version drops `langchain_pinecone`
entirely and talks to the raw `pinecone` client directly:

  - Dense embeddings   -> self.embeddings (bring-your-own LangChain
                          Embeddings object, injected by the caller — same
                          pattern as Faiss/Qdrant, NOT langchain_pinecone)
  - Sparse embeddings  -> pc.inference.embed(model="pinecone-sparse-english-v0")
                          via Pinecone's raw Inference API (no wrapper class)
  - Storage/query      -> self.index.upsert(...) / self.index.query(...)
                          (raw pinecone.Index, no PineconeVectorStore)

Interface contract (kept identical across Faiss/Qdrant/Pinecone):
  - get_vector_store() -> self
  - as_retriever(search_type, search_kwargs={"k":..., "filter": {...}}) -> object with .invoke(input=query)
  - search_chunks(query, k, dept_id=None, document_id=None, score_threshold=None) -> list[(doc, score)]
  - filter values may be a single value OR {"$in": [...]} OR a plain list — all three are honored.

`as_retriever` is kept as a thin wrapper around `search_chunks` (same shape
as the fixed Faiss implementation) rather than delegating to a vectorstore's
native `.as_retriever()` — there's no LangChain vectorstore object left to
delegate to, and this keeps all three backends structurally identical:
callers always get a `_BoundRetriever.invoke(query)` that internally calls
the backend's own `search_chunks`.
"""

import os
import re
import uuid
from datetime import datetime

from app.Rag.abstractions.IVectorstore import IVectorstore
from pinecone import Pinecone, ServerlessSpec
from langchain_core.documents import Document

SPARSE_MODEL = "pinecone-sparse-english-v0"


class _BoundRetriever:
    def __init__(self, search_fn):
        self._search_fn = search_fn

    def invoke(self, input=None, query=None, **kwargs):
        q = input if input is not None else query
        return self._search_fn(q)


class PineconeVectorstore(IVectorstore):

    def __init__(
        self,
        embeddings,
        org_id: str,
        isolation: str = "index",  # "index" | "namespace"
        shared_index_name: str = "org-shared",
        embedding_dim: int = 1536,
        metric: str | None = None,
        cloud: str = "aws",
        region: str = "us-east-1",
        score_threshold: float = 0.75,
        api_key: str | None = None,
        enable_bm25: bool = True,  # toggle sparse + dense alpha-weighted hybrid
        alpha: float = 0.5,        # 1.0 = pure dense, 0.0 = pure sparse
    ):
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required — every Pinecone store belongs to exactly one org")
        if isolation not in ("index", "namespace"):
            raise ValueError("isolation must be 'index' or 'namespace'")

        self.vectorstore_type = "pinecone"
        self.org_id = org_id
        self.isolation = isolation
        # Bring-your-own dense embeddings — any LangChain-compatible
        # Embeddings object. This is NOT langchain_pinecone; it's the same
        # injected-dependency pattern Faiss/Qdrant already use.
        self.embeddings = embeddings
        self.embedding_dim = embedding_dim
        self.cloud = cloud
        self.region = region
        self.score_threshold = score_threshold
        self.enable_bm25 = enable_bm25
        self.alpha = alpha
        self.metric = metric or ("dotproduct" if self.enable_bm25 else "cosine")

        sanitized = self._sanitize(org_id)
        if isolation == "index":
            self.index_name = f"org-{sanitized}"[:45]
            self.namespace = "default"
        else:
            self.index_name = shared_index_name
            self.namespace = sanitized

        self.pc = Pinecone(api_key=api_key or os.environ["PINECONE_API_KEY"])
        # Raw pinecone.Index client only — no LangChain vectorstore wrapper
        # of any kind sits in front of it.
        self.index = None

    @staticmethod
    def _sanitize(org_id: str) -> str:
        return re.sub(r"[^a-z0-9-]", "-", org_id.strip().lower())

    def _load_or_create_index(self):
        if self.index is not None:
            return self.index
        existing = [i["name"] for i in self.pc.list_indexes()]
        if self.index_name not in existing:
            self.pc.create_index(
                name=self.index_name, dimension=self.embedding_dim, metric=self.metric,
                spec=ServerlessSpec(cloud=self.cloud, region=self.region),
            )
        self.index = self.pc.Index(self.index_name)
        return self.index

    def set_vector_store(self, docs, embeddings):
        self._load_or_create_index()

    def get_vector_store(self):
        return self

    def provision(self):
        self._load_or_create_index()
        print(
            f"✅ Provisioned Pinecone store for org_id={self.org_id} "
            f"(index={self.index_name}, namespace={self.namespace}, metric={self.metric}, bm25={self.enable_bm25})"
        )

    @staticmethod
    def _hybrid_scale(dense: list[float], sparse_indices: list[int], sparse_values: list[float], alpha: float):
        hs = {"indices": sparse_indices, "values": [v * (1 - alpha) for v in sparse_values]}
        hd = [v * alpha for v in dense]
        return hd, hs

    # ---------- Raw Pinecone Inference API — no langchain_pinecone wrapper ----------
    def _embed_sparse(self, texts: list[str], input_type: str) -> list[tuple[list[int], list[float]]]:
        """input_type: 'passage' for documents being upserted, 'query' for search queries."""
        result = self.pc.inference.embed(
            model=SPARSE_MODEL,
            inputs=texts,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        out = []
        for item in result.data:
            # EmbeddingsList entries support both attribute and dict-style access
            # depending on SDK version — normalize defensively.
            indices = item["sparse_indices"] if isinstance(item, dict) else item.sparse_indices
            values = item["sparse_values"] if isinstance(item, dict) else item.sparse_values
            out.append((list(indices), list(values)))
        return out

    # ---------- Add documents ----------
    def add_documents(self, documents, document_id, dept_id):
        index = self._load_or_create_index()
        now = datetime.now()
        for c in documents:
            c.metadata.update({
                "document_id": document_id,
                "dept_id": dept_id,
                "org_id": self.org_id,
                "date_time": now.isoformat(),
            })

        texts = [c.page_content for c in documents]
        dense_vecs = self.embeddings.embed_documents(texts)
        sparse_pairs = self._embed_sparse(texts, "passage") if self.enable_bm25 else [(None, None)] * len(texts)

        vectors = []
        for text, dense, (indices, values), c in zip(texts, dense_vecs, sparse_pairs, documents):
            meta = dict(c.metadata)
            meta["page_content"] = text
            vec = {"id": str(uuid.uuid4()), "values": dense, "metadata": meta}
            if self.enable_bm25:
                vec["sparse_values"] = {"indices": indices, "values": values}
            vectors.append(vec)

        BATCH = 100
        for i in range(0, len(vectors), BATCH):
            index.upsert(vectors=vectors[i:i + BATCH], namespace=self.namespace)

        print(f"✅ Added {len(documents)} chunks (org_id={self.org_id}, document_id={document_id})")

    def get_document_ids(self):
        index = self._load_or_create_index()
        zero_vector = [0.0] * self.embedding_dim
        result = index.query(
            vector=zero_vector, top_k=10000, namespace=self.namespace,
            include_metadata=True, include_values=False,
        )
        return sorted({
            m["metadata"].get("document_id")
            for m in result.get("matches", [])
            if m.get("metadata") and m["metadata"].get("document_id") is not None
        })

    # ---------- Similarity check ----------
    def is_similar_document(self, chunks) -> bool:
        index = self._load_or_create_index()
        if not chunks:
            return False
        sample = chunks[:3] + chunks[-2:] if len(chunks) > 5 else chunks
        full_doc = "\n".join(c.page_content for c in sample)

        dense_vec = self.embeddings.embed_query(full_doc)
        query_kwargs = dict(
            vector=dense_vec, top_k=1, namespace=self.namespace,
            include_metadata=False, include_values=False,
        )
        if self.enable_bm25:
            indices, values = self._embed_sparse([full_doc], "query")[0]
            hd, hs = self._hybrid_scale(dense_vec, indices, values, self.alpha)
            query_kwargs["vector"] = hd
            query_kwargs["sparse_vector"] = hs

        result = index.query(**query_kwargs)
        matches = result.get("matches", [])
        if not matches:
            return False
        score = matches[0]["score"]
        print(f"[is_similar_document] org_id={self.org_id} similarity score: {score:.4f}")
        return {"status": "duplicate", "score": score} if score > 0.85 else False

    # ---------- Filter helper: honors single value, {"$in": [...]}, and plain list ----------
    @staticmethod
    def _filter_value(value):
        if isinstance(value, dict) and "$in" in value:
            return {"$in": value["$in"]}
        if isinstance(value, list):
            return {"$in": value}
        return {"$eq": value}

    def _build_pinecone_filter(self, dept_id=None, document_id=None) -> dict | None:
        pinecone_filter = {}
        if dept_id is not None:
            pinecone_filter["dept_id"] = self._filter_value(dept_id)
        if document_id is not None:
            pinecone_filter["document_id"] = self._filter_value(document_id)
        return pinecone_filter or None

    # ---------- Primary retrieval (dense OR dense+sparse hybrid, filters always applied) ----------
    def search_chunks(
        self,
        query: str,
        k: int = 5,
        dept_id=None,
        document_id=None,
        score_threshold: float | None = None,
    ) -> list:
        index = self._load_or_create_index()
        threshold = score_threshold if score_threshold is not None else self.score_threshold
        pinecone_filter = self._build_pinecone_filter(dept_id, document_id)

        dense_vec = self.embeddings.embed_query(query)
        query_kwargs = dict(
            top_k=k, namespace=self.namespace, filter=pinecone_filter,
            include_metadata=True, include_values=False,
        )

        if self.enable_bm25:
            indices, values = self._embed_sparse([query], "query")[0]
            hd, hs = self._hybrid_scale(dense_vec, indices, values, self.alpha)
            query_kwargs["vector"] = hd
            query_kwargs["sparse_vector"] = hs
            mode = "hybrid"
        else:
            query_kwargs["vector"] = dense_vec
            mode = "dense"

        result = index.query(**query_kwargs)

        filtered = []
        for m in result.get("matches", []):
            score = m["score"]
            if score < threshold:
                continue
            meta = dict(m.get("metadata") or {})
            page_content = meta.pop("page_content", "")
            # id= kept for parity with Faiss (docstore id) / Qdrant (point id) —
            # native LangChain retrievers on those backends also surface it.
            filtered.append((Document(id=m.get("id"), page_content=page_content, metadata=meta), score))

        print(f"[search_chunks:{mode}] org_id={self.org_id} query='{query[:60]}' | after_filter={len(filtered)}")
        return filtered

    # ---------- LangChain-shaped retriever wrapper (SAME across all 3 backends) ----------
    def as_retriever(self, search_type="similarity", search_kwargs=None):
        search_kwargs = search_kwargs or {}
        k = int(search_kwargs.get("k", 5))
        raw_filter = search_kwargs.get("filter", {}) or {}
        dept_id = raw_filter.get("dept_id")
        document_id = raw_filter.get("document_id")
        score_threshold = search_kwargs.get("score_threshold")

        def _search(query):
            results = self.search_chunks(
                query=query,
                k=k,
                dept_id=dept_id,
                document_id=document_id,
                score_threshold=score_threshold,
            )
            return [doc for doc, _ in results]

        return _BoundRetriever(_search)

    # ---------- Delete document + its chunks ----------
    def delete_document_by_id(self, document_id: str):
        index = self._load_or_create_index()
        try:
            index.delete(filter={"document_id": {"$eq": document_id}}, namespace=self.namespace)
            print(f"🗑️ Deleted chunks for org_id={self.org_id}, document_id={document_id}")
            return
        except Exception as e:
            print(f"⚠️ Filter delete unsupported ({e}) — falling back to id-based delete...")

        zero_vector = [0.0] * self.embedding_dim
        result = index.query(
            vector=zero_vector, top_k=10000, namespace=self.namespace,
            filter={"document_id": {"$eq": document_id}}, include_metadata=False, include_values=False,
        )
        ids_to_delete = [m["id"] for m in result.get("matches", [])]
        if not ids_to_delete:
            print(f"⚠️ No chunks found for document_id={document_id}")
            return
        index.delete(ids=ids_to_delete, namespace=self.namespace)
        print(f"🗑️ Deleted {len(ids_to_delete)} chunks for document_id={document_id}")