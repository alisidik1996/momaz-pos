import bcrypt
import jwt
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Request, Response
from app.config import settings
from app.core.validation import validate_password
import logging

logger = logging.getLogger(__name__)


def auth_version(password_hash: str) -> str:
    """Bind a session to its account's current password hash without exposing it."""
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def valid_auth_version(value, password_hash: str) -> bool:
    return isinstance(value, str) and hmac.compare_digest(value, auth_version(password_hash))


class TokenError(Exception):
    """Base class for token-related errors."""
    pass


class TokenExpiredError(TokenError):
    """Token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Token is malformed or invalid."""
    pass


def hash_password(password: str) -> str:
    pwd_bytes = validate_password(password).encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode JWT token with proper error distinction.
    Returns payload dict on success, None on failure.
    Raises specific TokenError subclasses for different failure modes.
    """
    try:
        t = str(token).strip().strip('"').strip("'")
        while t.lower().startswith("bearer "):
            t = t[7:].strip().strip('"').strip("'")
        payload = jwt.decode(t, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], options={"require": ["exp", "sub"]})
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise TokenExpiredError("Token kedaluwarsa. Silakan login kembali.")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise TokenInvalidError("Token tidak valid.")
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None


def set_auth_cookie(response: Response, request: Request, token: str):
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        secure=bool(getattr(settings, "IS_PRODUCTION", False)) or request.url.scheme == "https",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
