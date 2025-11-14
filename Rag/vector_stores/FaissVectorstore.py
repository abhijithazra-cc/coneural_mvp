from Rag.abstractions.IVectorstore import IVectorstore
from langchain_community.vectorstores import FAISS
import os

class FaissVectorstore(IVectorstore):
     # def __init__(self):
     #      self.vectorstre=None

     # def set_vector_store(self,docs,embeddings):
          
     #      # self.vectorstore = FAISS.from_documents(docs, embeddings)
     #      self.vectorstore = FAISS.from_documents(docs, embeddings)
          
         
     #    #   val=self.vectorstore.as_retriever()
     #    #   val._get_relevant_documents()
     # def get_vector_store(self):
     #      return self.vectorstore
    def __init__(self,embeddings,persist_dir="vectorstores\org"):
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        self.embeddings = embeddings
        self.vectorstore = None
        self.doc_id_list=[]
     
    # ---------- Load or create ----------
    def _load_or_create_store(self):
        if self.vectorstore is None and os.path.exists(
            os.path.join(self.persist_dir, "index.faiss")
        ):
            self.vectorstore = FAISS.load_local(
                self.persist_dir,
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
        elif self.vectorstore is None:
            self.vectorstore = FAISS.from_texts(["init"], self.embeddings)
            self.vectorstore.save_local(self.persist_dir)
        return self.vectorstore
    def set_vector_store(self,docs, embeddings):
        self.vectorstore= self._load_or_create_store()
        
    def get_vector_store(self):
        return self.vectorstore
    # ---------- Add documents ----------
    def add_documents(self, documents,doc_id):
            store = self._load_or_create_store()
            # assign doc_id metadata for deletion tracking
          #   doc_id = str(uuid.uuid4())
            for c in documents:
                c.metadata["doc_id"] = doc_id
            self.doc_id_list.append(doc_id)

            store.add_documents(documents=documents)
            print(f"✅ Added {len(documents)} chunks (doc_id={doc_id})")

            store.save_local(self.persist_dir)
            self.vectorstore = store
    def get_document_ids(self):
        return self.doc_id_list
    # ---------- Fetch chunks for one document ----------
    def get_chunks_by_doc_id(self, doc_id: str):
        store = self._load_or_create_store()
        docs = [
            doc for doc in store.docstore._dict.values()
            if doc.metadata.get("doc_id") == doc_id
        ]
        return docs

    # ---------- Delete document + its chunks ----------
    def delete_document_by_id(self, doc_id: str):
        store = self._load_or_create_store()
        # find matching IDs in FAISS index
        ids_to_delete = [
            id_ for id_, doc in store.docstore._dict.items()
            if doc.metadata.get("doc_id") == doc_id
        ]
        print("deleted ids",ids_to_delete)
        if not ids_to_delete:
            print(f"⚠️ No chunks found for doc_id={doc_id}")
            return
        store.delete(ids=ids_to_delete)
        store.save_local(self.persist_dir)
        print(f"🗑️ Deleted {len(ids_to_delete)} chunks for doc_id={doc_id}")
