from pydantic import BaseModel

class UploadResult(BaseModel):
    org_document_id: int
    total_chunks: int
    faiss_added: int
    message: str
