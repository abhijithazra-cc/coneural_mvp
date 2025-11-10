import threading
from typing import Dict
  # your class above
from Rag.FaissVectorstore import FaissVectorstore

class VectorManager:
    """
    Singleton registry that stores and manages multiple FaissVectorManager objects.
    Each unique persist_dir corresponds to one FAISS store instance.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(VectorManager, cls).__new__(cls)
                    cls._instance._stores: Dict[str, FaissVectorstore] = {}
        return cls._instance

    def get_store(self, embeddings,persist_dir: str) -> FaissVectorstore:
        """
        Returns an existing FaissVectorManager for the given persist_dir,
        or creates and caches one if it doesn’t exist yet.
        """
        if persist_dir not in self._stores:
            print(f"🆕 Creating new FAISS vector store for: {persist_dir}")
            self._stores[persist_dir] = FaissVectorstore(embeddings=embeddings,persist_dir=persist_dir)
            self._stores[persist_dir]=self._stores[persist_dir]._load_or_create_store()
        else:
            print(f"♻️ Reusing existing FAISS vector store for: {persist_dir}")
        return self._stores[persist_dir]

    def list_stores(self):
        """List all active FAISS vector store paths."""
        return list(self._stores.keys())

    def remove_store(self, persist_dir: str):
        """
        Removes a FAISS store from memory (does not delete its files).
        You can call FaissVectorManager.delete_by_doc_id separately to clear vectors.
        """
        if persist_dir in self._stores:
            del self._stores[persist_dir]
            print(f"🗑️ Removed FAISS store from memory: {persist_dir}")

vectorManager=VectorManager()