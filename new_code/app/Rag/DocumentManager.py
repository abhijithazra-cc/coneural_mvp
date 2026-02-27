import os
import threading
from typing import Dict

import sys
from app.Rag.document_loaders.DocLoader import DocLoader
from pympler import asizeof
from app.Rag.document_loaders.PdfLoader import PdfLoader
from app.Rag.document_loaders.ImageLoader import ImageLoader
from app.Rag.document_loaders.TxtLoader import TxtLoader
from app.Rag.document_loaders.PptLoader import PptLoader
from app.Rag.document_loaders.CsvLoader import CsvLoader
from app.Rag.document_loaders.MarkdownLoader import MarkdownLoader
# from app.Rag.document_loaders import PdfLoader,PptLoader,CsvLoader,ImageLoader,TxtLoader
class DocumentManager:
    """
    Singleton registry that stores and manages multiple FaissVectorstore objects.
    Each unique persist_dir corresponds to one FAISS store instance.
    Automatically reloads existing vector stores from disk on startup.
    """

    _instance = None
    _lock = threading.Lock()
    EXT_TO_HANDLER = {
        ".pdf": PdfLoader,
        ".txt": TxtLoader,
        ".pptx": PptLoader,
        ".ppt": PptLoader,
        ".md": MarkdownLoader,
        ".csv": CsvLoader,
        ".docx": DocLoader,
        # Images
        ".avif": ImageLoader,
        ".bmp": ImageLoader,
        ".gif": ImageLoader,
        ".ico": ImageLoader,
        ".jp2": ImageLoader,
        ".png": ImageLoader,
        ".webp": ImageLoader,
        ".tif": ImageLoader,
        ".tiff": ImageLoader,
        ".heic": ImageLoader,
        ".heif": ImageLoader,
        ".jpeg": ImageLoader,
        ".jpg": ImageLoader,
        ".jpe": ImageLoader,
    }
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DocumentManager, cls).__new__(cls)
                    # cls._instance._stores: Dict[str, FaissVectorstore] = {}
        return cls._instance

    def get_doc_loader(self, extension: str):
        """Return handler instance based on file extension."""
        ext = extension.lower()
        # print("requested extension:", ext)
        handler_class = self.EXT_TO_HANDLER.get(ext)
        # print(handler_class)
        if handler_class is None:
            raise ValueError(f"No handler found for extension '{ext}'")

        return handler_class()
    # --------------------------------------------------------------------------
   


# ✅ Global singleton
# docManager = DocumentManager()
# print("list of existing vector stores",vectorManager.list_stores())
