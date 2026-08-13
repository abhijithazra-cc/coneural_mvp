"""
QdrantVectorstore (LangChain-native)
======================================
Uses langchain_qdrant.QdrantVectorStore instead of raw qdrant_client
calls for storage/search. Hybrid dense+BM25 is handled by
RetrievalMode.HYBRID, which runs the same server-side prefetch + RRF
fusion under the hood that the raw version did manually.

We still keep the raw QdrantClient around for collection setup,
org-scoped scroll/delete, and payload-index creation — LangChain's
wrapper doesn't expose those admin operations.

Interface contract (kept identical across Faiss/Qdrant/Pinecone):
  - get_vector_store() -> self
  - as_retriever(search_type, search_kwargs={"k":..., "filter": {...}}) -> object with .invoke(input=query)
  - search_chunks(query, k, dept_id=None, document_id=None, score_threshold=None) -> list[(doc, score)]
  - filter values may be a single value OR {"$in": [...]} OR a plain list — all three are honored.
"""

import os
import re
from datetime import datetime

from langsmith import traceable

from app.Rag.abstractions.IVectorstore import IVectorstore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_core.documents import Document


class _BoundRetriever:
    def __init__(self, search_fn):
        self._search_fn = search_fn

    def invoke(self, input=None, query=None, **kwargs):
        q = input if input is not None else query
        return self._search_fn(q)


class QdrantVectorstore(IVectorstore):

    def __init__(
        self,
        embeddings,
        org_id: str,
        isolation: str = "collection",         # "collection" | "payload"
        shared_collection_name: str = "org_shared",
        embedding_dim: int = 1536,
        distance: qmodels.Distance = qmodels.Distance.COSINE,
        score_threshold: float = 0.75,
        url: str | None = None,
        api_key: str | None = None,
        enable_bm25: bool = True,   # toggle RetrievalMode.HYBRID vs DENSE
    ):
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required — every Qdrant store belongs to exactly one org")
        if isolation not in ("collection", "payload"):
            raise ValueError("isolation must be 'collection' or 'payload'")

        self.vectorstore_type = "qdrant"
        self.org_id = org_id
        self.isolation = isolation
        self.embeddings = embeddings
        self.embedding_dim = embedding_dim
        self.distance = distance
        self.score_threshold = score_threshold
        self.enable_bm25 = enable_bm25

        sanitized = self._sanitize(org_id)
        self.collection_name = f"org_{sanitized}" if isolation == "collection" else shared_collection_name

        self.client = QdrantClient(
            url=url or os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=api_key or os.environ.get("QDRANT_API_KEY"),
        )
        self._sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25") if enable_bm25 else None
        self._lc_store: QdrantVectorStore | None = None

    @staticmethod
    def _sanitize(org_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "-", org_id.strip().lower())

    def _load_or_create_store(self) -> QdrantVectorStore:
        if self._lc_store is not None:
            return self._lc_store

        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={"dense": qmodels.VectorParams(size=self.embedding_dim, distance=self.distance)},
                sparse_vectors_config=(
                    {"bm25": qmodels.SparseVectorParams(modifier=qmodels.Modifier.IDF)}
                    if self.enable_bm25 else None
                ),
            )
            if self.isolation == "payload":
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="org_id",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )

        self._lc_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            sparse_embedding=self._sparse_embeddings,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name="dense",
            sparse_vector_name="bm25",
        )
        return self._lc_store

    def set_vector_store(self, docs, embeddings):
        self._load_or_create_store()

    def get_vector_store(self):
        return self

    def provision(self):
        self._load_or_create_store()
        print(f"✅ Provisioned Qdrant store for org_id={self.org_id} (collection={self.collection_name}, isolation={self.isolation}, bm25={self.enable_bm25})")

    # ---------- Internal: mandatory org filter ----------
    def _org_condition(self):
        if self.isolation != "payload":
           return None

        return qmodels.FieldCondition(
        key="metadata.org_id",
        match=qmodels.MatchValue(value=str(self.org_id))
        )


    @staticmethod
    def _condition_for(key: str, value):
        qdrant_key = f"metadata.{key}"
        if isinstance(value, list):
           return qmodels.FieldCondition(
            key=qdrant_key,
            match=qmodels.MatchAny(
                any=value
            )
           )
        return qmodels.FieldCondition(
        key=f"metadata.{key}",
        match=qmodels.MatchValue(value=value)
        )


    def _build_filter(self, extra: list) -> qmodels.Filter | None:
        org_cond = self._org_condition()

        conditions = []

        if org_cond:
           conditions.append(org_cond)

        conditions.extend(extra)

        return qmodels.Filter(
        must=conditions
        ) if conditions else None

    # ---------- Add documents ----------
    def add_documents(self, documents, document_id, dept_id):
        store = self._load_or_create_store()
        now = datetime.now()
        for c in documents:
            c.metadata.update({
                "document_id": document_id,
                "dept_id": dept_id,
                "org_id": self.org_id,
                "date_time": now.isoformat(),
            })
        store.add_documents(documents)
        print(f"✅ Added {len(documents)} chunks (org_id={self.org_id}, document_id={document_id})")



    # ---------- LangChain-shaped retriever wrapper (SAME across all 3 backends) ----------
    @traceable(name="as_retriever_qdrant", project="core")
    def as_retriever(self, search_type="similarity", search_kwargs=None):
        store = self._load_or_create_store()
        search_kwargs = search_kwargs or {}
        k = int(search_kwargs.get("k", 5))
        raw_filter = search_kwargs.get("filter", {}) or {}

    # ---- Step 1: Filter Builder ----
        extra = []
        if raw_filter.get("dept_id") is not None:
           extra.append(self._condition_for("dept_id", raw_filter["dept_id"]))
        if raw_filter.get("document_id") is not None:
           extra.append(self._condition_for("document_id", raw_filter["document_id"]))
        qfilter = self._build_filter(extra)   # org_id yahin mandatory inject hota hai

    # ---- Step 2: Native as_retriever call ----
        # return store.as_retriever(search_type=search_type, search_kwargs={"k": k, "filter": qfilter})
        return store.as_retriever(search_type=search_type, search_kwargs={"k": k, "filter": qfilter})


    # ---------- Delete document + its chunks ----------
    def delete_document_by_id(self, document_id: str):
        self._load_or_create_store()
        extra = [self._condition_for("document_id", document_id)]
        qfilter = self._build_filter(extra)
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(filter=qfilter),
        )
        print(f"🗑️ Deleted chunks for org_id={self.org_id}, document_id={document_id} (status={result.status})")
