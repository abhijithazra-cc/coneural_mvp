# Import all models so SQLAlchemy sees every table before create_all()

from .organization_model import Organization              # __tablename__ = "organizations"
from .department_model import  Department       # __tablename__ = "Departments"
from .user_model import User                  # __tablename__ = "users"
from .doc_models import OrgDocument, DocChunk             # __tablename__ = "org_documents", "doc_chunks"
from .user_access_department_model import UserAccessDepartment                # __tablename__ = "user_domain_access"
from .chat_thread_model import ChatThreads
from .chat_messages_model import ChatMessage                  # __tablename__ = "chat_messages"
from .department_licenses_model import DepartmentLicenses
from .user_licenses_model import UserLicenses
# from .user_password_history_model import UserPasswordHistory
__all__ = [
    "Organization",
    "Department",
    "User", "UserType",
    "OrgDocument", 
    "DocChunk",
    "UserAccessDepartment",
    "ChatMessage",
    "ChatThreads",
    "UserLicenses",
    "DepartmentLicenses",
    "UserPasswordHistory",
]
