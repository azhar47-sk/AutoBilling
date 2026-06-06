from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from bcrypt import hashpw, checkpw, gensalt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings

bearer_scheme = HTTPBearer()


# ── password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return hashpw(plain.encode(), gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return checkpw(plain.encode(), hashed.encode())


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(owner_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(owner_id), "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── FastAPI dependency ────────────────────────────────────────────────────────

def require_owner(
    creds: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> int:
    """Returns owner_id from a valid JWT. Raises 401 otherwise."""
    payload = decode_token(creds.credentials)
    return int(payload["sub"])


# ── Pi secret dependency ──────────────────────────────────────────────────────

from fastapi import Header


def require_pi(x_pi_secret: str = Header(...)) -> None:
    """Validates the shared Pi↔backend secret. Raises 403 otherwise."""
    if x_pi_secret != settings.PI_SECRET:
        raise HTTPException(status_code=403, detail="Invalid Pi secret")
