import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from jose import jwt
from passlib.context import CryptContext

# --- Config from environment (set these in your .env) ---
SECRET_KEY = os.getenv("ACCESS_TOKEN_SECRET", "change_me")   # ← replace in prod
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Configure bcrypt so it won't raise on >72 bytes (will silently truncate)
_pwd_ctx = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__truncate_error=False,  # ✅ no ValueError on long passwords
)

def _truncate72(s: str) -> str:
    b = s.encode("utf-8")
    if len(b) > 72:
        return b[:72].decode("utf-8", errors="ignore")
    return s

def get_password_hash(password: str) -> str:
    # Truncate for consistent behavior even if context changes later
    return _pwd_ctx.hash(_truncate72(password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Match the same truncation logic used during hashing
    try:
        return _pwd_ctx.verify(_truncate72(plain_password), hashed_password)
    except Exception:
        # Absolute fallback (should not trigger with bcrypt__truncate_error=False)
        return False

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
