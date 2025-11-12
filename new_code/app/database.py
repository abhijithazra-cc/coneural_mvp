# app/database.py
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()  # ← loads .env at project root

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Optional: support component-style vars if you prefer
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    dbname = os.getenv("DB_NAME")
    if host and user and password and dbname:
        DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:3306/{dbname}"
    else:
        raise RuntimeError(
            "DATABASE_URL is not set. Create a .env file or export the variable. "
            "Example: DATABASE_URL=mysql+pymysql://user:pass@host:3306/coreneural_dev"
        )

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
