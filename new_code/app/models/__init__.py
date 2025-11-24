# Import all models so SQLAlchemy sees every table before create_all()

from .organization_model import Organization              # __tablename__ = "organizations"
from .suborganization_model import Suborganization        # __tablename__ = "suborganizations"
from .user_model import User, UserType                    # __tablename__ = "users"
from .doc_models import OrgDocument, DocChunk             # __tablename__ = "org_documents", "doc_chunks"
from .access_model import UserDomainAccess                # __tablename__ = "user_domain_access"
from .user_thread_model import UserThreads
from .user_chat_model import ChatMessage                  # __tablename__ = "chat_messages"

__all__ = [
    "Organization",
    "Suborganization",
    "User", "UserType",
    "OrgDocument", 
    "DocChunk",
    "UserDomainAccess",
    "ChatMessage"
    "UserThreads"
]
