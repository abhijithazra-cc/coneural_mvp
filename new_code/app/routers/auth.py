# # app/routers/auth.py
# import os
# from datetime import timedelta
# from typing import Optional

# import httpx
# from fastapi import APIRouter, Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordRequestForm
# from pydantic import BaseModel, EmailStr, Field, validator
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.models.user_model import User as UserModel, UserType
# from app.models.organization_model import Organization as OrganizationModel
# from app.services.auth import (
#     get_password_hash,
#     authenticate_user,
#     create_access_token,
#     get_user_by_email,
#     get_user_by_username,
#     ACCESS_TOKEN_EXPIRE_MINUTES,
#     get_current_active_user,
# )

# router = APIRouter(prefix="/auth", tags=["authentication"])

# # ------------------------------------------------------------------------------
# # Schemas
# # ------------------------------------------------------------------------------

# class AdminSignup(BaseModel):
#     """Figma: Sign up on behalf of your Organization"""
#     org_name: str = Field(..., min_length=2, max_length=255, description="Organization / Company name")
#     admin_name: str = Field(..., min_length=2, max_length=255, description="Your name / username")
#     email: EmailStr
#     password: str = Field(..., min_length=8, max_length=16, description="8–16 characters")

#     @validator("password")
#     def _bcrypt_limit(cls, v: str):
#         # bcrypt max is 72 bytes
#         if len(v.encode("utf-8")) > 72:
#             raise ValueError("Password exceeds 72-byte bcrypt limit")
#         return v


# class UserLogin(BaseModel):
#     email: EmailStr
#     password: str


# class Token(BaseModel):
#     access_token: str
#     token_type: str = "bearer"
#     user: dict


# class OAuthTokenIn(BaseModel):
#     id_token: str


# # ------------------------------------------------------------------------------
# # OAuth env
# # ------------------------------------------------------------------------------

# OAUTH_DEV_SKIP_VERIFY = os.getenv("OAUTH_DEV_SKIP_VERIFY", "false").lower() == "true"
# GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
# MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")

# # ------------------------------------------------------------------------------
# # OAuth helpers (minimal; production should validate JWT signatures)
# # ------------------------------------------------------------------------------

# async def _google_verify(id_token: str) -> dict:
#     if OAUTH_DEV_SKIP_VERIFY:
#         return {"email": f"dev-google-{id_token[:8]}@example.com", "name": "Google User"}

#     async with httpx.AsyncClient(timeout=10) as client:
#         r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
#         if r.status_code != 200:
#             raise HTTPException(status_code=401, detail="Invalid Google id_token")
#         data = r.json()
#         if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
#             raise HTTPException(status_code=401, detail="Google token audience mismatch")
#         email = data.get("email")
#         if not email:
#             raise HTTPException(status_code=401, detail="Google profile missing email")
#         return {"email": email, "name": data.get("name") or email.split("@")[0]}


# async def _microsoft_verify(id_token: str) -> dict:
#     if OAUTH_DEV_SKIP_VERIFY:
#         return {"email": f"dev-ms-{id_token[:8]}@example.com", "name": "MS User"}
#     # Implement proper MSAL/JWKS validation in production
#     raise HTTPException(status_code=501, detail="Microsoft id_token verification not implemented")


# # ------------------------------------------------------------------------------
# # Routes
# # ------------------------------------------------------------------------------

# @router.post("/signup", status_code=status.HTTP_201_CREATED, summary="Sign up on behalf of your Organization")
# def create_org_and_admin(body: AdminSignup, db: Session = Depends(get_db)):
#     """
#     Creates a new Organization and an Admin user linked to it.
#     Returns organization + minimal user + bearer token.
#     """
#     # Unique org name
#     existing_org = db.query(OrganizationModel).filter(OrganizationModel.name == body.org_name).first()
#     if existing_org:
#         raise HTTPException(status_code=409, detail="Organization name already exists")

#     # Unique email / username
#     if get_user_by_email(db, body.email):
#         raise HTTPException(status_code=409, detail="Email already registered")

#     # Ensure username uniqueness (admin_name)
#     if get_user_by_username(db, body.admin_name):
#         base, i, uname = body.admin_name, 1, body.admin_name
#         while get_user_by_username(db, uname):
#             i += 1
#             uname = f"{base}{i}"
#         username = uname
#     else:
#         username = body.admin_name

#     # Create org
#     org = OrganizationModel(name=body.org_name, description=body.org_name)
#     db.add(org)
#     db.flush()  # get org.id before commit

#     # Hash password (bcrypt 72-byte limit already validated)
#     hashed = get_password_hash(body.password)

#     # Create admin user
#     admin = UserModel(
#         email=body.email,
#         username=username,
#         hashed_password=hashed,
#         user_type=UserType.ADMIN,
#         organization_id=org.id,
#     )
#     db.add(admin)
#     db.commit()
#     db.refresh(admin)

#     token = create_access_token({"sub": admin.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

#     return {
#         "organization": {"id": org.id, "name": org.name, "description": org.description},
#         "user": {"id": admin.id, "name": admin.username, "email": admin.email, "user_type": admin.user_type.value},
#         "access_token": token,
#         "token_type": "bearer",
#     }


# @router.post("/login", response_model=Token, summary="Email & password login")
# def login_user(creds: UserLogin, db: Session = Depends(get_db)):
#     user = authenticate_user(db, creds.email, creds.password)
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect email or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
#     }


# @router.post("/token", summary="OAuth2 Password (for Swagger UI)", response_model=Token)
# def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     """
#     This endpoint powers Swagger's OAuth2 password popup.
#     Use: username=<email>, password=<password>.
#     """
#     user = authenticate_user(db, form_data.username, form_data.password)
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
#     }


# @router.post("/oauth/google", response_model=Token, summary="Sign in with Google Workspace")
# async def login_google(body: OAuthTokenIn, db: Session = Depends(get_db)):
#     profile = await _google_verify(body.id_token)
#     email = profile["email"]
#     user = get_user_by_email(db, email)

#     if not user:
#         # First-time SSO user (org setup handled in onboarding)
#         uname = profile["name"] or email.split("@")[0]
#         base, i, candidate = uname, 1, uname
#         while get_user_by_username(db, candidate):
#             i += 1
#             candidate = f"{base}{i}"
#         user = UserModel(
#             email=email,
#             username=candidate,
#             hashed_password=get_password_hash("OAuth@" + candidate),  # dummy hashed secret
#             user_type=UserType.ADMIN,
#             organization_id=None,  # set later during onboarding
#         )
#         db.add(user)
#         db.commit()
#         db.refresh(user)

#     token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
#     }


# @router.post("/oauth/microsoft", response_model=Token, summary="Sign in with Microsoft Azure")
# async def login_microsoft(body: OAuthTokenIn, db: Session = Depends(get_db)):
#     profile = await _microsoft_verify(body.id_token)
#     email = profile.get("email")
#     if not email:
#         raise HTTPException(status_code=401, detail="Microsoft profile missing email")

#     user = get_user_by_email(db, email)
#     if not user:
#         uname = profile.get("name") or email.split("@")[0]
#         base, i, candidate = uname, 1, uname
#         while get_user_by_username(db, candidate):
#             i += 1
#             candidate = f"{base}{i}"
#         user = UserModel(
#             email=email,
#             username=candidate,
#             hashed_password=get_password_hash("OAuth@" + candidate),
#             user_type=UserType.ADMIN,
#             organization_id=None,
#         )
#         db.add(user)
#         db.commit()
#         db.refresh(user)

#     token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     return {
#         "access_token": token,
#         "token_type": "bearer",
#         "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
#     }


# @router.get("/me", summary="Current user")
# def read_users_me(current_user: UserModel = Depends(get_current_active_user)):
#     return {
#         "id": current_user.id,
#         "name": current_user.username,
#         "email": current_user.email,
#         "user_type": current_user.user_type.value,
#         "organization_id": current_user.organization_id,
#         "suborganization_id": current_user.suborganization_id,
#     }





import os
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel, UserType
from app.models.organization_model import Organization as OrganizationModel

# ✅ Crypto/JWT helpers come from utils (prevents circular imports)
from app.utils.security import (
    get_password_hash,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# ✅ DB lookups & auth deps from services
from app.services.auth import (
    authenticate_user,
    get_user_by_email,
    get_user_by_username,
    get_current_active_user,
)

from app.Rag.VectorManager import vectorManager
from app.Rag.utils import embeddings,BASE_DIR 


router = APIRouter(prefix="/auth", tags=["authentication"])

# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class AdminSignup(BaseModel):
    """Figma: Sign up on behalf of your Organization."""
    org_name: str = Field(..., min_length=2, max_length=255, description="Organization / Company name")
    admin_name: str = Field(..., min_length=2, max_length=255, description="Your name / username")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=16, description="8–16 characters")

    @validator("password")
    def _bcrypt_limit(cls, v: str):
        # bcrypt hard limit is 72 bytes
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password exceeds 72-byte bcrypt limit")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class OAuthTokenIn(BaseModel):
    id_token: str

# --------------------------------------------------------------------------
# OAuth env
# --------------------------------------------------------------------------
OAUTH_DEV_SKIP_VERIFY = os.getenv("OAUTH_DEV_SKIP_VERIFY", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")

# --------------------------------------------------------------------------
# OAuth helpers (minimal; add JWT signature validation in production)
# --------------------------------------------------------------------------
async def _google_verify(id_token: str) -> dict:
    if OAUTH_DEV_SKIP_VERIFY:
        return {"email": f"dev-google-{id_token[:8]}@example.com", "name": "Google User"}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token})
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google id_token")
        data = r.json()
        if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=401, detail="Google token audience mismatch")
        email = data.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Google profile missing email")
        return {"email": email, "name": data.get("name") or email.split("@")[0]}

async def _microsoft_verify(id_token: str) -> dict:
    if OAUTH_DEV_SKIP_VERIFY:
        return {"email": f"dev-ms-{id_token[:8]}@example.com", "name": "MS User"}
    # TODO: Implement MSAL/JWKS validation for production.
    raise HTTPException(status_code=501, detail="Microsoft id_token verification not implemented")

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.post("/signup", status_code=status.HTTP_201_CREATED, summary="Sign up on behalf of your Organization")
def create_org_and_admin(body: AdminSignup, db: Session = Depends(get_db)):
    """
    Create a new Organization and an Admin user linked to it.
    Returns organization + minimal user + bearer token.
    """
    # Unique org name
    if db.query(OrganizationModel).filter(OrganizationModel.name == body.org_name).first():
        raise HTTPException(status_code=409, detail="Organization name already exists")

    # Unique email
    if get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    # Unique username (admin_name)
    if get_user_by_username(db, body.admin_name):
        base, i, uname = body.admin_name, 1, body.admin_name
        while get_user_by_username(db, uname):
            i += 1
            uname = f"{base}{i}"
        username = uname
    else:
        username = body.admin_name

    # Create org
    org = OrganizationModel(name=body.org_name, description=body.org_name)
    db.add(org)
    db.flush()  # get org.id before commit
    vectorManager.get_store(embeddings=embeddings,persist_dir=f"{BASE_DIR}\{org.id}")
    # Create admin user
    hashed = get_password_hash(body.password)
    admin = UserModel(
        email=body.email,
        username=username,
        hashed_password=hashed,
        user_type=UserType.ADMIN,
        organization_id=org.id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token = create_access_token({"sub": admin.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    return {
        "organization": {"id": org.id, "name": org.name, "description": org.description},
        "user": {"id": admin.id, "name": admin.username, "email": admin.email, "user_type": admin.user_type.value},
        "access_token": token,
        "token_type": "bearer",
    }

@router.post("/login", response_model=Token, summary="Email & password login")
def login_user(creds: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, creds.email, creds.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
    }

@router.post("/token", response_model=Token, summary="OAuth2 Password (for Swagger UI)")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    This endpoint powers Swagger's OAuth2 password popup.
    Use: username=<email>, password=<password>.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
    }

@router.post("/oauth/google", response_model=Token, summary="Sign in with Google Workspace")
async def login_google(body: OAuthTokenIn, db: Session = Depends(get_db)):
    profile = await _google_verify(body.id_token)
    email = profile["email"]
    user = get_user_by_email(db, email)

    if not user:
        uname = profile["name"] or email.split("@")[0]
        base, i, candidate = uname, 1, uname
        while get_user_by_username(db, candidate):
            i += 1
            candidate = f"{base}{i}"
        user = UserModel(
            email=email,
            username=candidate,
            hashed_password=get_password_hash("OAuth@" + candidate),  # dummy hashed secret
            user_type=UserType.ADMIN,
            organization_id=None,  # set during onboarding
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
    }

@router.post("/oauth/microsoft", response_model=Token, summary="Sign in with Microsoft Azure")
async def login_microsoft(body: OAuthTokenIn, db: Session = Depends(get_db)):
    profile = await _microsoft_verify(body.id_token)
    email = profile.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Microsoft profile missing email")

    user = get_user_by_email(db, email)
    if not user:
        uname = profile.get("name") or email.split("@")[0]
        base, i, candidate = uname, 1, uname
        while get_user_by_username(db, candidate):
            i += 1
            candidate = f"{base}{i}"
        user = UserModel(
            email=email,
            username=candidate,
            hashed_password=get_password_hash("OAuth@" + candidate),
            user_type=UserType.ADMIN,
            organization_id=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.email}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.username, "email": user.email, "user_type": user.user_type.value},
    }

@router.get("/me", summary="Current user")
def read_users_me(current_user: UserModel = Depends(get_current_active_user)):
    return {
        "id": current_user.id,
        "name": current_user.username,
        "email": current_user.email,
        "user_type": current_user.user_type.value,
        "organization_id": current_user.organization_id,
        "suborganization_id": current_user.suborganization_id,
    }
