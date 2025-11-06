

import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
load_dotenv()

# DATABASE_URL = os.getenv("DATABASE_URL")
# if not DATABASE_URL:
    
#     DATABASE_URL = "mysql+aiomysql://boatuser:dR-sW11l7lR2hI9E%2B%40Ve@157.245.249.39:3306/coredb"
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:mysql@localhost:3306/testdb"
)

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
# engine = create_engine(SQLALCHEMY_DATABASE_URL,echo=True)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# async def get_session() -> AsyncSession:
#     async with SessionLocal() as session:
#         yield session

# Dependency to get DB session
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
Base = declarative_base()