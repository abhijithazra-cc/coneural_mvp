from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query,WebSocket,BackgroundTasks
from app.schemas.request_schema import AskRequest,AskRequestOnDocument
from sqlalchemy.orm import Session
from sqlalchemy import select
import os
from pydantic import BaseModel,Field
from app.database import get_db
from app.services.auth import get_current_active_user,get_current_active_socket_user
from app.models.user_model import User as UserModel
from app.models.user_access_department_model import UserAccessDepartment
from app.models.department_model import Department as DepartmentModel
from app.models.doc_models import DocChunk                   #  from doc_models
# from app.models.org_document_model import OrgDocument       #  from org_document_model
from app.models.doc_models import OrgDocument
from app.utils.embeddings import embed_texts
from app.models.chat_thread_model import ChatThreads
from fastapi.responses import StreamingResponse
# from app.utils.faiss_manager import FaissManager
from app.Rag.utils import embeddings,llm,BASE_DIR,retriever
from app.Rag.VectorManager import vectorManager
from langchain_classic.retrievers.ensemble import EnsembleRetriever
from typing import Dict, List
from langchain_classic.text_splitter import CharacterTextSplitter
from app.Rag.HighlightText import HighlightText
from app.models.chat_messages_model import ChatMessage
router = APIRouter(prefix="/uq", tags=["unanswer_panel"])

def _response_unanswered_question(c:ChatMessage):
    return{
        "id":c.id,
        "unanswer_question":c.query,
        "org_id":c.org_id,
        "user_id":c.user_id,
        "date":c.created_at
    }
    

def _all_unanswered_question(db:Session):
    unq=db.query(ChatMessage).filter(ChatMessage.unanswer_query==1).all()

    return [_response_unanswered_question(item) for item in unq ]

@router.get("/get_unanswered_questions")
def get_unanswered_questions(db: Session = Depends(get_db)):
    items=_all_unanswered_question(db)
    return {"response":items}
