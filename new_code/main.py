# main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine

# 🔹 Import all models so SQLAlchemy sees every table + foreign key
import app.models  # noqa: F401

# 🔹 Create the single FastAPI app
app = FastAPI(
    title="Coneural Backend",
    version="1.0.0",
    description="AI-powered SaaS backend for orgs, departments, and document ingestion",
)

# 🔹 CORS (relaxed for dev; restrict origins in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # e.g. ["https://your-frontend.com"] in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔹 Create tables if not using Alembic migrations
Base.metadata.create_all(bind=engine)

# 🔹 Import routers AFTER app + models
from app.routers.auth import router as auth_router            # /auth
from app.routers.organizations import router as org_router    # /organizations
from app.routers.suborganizations import router as suborg_router  # /departments or /suborganizations
from app.routers.users import router as users_router          # /users
from app.routers.documents import router as docs_router       # /org-documents
from app.routers.access import router as access_router        # /access
from app.routers.qa import router as qa_router

# 🔹 Attach routers
app.include_router(auth_router)
app.include_router(org_router)
app.include_router(suborg_router)
app.include_router(users_router)
app.include_router(docs_router)
app.include_router(access_router)
app.include_router(qa_router)

# 🔹 Health / root endpoints
@app.get("/")
def root():
    return {"status": "ok", "message": "Coneural Backend API is running"}

@app.get("/health")
def health_check():
    return {
        "ok": True,
        "db_connected": True,         # just a static flag; add real DB ping if you like
        "env": os.getenv("ENVIRONMENT", "dev"),
    }
