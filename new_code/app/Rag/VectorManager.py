"""
VectorManager
=============
org_id-first, backend-agnostic registry of vector stores.

Every public method takes org_id — never a raw path/index/collection name —
so "which org am I operating on" is structurally impossible to omit,
regardless of whether the configured factory builds FAISS, Pinecone, or
Qdrant underneath. Each backend's own constructor (see FaissVectorstore /
PineconeVectorstore / QdrantVectorstore) is what actually turns org_id into
a directory / index / collection — VectorManager just routes by org_id and
caches the resulting instance.
"""

import logging
import threading
from typing import Dict, Optional

from langsmith import traceable

from app.Rag.abstractions.IVectorstore import IVectorstore
from app.Rag.VectorstoreFactory import VectorstoreFactory
from app.Rag.utils import embeddings as default_embeddings

logger = logging.getLogger(__name__)


class VectorManager:
    """Singleton registry, keyed by org_id, bound to ONE backend factory.

    NOTE: this remains a process-wide singleton bound to a single factory —
    if you need two backends live simultaneously (e.g. some orgs on
    Pinecone, some on Qdrant), see the multi-backend note at the bottom of
    this file before reaching for two VectorManager() calls.
    """

    _instance: Optional["VectorManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        factory: Optional[VectorstoreFactory] = None,
        embeddings=None,
    ):
        if self._initialized:
            return
        self._initialized = True

        self.embeddings = embeddings or default_embeddings
        self.factory = factory or VectorstoreFactory("faiss")

        self._stores: Dict[str, IVectorstore] = {}   # key: normalized org_id
        self._stores_lock = threading.RLock()

    # ---------- Key derivation ----------
    @staticmethod
    def _key(org_id: str) -> str:
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required and cannot be empty")
        return org_id.strip().lower()

    # ---------- Org lifecycle ----------
    def create_organization(self, org_id: str) -> IVectorstore:
        """Call this from your 'organization created' workflow (signup,
        admin console, provisioning API — wherever a new org first comes
        into existence in your system). Eagerly builds the org's store so
        it exists before anyone tries to upload a document, rather than
        being silently created on first use."""
        key = self._key(org_id)
        with self._stores_lock:
            if key in self._stores:
                logger.info("Organization already provisioned: %s", org_id)
                return self._stores[key]

            logger.info("Provisioning new vector store for organization: %s", org_id)
            store = self.factory.build(self.embeddings, org_id)
            if hasattr(store, "provision"):
                store.provision()
            self._stores[key] = store
            return store

    def delete_organization(self, org_id: str):
        """Call this from your 'organization deleted' workflow. Wipes the
        org's data at the backend level (not just from the in-memory
        cache) if the backend supports it."""
        key = self._key(org_id)
        with self._stores_lock:
            store = self._stores.get(key) or self.factory.build(self.embeddings, org_id)
            if hasattr(store, "delete_organization"):
                store.delete_organization()
            else:
                logger.warning(
                    "Backend %s has no delete_organization() — remove data manually.",
                    type(store).__name__,
                )
            self._stores.pop(key, None)

    # ---------- Store access ----------
    @traceable(
        name="get_store",
        project="core",
        metadata={"description": "Get or lazily create an org's vector store"},
        tags=["vectorstore"],
    )
    def get_store(self, org_id: str) -> IVectorstore:
        """The single entry point for getting an org's store. Creates it
        on first access if create_organization() was never called
        explicitly (e.g. for orgs that existed before this pattern)."""
        key = self._key(org_id)

        with self._stores_lock:
            if key in self._stores:
                logger.debug("Reusing existing store in memory: org_id=%s", org_id)
                return self._stores[key]

        # Build outside the lock (can be slow — disk IO / network), then
        # publish under the lock, double-checking in case another thread
        # raced us to create the same org's store.
        store = self.factory.build(self.embeddings, org_id)

        with self._stores_lock:
            if key not in self._stores:
                self._stores[key] = store
            return self._stores[key]

    def list_organizations(self):
        with self._stores_lock:
            return list(self._stores.keys())

    def evict_from_memory(self, org_id: str):
        """Remove from the in-memory cache only — does NOT delete the
        org's data. Use delete_organization() for that."""
        key = self._key(org_id)
        with self._stores_lock:
            if key in self._stores:
                del self._stores[key]
                logger.info("Evicted store from memory: org_id=%s", org_id)


def get_vector_manager() -> VectorManager:
    return VectorManager()

vectorManager=get_vector_manager()

# ---------------------------------------------------------------------------
# Multi-backend note
# ---------------------------------------------------------------------------
# VectorManager() is a singleton bound to ONE factory for the whole process.
# If some orgs need Pinecone and others need Qdrant simultaneously, don't
# call VectorManager() twice with different factories — the second call
# will silently return the first instance (because __init__ short-circuits
# once _initialized is True).
#
# Instead, either:
#   (a) route by org at a layer above VectorManager — look up which backend
#       an org uses (e.g. from your orgs table), then call the matching
#       factory.build(embeddings, org_id) directly, bypassing VectorManager
#       for that case, or
#   (b) tell me and I'll change VectorManager to hold a dict of
#       {backend_name: VectorstoreFactory} and route get_store(org_id) by
#       looking up each org's assigned backend from your database.