"""
TALVEX - Zero Trust Authentication Module

Stateful JWT authentication backed by Redis for instant session revocation.
Includes brute-force protection, CSRF double-submit cookies, and per-user
daily quota enforcement.

All sensitive operations require a valid session in Redis — a JWT alone
is NOT sufficient.  This enables instant revocation without waiting for
token expiry.
"""

import json
import os
import re
import secrets
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from fastapi import APIRouter, Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User

logger = logging.getLogger("talvex.auth")

# ============================================================
# 1. Configuration (from environment)
# ============================================================

_JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")
if not _JWT_SECRET_KEY:
    _JWT_SECRET_KEY = secrets.token_urlsafe(64)
    logger.warning(
        "JWT_SECRET_KEY not set in environment — generated an ephemeral key. "
        "ALL SESSIONS WILL BE INVALIDATED ON RESTART. "
        "Set JWT_SECRET_KEY in .env for persistent sessions."
    )

JWT_ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
BCRYPT_ROUNDS: int = int(os.environ.get("BCRYPT_ROUNDS", "12"))

# Quota limits (per action per user per day)
QUOTA_LIMITS: dict[str, int] = {
    "resume_optimize": 10,
    "job_search": 20,
    "llm_call": 50,
    "resume_generate": 5,
}

# ============================================================
# 2. Password Hashing
# ============================================================

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


# ============================================================
# 3. JWT Token Management (STATEFUL — Redis-backed)
# ============================================================

def create_access_token(
    data: dict,
    redis_client: redis.Redis,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT and register the session in Redis.

    The ``jti`` claim is stored as ``talvex:session:{jti}`` with a TTL
    matching the token expiry.  Revoking a session is as simple as
    DELETE-ing that key.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())

    payload = {
        **data,
        "jti": jti,
        "exp": now + expires_delta,
        "iat": now,
    }

    token = jwt.encode(payload, _JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Store session metadata in Redis for audit & revocation
    session_key = f"talvex:session:{jti}"
    session_value = json.dumps({
        "user_id": data.get("sub"),
        "email": data.get("email"),
        "role": data.get("role"),
    })
    ttl_seconds = int(expires_delta.total_seconds())
    redis_client.setex(session_key, ttl_seconds, session_value)

    logger.debug(
        "Created access token jti=%s for user=%s (ttl=%ds)",
        jti, data.get("sub"), ttl_seconds,
    )
    return token


def revoke_token(jti: str, redis_client: redis.Redis) -> None:
    """Immediately invalidate a session by removing it from Redis."""
    session_key = f"talvex:session:{jti}"
    redis_client.delete(session_key)
    logger.info("Revoked session jti=%s", jti)


def revoke_all_user_sessions(user_id: str, redis_client: redis.Redis) -> int:
    """Force-revoke every active session belonging to *user_id*.

    Scans all ``talvex:session:*`` keys, checks if the stored JSON
    contains the target user_id, and deletes matching keys.

    Returns the number of sessions revoked.
    """
    pattern = "talvex:session:*"
    revoked = 0
    cursor = 0

    while True:
        cursor, keys = redis_client.scan(cursor, match=pattern, count=200)
        if keys:
            values = redis_client.mget(keys)
            for key, value in zip(keys, values):
                if value is None:
                    continue
                try:
                    session_data = json.loads(value)
                    if session_data.get("user_id") == user_id:
                        redis_client.delete(key)
                        revoked += 1
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Corrupt session data in key %s — skipping", key)
        if cursor == 0:
            break

    logger.info("Revoked %d session(s) for user_id=%s", revoked, user_id)
    return revoked


def is_token_valid(jti: str, redis_client: redis.Redis) -> bool:
    """Check whether a session is still active in Redis.

    Returns ``False`` if the key has been deleted (revoked) or has
    naturally expired via Redis TTL.
    """
    session_key = f"talvex:session:{jti}"
    return redis_client.exists(session_key) > 0


# ============================================================
# 4. JWT Decode
# ============================================================

def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT string.

    Raises ``HTTPException(401)`` if the token is malformed, expired,
    or has an invalid signature.
    """
    try:
        payload = jwt.decode(token, _JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


# ============================================================
# 5. Brute-Force Protection (Redis-backed)
# ============================================================

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_TTL = 900  # 15 minutes in seconds


def check_brute_force(email: str, redis_client: redis.Redis) -> Optional[str]:
    """Check whether *email* is currently locked out due to too many
    failed login attempts.

    Returns a human-readable string with remaining lockout time if
    locked, or ``None`` if login is allowed.
    """
    lockout_key = f"talvex:lockout:{email}"

    remaining_ttl = redis_client.ttl(lockout_key)
    if remaining_ttl and remaining_ttl > 0:
        minutes, seconds = divmod(remaining_ttl, 60)
        return f"Account locked. Try again in {minutes}m {seconds}s."

    attempts_key = f"talvex:attempts:{email}"
    current_attempts = redis_client.get(attempts_key)
    if current_attempts and int(current_attempts) >= _MAX_FAILED_ATTEMPTS:
        # Shouldn't normally happen (lockout key should exist), but handle it
        redis_client.setex(lockout_key, _LOCKOUT_TTL, "locked")
        return "Account locked due to too many failed attempts."

    return None


def record_failed_attempt(email: str, redis_client: redis.Redis) -> int:
    """Increment the failed-login counter for *email*.

    If the counter reaches the threshold, a lockout key is created.

    Returns the new attempt count.
    """
    attempts_key = f"talvex:attempts:{email}"
    count = redis_client.incr(attempts_key)

    # Set TTL on first attempt
    if count == 1:
        redis_client.expire(attempts_key, _LOCKOUT_TTL)

    if count >= _MAX_FAILED_ATTEMPTS:
        lockout_key = f"talvex:lockout:{email}"
        redis_client.setex(lockout_key, _LOCKOUT_TTL, "locked")
        logger.warning(
            "Brute-force lockout triggered for email=%s after %d attempts",
            email, count,
        )

    return count


def clear_failed_attempts(email: str, redis_client: redis.Redis) -> None:
    """Remove all brute-force tracking for *email* (called on successful login)."""
    redis_client.delete(f"talvex:attempts:{email}", f"talvex:lockout:{email}")


async def reset_password(email: str, new_password: str) -> dict:
    """Server-side CLI utility to reset a user's password.

    This function is intended for use via ``docker exec`` when an admin
    locks themselves out. It bypasses brute-force checks because it's an
    out-of-band server-side operation, NOT a public API endpoint.

    Usage via Docker::
        docker exec talvex-backend python -c "
        import asyncio; from auth import reset_password; asyncio.run(reset_password('admin@example.com', 'NewPass123!'))"

    It also clears brute-force tracking and revokes all active sessions
    for the user to force re-login with the new password.

    Returns a dict with the result.
    """
    if not new_password or len(new_password) < 8:
        return {"success": False, "error": "Password must be at least 8 characters."}

    try:
        from database import AsyncSessionLocal
        from models import User

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).filter(User.email == email.strip().lower()))
            user = result.scalar_one_or_none()
            if not user:
                return {"success": False, "error": f"User '{email}' not found."}

            user.passwordHash = hash_password(new_password)
            await db.commit()

            # Clear brute-force lockout for this email
            redis_client = get_redis_client()
            clear_failed_attempts(email.strip().lower(), redis_client)

            # Revoke all active sessions for this user
            revoked = revoke_all_user_sessions(user.id, redis_client)

            logger.info(
                "Password reset for user=%s — %d session(s) revoked (server-side CLI)",
                email, revoked,
            )
            return {
                "success": True,
                "email": user.email,
                "revoked_sessions": revoked,
                "message": "Password reset successfully. All sessions revoked.",
            }
    except Exception as exc:
        logger.error("Password reset failed for user %s: %s", user.id, exc)
        return {"success": False, "error": str(exc)}


# ============================================================
# 6. FastAPI Dependencies
# ============================================================

_redis_singleton: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Return a Redis connection as a lazy singleton.

    Follows the same pattern as ``PIIVault`` in ``pii_sanitizer.py``:
    connects once, reuses the connection for the lifetime of the process.
    """
    global _redis_singleton
    if _redis_singleton is None:
        try:
            _redis_singleton = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_singleton.ping()
            logger.info("Auth module connected to Redis at %s", REDIS_URL)
        except Exception as exc:
            logger.error("Auth module: Redis connection failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service unavailable (Redis connection failed).",
            ) from exc
    return _redis_singleton


async def get_current_user(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """FastAPI dependency that extracts and validates the current user.

    1. Reads JWT from ``talvex_session`` HTTP-only cookie.
    2. Decodes and verifies the JWT signature.
    3. Checks Redis for an active session (stateful validation).
    4. Looks up the user in the database.
    5. Returns ``{"user_id": ..., "email": ..., "role": ...}``.
    """
    # 1. Extract JWT from cookie
    token = request.cookies.get("talvex_session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. No session cookie found.",
        )

    # 2. Decode JWT
    payload = decode_access_token(token)
    jti = payload.get("jti")
    user_id = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing jti or sub claim.",
        )

    # 3. Check Redis session validity
    if not is_token_valid(jti, redis_client):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked. Please log in again.",
        )

    # 4. Look up user in DB
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled. Contact an administrator.",
        )

    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
    }


def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """FastAPI dependency that requires the current user to be an admin."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


async def get_optional_user(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """Like ``get_current_user`` but returns ``None`` instead of raising 401.

    Used for endpoints that function without authentication but provide
    enhanced behaviour when a user is logged in.
    """
    token = request.cookies.get("talvex_session")
    if not token:
        return None

    try:
        payload = decode_access_token(token)
        jti = payload.get("jti")
        user_id = payload.get("sub")

        if not jti or not user_id:
            return None

        if not is_token_valid(jti, redis_client):
            return None

        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.isActive:
            return None

        return {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
        }
    except HTTPException:
        return None


# ============================================================
# 7. User Quota Checking
# ============================================================

def check_user_quota(
    user_id: str,
    action: str,
    redis_client: redis.Redis,
) -> bool:
    """Check and increment a daily usage counter for *action*.

    Redis key: ``talvex:quota:{user_id}:{action}:{YYYY-MM-DD}``
    TTL is set to end of current UTC day.

    Returns ``True`` if the action is within the quota limit,
    ``False`` if the quota has been exceeded.
    """
    limit = QUOTA_LIMITS.get(action)
    if limit is None:
        logger.warning("Unknown quota action: %s — allowing by default", action)
        return True

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    quota_key = f"talvex:quota:{user_id}:{action}:{date_str}"

    current = redis_client.incr(quota_key)

    # Set TTL to end of day on first increment
    if current == 1:
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        remaining_seconds = int((end_of_day - now).total_seconds()) + 1
        redis_client.expire(quota_key, remaining_seconds)

    if current > limit:
        logger.info(
            "Quota exceeded for user=%s action=%s (%d/%d)",
            user_id, action, current, limit,
        )
        return False

    return True


# ============================================================
# 8. Cookie Helpers
# ============================================================

# Detect debug mode for cookie Secure flag
_DEBUG_MODE = os.environ.get("DEBUG", "0").lower() in ("1", "true", "yes")


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    """Set the HTTP-only session cookie on a response."""
    response.set_cookie(
        key="talvex_session",
        value=token,
        httponly=True,
        secure=not _DEBUG_MODE,
        samesite="Lax",
        path="/",
        max_age=86400,
    )


def _set_csrf_cookie(response: JSONResponse, csrf_token: str) -> None:
    """Set the non-HttpOnly CSRF cookie (double-submit pattern)."""
    response.set_cookie(
        key="talvex_csrf",
        value=csrf_token,
        httponly=False,
        secure=not _DEBUG_MODE,
        samesite="Lax",
        path="/",
        max_age=86400,
    )


def _clear_cookies(response: JSONResponse) -> None:
    """Clear both session and CSRF cookies."""
    response.delete_cookie(key="talvex_session", path="/")
    response.delete_cookie(key="talvex_csrf", path="/")


# ============================================================
# 9. Validation Helpers
# ============================================================

_RE_EMAIL = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def _validate_email(email: str) -> str:
    """Validate email format.  Returns normalised (lowercased) email."""
    email = email.strip().lower()
    if not _RE_EMAIL.match(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email format.",
        )
    return email


def _validate_password(password: str) -> None:
    """Validate password meets minimum requirements."""
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long.",
        )


# ============================================================
# 10. Pydantic Request Models
# ============================================================

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ============================================================
# 11. Auth Router
# ============================================================

router = APIRouter(prefix="/api/auth", tags=["auth"])

# HTTPBearer scheme — registered so FastAPI's Swagger UI shows the lock icon.
_http_bearer = HTTPBearer(auto_error=False)


# ----------------------------------------------------------
# POST /api/auth/register
# ----------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_endpoint(
    body: RegisterRequest,
    redis_client: redis.Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account.

    All registered users receive ``role="user"``. Admin accounts are created
    exclusively via the ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` environment variables
    during server startup (see ``_bootstrap_admin_user`` in ``main.py``).

    Returns user info (no password hash).
    """
    email = _validate_email(body.email)
    _validate_password(body.password)

    # Check if email is already registered
    result = await db.execute(select(User).filter(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # SECURITY: Registration endpoint ALWAYS creates "user" role.
    # Admin accounts are created ONLY via out-of-band environment variables
    # (ADMIN_EMAIL + ADMIN_PASSWORD) during server startup in main.py.
    # There is NO way to escalate to admin through the public API.
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        passwordHash=hash_password(body.password),
        displayName=body.display_name,
        role="user",
        isActive=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create session token
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role},
        redis_client=redis_client,
    )

    # Generate CSRF token (double-submit pattern)
    csrf_token = secrets.token_hex(32)
    token_payload = decode_access_token(token)
    jti = token_payload.get("jti", "")
    csrf_key = f"talvex:csrf:{jti}"
    redis_client.setex(csrf_key, ACCESS_TOKEN_EXPIRE_MINUTES * 60, csrf_token)

    # Build response with cookies
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "display_name": user.displayName,
            "created_at": user.createdAt.isoformat() if user.createdAt else None,
        },
    )
    _set_session_cookie(response, token)
    _set_csrf_cookie(response, csrf_token)

    logger.info("User registered: user_id=%s (role=%s)", user.id, user.role)
    return response


# ----------------------------------------------------------
# POST /api/auth/login
# ----------------------------------------------------------

@router.post("/login")
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and issue a session cookie.

    Includes brute-force protection: after 5 failed attempts the
    account is locked for 15 minutes.

    Sets both a session cookie (HttpOnly) and a CSRF cookie (non-HttpOnly)
    using the double-submit pattern.
    """
    email = _validate_email(body.email)

    # Check brute-force lockout
    lockout_msg = check_brute_force(email, redis_client)
    if lockout_msg:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_msg,
        )

    # Look up user
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        record_failed_attempt(email, redis_client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled. Contact an administrator.",
        )

    # Verify password
    if not verify_password(body.password, user.passwordHash):
        attempts = record_failed_attempt(email, redis_client)
        remaining = _MAX_FAILED_ATTEMPTS - attempts
        detail = "Invalid email or password."
        if remaining > 0:
            detail += f" {remaining} attempt(s) remaining."
        else:
            detail += " Account is now locked for 15 minutes."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )

    # Success — clear failed attempts
    clear_failed_attempts(email, redis_client)

    # Create session token
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role},
        redis_client=redis_client,
    )

    # Generate CSRF token (double-submit pattern)
    csrf_token = secrets.token_hex(32)
    token_payload = decode_access_token(token)
    jti = token_payload.get("jti", "")
    csrf_key = f"talvex:csrf:{jti}"
    redis_client.setex(csrf_key, ACCESS_TOKEN_EXPIRE_MINUTES * 60, csrf_token)

    # Build response with cookies
    response = JSONResponse(
        content={
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "display_name": user.displayName,
        },
    )
    _set_session_cookie(response, token)
    _set_csrf_cookie(response, csrf_token)

    logger.info("User logged in: user_id=%s", user.id)
    return response


# ----------------------------------------------------------
# POST /api/auth/logout
# ----------------------------------------------------------

@router.post("/logout")
async def logout_endpoint(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis_client),
):
    """Revoke the current session and clear cookies.

    Accepts the token from the ``talvex_session`` cookie.  If no valid
    cookie is present, still clears cookies (idempotent).
    """
    token = request.cookies.get("talvex_session")

    if token:
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti")
            if jti:
                revoke_token(jti, redis_client)
                # Also clean up CSRF key
                redis_client.delete(f"talvex:csrf:{jti}")
        except HTTPException:
            pass  # Invalid token — just clear cookies

    response = JSONResponse(content={"detail": "Logged out successfully."})
    _clear_cookies(response)
    return response


# ----------------------------------------------------------
# GET /api/auth/me
# ----------------------------------------------------------

@router.get("/me")
async def me_endpoint(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current authenticated user's profile.

    Requires a valid session cookie.
    """
    result = await db.execute(select(User).filter(User.id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "display_name": user.displayName,
        "created_at": user.createdAt.isoformat() if user.createdAt else None,
    }


# ----------------------------------------------------------
# POST /api/auth/change-password
# ----------------------------------------------------------

@router.post("/change-password")
async def change_password_endpoint(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password.

    After a successful password change, ALL existing sessions for the
    user are revoked, forcing a re-login on every device.
    """
    _validate_password(body.new_password)

    result = await db.execute(select(User).filter(User.id == current_user["user_id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    # Verify current password
    if not verify_password(body.current_password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    # Update password
    user.passwordHash = hash_password(body.new_password)
    await db.commit()

    # Revoke ALL sessions (force re-login on every device)
    revoked_count = revoke_all_user_sessions(user.id, redis_client)

    logger.info(
        "Password changed for user=%s — revoked %d session(s)",
        user.email, revoked_count,
    )

    return JSONResponse(
        content={
            "detail": "Password changed successfully. "
                      f"{revoked_count} session(s) revoked. "
                      "Please log in again on all devices.",
        }
    )
