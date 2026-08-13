"""
vectorstore_config.py
======================
Reads which vectorstore backend to use, and that backend's settings,
purely from the environment (.env). This is the ONLY place backend
selection happens — nothing else in the app should hardcode "pinecone" /
"qdrant" / "faiss".

.env keys
---------
VECTORSTORE_BACKEND=pinecone            # "faiss" | "pinecone" | "qdrant"  (required)
VECTORSTORE_EMBEDDING_DIM=1536

# faiss only
FAISS_BASE_DIR=vectorstores/orgs

# pinecone only
PINECONE_ISOLATION=namespace            # "index" | "namespace"
PINECONE_SHARED_INDEX_NAME=org-shared   # used only when isolation=namespace
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
# PINECONE_API_KEY read directly by PineconeVectorstore itself

# qdrant only
QDRANT_ISOLATION=payload                # "collection" | "payload"
QDRANT_SHARED_COLLECTION_NAME=org_shared
# QDRANT_URL / QDRANT_API_KEY read directly by QdrantVectorstore itself
"""

import os

from app.Rag.VectorstoreFactory import VectorstoreFactory


def build_factory_from_env() -> VectorstoreFactory:
    backend = os.environ.get("VECTORSTORE_BACKEND", "").strip().lower()
    if not backend:
        raise RuntimeError(
            "VECTORSTORE_BACKEND is not set in the environment. "
            "Set it to 'faiss', 'pinecone', or 'qdrant' in your .env."
        )

    embedding_dim = int(os.environ.get("VECTORSTORE_EMBEDDING_DIM", "1536"))

    if backend == "faiss":
        return VectorstoreFactory(
            "faiss",
            base_dir=os.environ.get("FAISS_BASE_DIR", "vectorstores/orgs"),
            embedding_dim=embedding_dim,
        )

    if backend == "pinecone":
        return VectorstoreFactory(
            "pinecone",
            isolation=os.environ.get("PINECONE_ISOLATION", "index"),
            shared_index_name=os.environ.get(
                "PINECONE_SHARED_INDEX_NAME", "org-shared"
            ),
            embedding_dim=embedding_dim,
            cloud=os.environ.get("PINECONE_CLOUD", "aws"),
            region=os.environ.get("PINECONE_REGION", "us-east-1"),
        )

    if backend == "qdrant":
        return VectorstoreFactory(
            "qdrant",
            isolation=os.environ.get("QDRANT_ISOLATION", "collection"),
            shared_collection_name=os.environ.get(
                "QDRANT_SHARED_COLLECTION_NAME", "org_shared"
            ),
            embedding_dim=embedding_dim,
        )

    raise RuntimeError(
        f"Unknown VECTORSTORE_BACKEND='{backend}'. Must be 'faiss', 'pinecone', or 'qdrant'."
    )


def configure_vector_manager():
    """Call once at app startup (e.g. in main.py's startup event / lifespan).
    Builds the env-selected factory and binds it to the VectorManager
    singleton so every request downstream just calls get_vector_manager()
    without knowing or caring which backend is active."""
    from app.Rag.VectorManager import get_vector_manager
    from app.Rag.utils import embeddings

    manager = get_vector_manager()
    manager.factory = build_factory_from_env()
    manager.embeddings = embeddings
    return manager
