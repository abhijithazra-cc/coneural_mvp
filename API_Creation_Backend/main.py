import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import engine
from models import Base
from routers.organizations import router as org_router
from routers.suborgs import router as suborg_router
from routers.users import router as users_router
from routers.domains import router as domain_router
from routers.org_documents import router as orgdoc_router

load_dotenv()

app = FastAPI(title="Multi-Org/Suborg Knowledge API")

origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or "").split(",") if o.strip()] or ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(org_router)
app.include_router(suborg_router)
app.include_router(users_router)
app.include_router(domain_router)
app.include_router(orgdoc_router)

@app.on_event("startup")
async def on_startup():
    # Will create tables we declared if missing (won't drop/alter your existing ones).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health")
def health():
    return {"status": "ok"}
