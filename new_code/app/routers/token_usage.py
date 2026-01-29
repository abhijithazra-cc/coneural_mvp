from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, Table, MetaData, func
from app.database import get_db

router_dept = APIRouter(prefix="/department-tokens", tags=["Department Tokens"])
router_user = APIRouter(prefix="/user-tokens", tags=["User Tokens"])


@router_dept.get("/{org_id}/{dept_id}", response_model=dict)
def get_department_token_usage(org_id: int, dept_id: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT allocated_tokens, used_tokens, balance_tokens
        FROM department_licenses
        WHERE org_id = :org_id AND dept_id = :dept_id
        LIMIT 1
    """)
    result = db.execute(query, {"org_id": org_id, "dept_id": dept_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Department license not found")

    return {
        "allocated_tokens": result.allocated_tokens or 0,
        "used_tokens": result.used_tokens or 0,
        "balance_tokens": result.balance_tokens or 0
    }



@router_user.get("/{user_id}", response_model=dict)
def get_user_token_usage(user_id: int, db: Session = Depends(get_db)):
    metadata = MetaData()
    user_licenses = Table("user_licenses", metadata, autoload_with=db.bind)

    stmt = select(
        func.sum(user_licenses.c.allocated_tokens).label("allocated_tokens"),
        func.sum(user_licenses.c.used_tokens).label("used_tokens"),
        func.sum(user_licenses.c.balance_tokens).label("balance_tokens")
    ).where(user_licenses.c.user_id == user_id)

    result = db.execute(stmt).fetchone()
    if not result or result.allocated_tokens is None:
        raise HTTPException(status_code=404, detail="User license not found")

    return {
        "allocated_tokens": result.allocated_tokens,
        "used_tokens": result.used_tokens,
        "balance_tokens": result.balance_tokens
    }
