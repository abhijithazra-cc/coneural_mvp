import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import engine
from models import Base

# import routers
from routers.orgs import router as org_router
from routers.suborgs import router as suborg_router
from routers.users import router as user_router
from routers.domains import router as domain_router
from routers.org_documents import router as doc_router
from routers.access import router as access_router
from routers.qa import router as qa_router

load_dotenv()

app = FastAPI(title="Org Document Portal")

#  CORS setup
origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "").split(",") if o.strip()] \
          or ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#  include routers
app.include_router(org_router)
app.include_router(suborg_router)
app.include_router(user_router)
app.include_router(domain_router)
app.include_router(doc_router)
app.include_router(access_router)
app.include_router(qa_router)


@app.on_event("startup")
async def on_startup():
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    """Simple health check endpoint"""
    return {"status": "ok"}
