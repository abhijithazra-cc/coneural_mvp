from typing import List
import os
import tiktoken
from langchain_core.documents import Document

from sqlalchemy import update, select, Table, MetaData
from sqlalchemy.orm import Session
from datetime import datetime
from app.models.organization_model import Organization
from app.models.department_licenses_model import DepartmentLicenses
from app.models.user_licenses_model import UserLicenses
def dept_license_and_token_update(
    db: Session,
    org_id: int,
    dept_id: int,
    tokens_used: int,

) -> None:
    """
    When an author uploads a file, this function updates the department_licenses
    table with token usage for the specified department.

    Args:
        db (Session): SQLAlchemy DB session
        org_id (int): Organization ID
        dept_id (int): Department ID
        tokens_used (int): Number of tokens used for embedding the file

    Raises:
        ValueError: If the department_licenses row is not found
    """
    metadata = MetaData()
    dept_licenses = Table("department_licenses", metadata, autoload_with=db.bind)

    # Fetch existing token values
    stmt = select(
        dept_licenses.c.used_tokens,
        dept_licenses.c.balance_tokens
    ).where(
        dept_licenses.c.org_id == org_id,
        dept_licenses.c.dept_id == dept_id
    )

    result = db.execute(stmt).fetchone()
    if result is None:
            
        dept_license=DepartmentLicenses(org_id=org_id, dept_id=dept_id, used_tokens=tokens_used)
        db.add(dept_license)
        db.commit()
        return


    used_tokens = (result.used_tokens or 0) + tokens_used
    balance_tokens = max((result.balance_tokens or 0) - tokens_used, 0)

    # Perform update
    upd = (
        update(dept_licenses)
        .where(
            dept_licenses.c.org_id == org_id,
            dept_licenses.c.dept_id == dept_id
        )
        .values(
            used_tokens=used_tokens,
            balance_tokens=balance_tokens,
            updated_at=datetime.utcnow()
        )
    )
    db.execute(upd)
    db.commit()


from sqlalchemy import update, select, Table, MetaData
from sqlalchemy.orm import Session
from datetime import datetime

def org_license_and_token_update(
    db: Session,

    org_id: int,

    tokens_used: int,

) -> None:
    """
    Updates the org_licenses table for a specific org and department
    when that org uploads a file that consumes embedding tokens.

    Adds to the used_tokens column (other columns are generated).
    """
    metadata = MetaData()
    org_licenses = Table("organizations", metadata, autoload_with=db.bind)

    stmt = select(org_licenses.c.used_tokens).where(
        org_licenses.c.id == org_id,
    )
    result = db.execute(stmt).fetchone()

    if not result:
        org_license=Organization(id=org_id, used_tokens=tokens_used)
        db.add(org_license)
        db.commit()
        return


    new_used_tokens = (result.used_tokens or 0) + tokens_used

    upd = (
        update(org_licenses)
        .where(
            org_licenses.c.id == org_id,
        )
        .values(
            used_tokens=new_used_tokens,
            updated_at=datetime.utcnow()
        )
    )
    db.execute(upd)
    db.commit()

# def user_license_and_token_update(
#     db: Session,

#     user_id: int,
#     # dept_id: int,
#     tokens_used: int,

# ) -> None:
#     """
#     Updates the user_licenses table for a specific user and department
#     when that user uploads a file that consumes embedding tokens.

#     Adds to the used_tokens column (other columns are generated).
#     """
#     metadata = MetaData()
#     user_licenses = Table("user_licenses", metadata, autoload_with=db.bind)
#     # print("dept_id in embedding token",dept_id,type(dept_id))
#     if dept_id ==0:
#         stmt=select(user_licenses.c.used_tokens).where(
#             user_licenses.c.user_id == user_id,
#             user_licenses.c.dept_id.is_(None),
#         )
#     else:
#        stmt = select(user_licenses.c.used_tokens).where(
#         user_licenses.c.user_id == user_id,
#         user_licenses.c.dept_id == dept_id,
    
#        )
#     result = db.execute(stmt).fetchone()

#     if not result:
#         if dept_id ==0:
#             user_license=UserLicenses(user_id=user_id, used_tokens=tokens_used)
#         else:
#             user_license=UserLicenses(user_id=user_id, dept_id=dept_id, used_tokens=tokens_used)
        
#         db.add(user_license)
#         db.commit()
#         return


#     new_used_tokens = (result.used_tokens or 0) + tokens_used
#     if dept_id ==0:
#         upd=(
#             update(user_licenses)
#             .where(
#                 user_licenses.c.user_id == user_id,
#                 user_licenses.c.dept_id.is_(None),
#             )
#             .values(
#                 used_tokens=new_used_tokens,
#                 updated_at=datetime.utcnow()
#             )
#         )
#         db.execute(upd)
#         db.commit()
#         return
#     upd = (
#         update(user_licenses)
#         .where(
#             user_licenses.c.user_id == user_id,
#             user_licenses.c.dept_id == dept_id
#         )
#         .values(
#             used_tokens=new_used_tokens,
#             updated_at=datetime.utcnow()
#         )
#     )
#     db.execute(upd)
#     db.commit()

def user_license_and_token_update(
    db: Session,
    user_id: int,
  
    tokens_used: int) -> None:
    """
    Updates the user_licenses table for a specific user and organization
    when that user uploads a file that consumes embedding tokens.
    Adds to the used_tokens column (other columns are generated).
    """
    metadata = MetaData()
    user_licenses = Table("user_licenses", metadata, autoload_with=db.bind)
    stmt = select(user_licenses.c.used_tokens).where(
        user_licenses.c.user_id == user_id
    )
    result = db.execute(stmt).fetchone()
    if not result:
        user_license=UserLicenses(user_id=user_id, used_tokens=tokens_used)
        db.add(user_license)
        db.commit()
        return
    new_used_tokens = (result.used_tokens or 0) + tokens_used
    upd = (
        update(user_licenses)
        .where(
            user_licenses.c.user_id == user_id
        )
        .values(
            used_tokens=new_used_tokens,
            updated_at=datetime.utcnow()
        )
    )
    db.execute(upd)
    db.commit() 


def _get_openai_embedding_encoding(model_name: str):
    """
    Returns the correct tokenizer for the given OpenAI embedding model.
    """
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback for unknown/new models
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens_for_openai_embeddings(model_name: str, texts: List[str]) -> int:
    """
    Exact token count for OpenAI embeddings using the SAME tokenizer
    as the embedding model.
    """
    if not texts:
        return 0

    enc = _get_openai_embedding_encoding(model_name)

    total_tokens = 0
    for text in texts:
        if text:
            total_tokens += len(enc.encode(text))

    return total_tokens