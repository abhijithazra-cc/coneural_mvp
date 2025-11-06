# crud.py
from sqlalchemy.orm import Session
from models import User
from schemas.user import UserCreate

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user: UserCreate):
    db_user = User(
        username=user.username,
        email=user.email,
        password=user.password  # no hashing
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
