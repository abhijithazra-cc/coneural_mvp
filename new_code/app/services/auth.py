# import os
# from datetime import datetime, timedelta
# from typing import Optional

# from fastapi import Depends, HTTPException, status
# from fastapi.security import OAuth2PasswordBearer
# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from sqlalchemy.orm import Session

# from app.database import get_db
# from app.models.user_model import User as UserModel

# # -----------------------------------------------------------------------------
# # CONFIGURATION
# # -----------------------------------------------------------------------------
# SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-this")
# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day by default

# # bcrypt hashing context
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# # OAuth2 scheme for FastAPI dependency
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# # -----------------------------------------------------------------------------
# # PASSWORD UTILS
# # -----------------------------------------------------------------------------

# def get_password_hash(password: str) -> str:
#     """
#     Hash password using bcrypt.
#     Note: bcrypt only supports up to 72 bytes of password length.
#     """
#     if len(password.encode("utf-8")) > 72:
#         raise ValueError("Password exceeds bcrypt 72-byte limit, please use a shorter password.")
#     return pwd_context.hash(password)


# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     """
#     Verify plain password against hashed one.
#     """
#     return pwd_context.verify(plain_password, hashed_password)


# # -----------------------------------------------------------------------------
# # TOKEN CREATION
# # -----------------------------------------------------------------------------

# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
#     """
#     Create JWT token with expiry.
#     """
#     to_encode = data.copy()
#     expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt


# # -----------------------------------------------------------------------------
# # DATABASE HELPERS
# # -----------------------------------------------------------------------------

# def get_user_by_email(db: Session, email: str) -> Optional[UserModel]:
#     """
#     Return user record by email.
#     """
#     return db.query(UserModel).filter(UserModel.email == email).first()


# def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
#     """
#     Return user record by username.
#     """
#     return db.query(UserModel).filter(UserModel.username == username).first()


# def authenticate_user(db: Session, email: str, password: str) -> Optional[UserModel]:
#     """
#     Authenticate user by verifying email and password.
#     """
#     user = get_user_by_email(db, email)
#     if not user:
#         return None
#     if not verify_password(password, user.hashed_password):
#         return None
#     return user


# # -----------------------------------------------------------------------------
# # TOKEN VALIDATION DEPENDENCIES
# # -----------------------------------------------------------------------------

# def get_current_user(
#     db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
# ) -> UserModel:
#     """
#     Extract and verify user from JWT token.
#     """
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Invalid authentication credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         email: str = payload.get("sub")
#         if email is None:
#             raise credentials_exception
#     except JWTError:
#         raise credentials_exception

#     user = get_user_by_email(db, email)
#     if user is None:
#         raise credentials_exception
#     return user


# def get_current_active_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
#     """
#     Validate current user as active. (Extend with 'is_active' check if field exists)
#     """
#     # Example future logic:
#     # if not current_user.is_active:
#     #     raise HTTPException(status_code=400, detail="Inactive user")
#     return current_user




# app/services/auth.py
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24))  # default 1 day

# bcrypt context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# IMPORTANT: Swagger's OAuth2 password flow hits /auth/token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# -----------------------------------------------------------------------------
# PASSWORD HELPERS
# -----------------------------------------------------------------------------
def get_password_hash(password: str) -> str:
    """
    Hash password with bcrypt. bcrypt accepts up to 72 bytes only.
    """
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password exceeds bcrypt 72-byte limit, please use a shorter password.")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# -----------------------------------------------------------------------------
# JWT HELPERS
# -----------------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -----------------------------------------------------------------------------
# DB HELPERS
# -----------------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.email == email).first()

def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.username == username).first()

def authenticate_user(db: Session, email: str, password: str) -> Optional[UserModel]:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    # Optional: check active here as well
    if hasattr(user, "is_active") and user.is_active is False:
        return None
    return user

# -----------------------------------------------------------------------------
# TOKEN → USER DEPENDENCIES
# -----------------------------------------------------------------------------
def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email)
    if not user:
        raise credentials_exception
    return user

def get_current_active_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    # Enforce active flag if present
    if hasattr(current_user, "is_active") and current_user.is_active is False:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


#######################################################################################################



# app/routers/auth.py
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_model import User as UserModel
from app.utils.security import verify_password, SECRET_KEY, ALGORITHM

# Must match your router’s token endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# ---------------------------------------------------------------------
# DB lookups
# ---------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.email == email).first()

def get_user_by_username(db: Session, username: str) -> Optional[UserModel]:
    return db.query(UserModel).filter(UserModel.username == username).first()

# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------
def authenticate_user(db: Session, email: str, password: str) -> Optional[UserModel]:
    user = get_user_by_email(db, email)
    print("user",user)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# ---------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    return user

def get_current_active_user(
    current_user: UserModel = Depends(get_current_user),
) -> UserModel:
    # If you track is_active, enforce here:
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
