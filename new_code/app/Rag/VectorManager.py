import os
import threading
from typing import Dict
from app.Rag.abstractions.IVectorstore import IVectorstore
from app.Rag.vector_stores.FaissVectorstore import FaissVectorstore  # your class
from app.Rag.utils import BASE_DIR,embeddings
import sys
from pympler import asizeof
class VectorManager:
    """
    Singleton registry that stores and manages multiple FaissVectorstore objects.
    Each unique persist_dir corresponds to one FAISS store instance.
    Automatically reloads existing vector stores from disk on startup.
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

    def deep_sizeof(self,obj):
        size = asizeof.asizeof(obj)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
               return f"{size:.2f} {unit}"
            size /= 1024
    def __init__(self, base_dir: str = BASE_DIR):
        # Only initialize once (avoid overwriting _stores)
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.base_dir = base_dir
            os.makedirs(base_dir, exist_ok=True)
            self._reload_existing_stores()

    # --------------------------------------------------------------------------
   
    def _reload_existing_stores(self):
        "" "Recursively scan base_dir for FAISS indexes and reload them."""
        print("♻️ Reloading existing FAISS vector stores (recursive)...")
        for root, dirs, files in os.walk(self.base_dir):
          if "index.faiss" in files:
            path = root
            print(f"🔄 Found existing FAISS DB: {path}")
            try:
                vstore = FaissVectorstore(embeddings=embeddings, persist_dir=path)
                vstore._load_or_create_store()
                self._stores[path] = vstore
                print(f"store :{path} , size: {sys.getsizeof(vstore)} , deep_size: {self.deep_sizeof(vstore)}")
            except Exception as e:
                print(f"⚠️ Failed to load store at {path}: {e}")

    def create_store(self,embeddings,persist_dir:str)-> FaissVectorstore:
        print(f"🆕 Creating new FAISS vector store at: {persist_dir}")
        os.makedirs(persist_dir, exist_ok=True)
        vstore = FaissVectorstore(embeddings=embeddings, persist_dir=persist_dir)
        vstore._load_or_create_store()
        self._stores[persist_dir] = vstore
    def load_store(self, persist_dir: str) -> FaissVectorstore:
            if os.path.exists(os.path.join(persist_dir, "index.faiss")):
                print(f"♻️ Loading existing FAISS vector store from disk: {persist_dir}")
                vstore = FaissVectorstore(embeddings=embeddings, persist_dir=persist_dir)
                vstore._load_or_create_store()
                self._stores[persist_dir] = vstore
    # --------------------------------------------------------------------------
    def get_store(self, embeddings, persist_dir: str) -> FaissVectorstore:
        """Return an existing or newly created FAISS vector store."""
        # Normalize path
        # if not os.path.isabs(persist_dir):
            # persist_dir = os.path.join( persist_dir)

        if persist_dir not in self._stores:
            if os.path.exists(os.path.join(persist_dir, "index.faiss")):
                print(f"♻️ Loading existing FAISS vector store from disk: {persist_dir}")
                vstore = FaissVectorstore(embeddings=embeddings, persist_dir=persist_dir)
                vstore._load_or_create_store()
                self._stores[persist_dir] = vstore
            else:
                print(f"🆕 Creating new FAISS vector store at: {persist_dir}")
                os.makedirs(persist_dir, exist_ok=True)
                vstore = FaissVectorstore(embeddings=embeddings, persist_dir=persist_dir)
                vstore._load_or_create_store()
                self._stores[persist_dir] = vstore

        else:
            print(f"✅ Reusing existing FAISS store in memory: {persist_dir}")

        return self._stores[persist_dir]

    def set_store(self,persist_dir,store):
        self._stores[persist_dir] = store
    # --------------------------------------------------------------------------
    def list_stores(self):
        """List all loaded FAISS store directories."""
        return list(self._stores.keys())

    def remove_store(self, persist_dir: str):
        """Remove store from memory (not from disk)."""
        if persist_dir in self._stores:
            del self._stores[persist_dir]
            print(f"🗑️ Removed FAISS store from memory: {persist_dir}")

# ✅ Global singleton
vectorManager = VectorManager()
print("list of existing vector stores",vectorManager.list_stores())
