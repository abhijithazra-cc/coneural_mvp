from abstractions.IVectorstore import IVectorstore
from langchain_community.vectorstores import Chroma

class ChromadbVectorstore():
    def __init__(self, embeddings, persist_dir="vectorstores/org/"):
        self.persist_dir = persist_dir
        self.embeddings = embeddings
        self.vectorstore = Chroma(
            collection_name="my-collection",
            embedding_function=self.embeddings,
            persist_directory=self.persist_dir
        )

    def set_vector_store(self, docs):
        # Add docs to the existing persistent collection
        docs=docs[:1]
        print(f"Adding {len(docs)} chunks to Chroma store...")
        self.vectorstore.add_documents(docs)
        self.vectorstore.persist()
        print("✅ Chroma vector store updated and saved.")

    def get_vector_store(self):
        return self.vectorstore
