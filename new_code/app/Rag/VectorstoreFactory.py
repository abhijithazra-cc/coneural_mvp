"""
VectorstoreFactory
===================
build(embeddings, org_id) — org_id is now the ONE uniform identifier every
backend builder receives. What each backend does with it is up to that
backend's constructor (FAISS: a subdirectory, Pinecone: an index or
namespace, Qdrant: a collection or payload field) — the factory itself
doesn't need to know or care.
"""

from typing import Callable, Dict

from app.Rag.abstractions.IVectorstore import IVectorstore


class VectorstoreFactory:
    """
    Usage
    -----
    factory = VectorstoreFactory("faiss", base_dir="vectorstores/orgs")
    store = factory.build(embeddings, org_id="acme-corp")

    factory = VectorstoreFactory("pinecone", isolation="namespace", embedding_dim=1536)
    store = factory.build(embeddings, org_id="acme-corp")

    factory = VectorstoreFactory("qdrant", isolation="payload", embedding_dim=1536)
    store = factory.build(embeddings, org_id="acme-corp")
    """

    _registry: Dict[str, Callable[..., IVectorstore]] = {}

    def __init__(self, backend: str, **backend_kwargs):
        if backend not in self._registry:
            available = ", ".join(sorted(self._registry)) or "(none registered)"
            raise ValueError(
                f"Unknown vectorstore backend '{backend}'. Available: {available}"
            )
        self.backend = backend
        self.backend_kwargs = backend_kwargs

    def build(self, embeddings, org_id: str) -> IVectorstore:
        builder = self._registry[self.backend]
        return builder(embeddings, org_id, **self.backend_kwargs)

    def __call__(self, embeddings, org_id: str) -> IVectorstore:
        return self.build(embeddings, org_id)

    @classmethod
    def register(cls, name: str):
        def decorator(builder_fn: Callable[..., IVectorstore]):
            cls._registry[name] = builder_fn
            return builder_fn

        return decorator

    @classmethod
    def available_backends(cls):
        return sorted(cls._registry)


@VectorstoreFactory.register("faiss")
def _build_faiss(embeddings, org_id: str, **kwargs) -> IVectorstore:
    from app.Rag.vector_stores.FaissVectorstore import FaissVectorstore

    return FaissVectorstore(embeddings=embeddings, org_id=org_id, **kwargs)


@VectorstoreFactory.register("pinecone")
def _build_pinecone(embeddings, org_id: str, **kwargs) -> IVectorstore:
    from app.Rag.vector_stores.PineconeVectorstore import PineconeVectorstore

    return PineconeVectorstore(embeddings=embeddings, org_id=org_id, **kwargs)


@VectorstoreFactory.register("qdrant")
def _build_qdrant(embeddings, org_id: str, **kwargs) -> IVectorstore:
    from app.Rag.vector_stores.QdrantVectorstore import QdrantVectorstore

    return QdrantVectorstore(embeddings=embeddings, org_id=org_id, **kwargs)
