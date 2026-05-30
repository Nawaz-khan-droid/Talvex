"""
TALVEX Settings Router — Secure API key storage using Fernet encryption.
Keys are encrypted at rest and never returned to the client in plaintext.
"""

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import AuditLog, UserSettings
from schemas import SettingsResponse, SettingsUpdate

logger = logging.getLogger("talvex.settings")

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ============================================================
# Fernet Encryption Helpers
# ============================================================

def _get_fernet() -> Fernet:
    """Get Fernet instance using PII_VAULT_MASTER_KEY from environment."""
    master_key = os.environ.get("PII_VAULT_MASTER_KEY", "")
    if not master_key:
        raise RuntimeError("PII_VAULT_MASTER_KEY not configured")
    # Ensure key is valid Fernet key (44 chars, base64-encoded)
    if len(master_key) == 44:
        return Fernet(master_key.encode())
    # If it's a shorter hex key, derive a proper Fernet key
    key_bytes = hashlib.sha256(master_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _encrypt_value(plain_text: str) -> str:
    """Encrypt a value using Fernet. Returns encrypted string."""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def _decrypt_value(encrypted_text: str) -> str:
    """Decrypt a value using Fernet. Returns plaintext string."""
    return _get_fernet().decrypt(encrypted_text.encode()).decode()


# ============================================================
# Internal Helpers
# ============================================================

def _require_internal_request(request: Request) -> None:
    """Reject browser requests to internal-only key decryption endpoints.

    Backend services (openrouter_client, tavily, etc.) call these endpoints
    via httpx/requests with a service-to-service header.  Browser requests
    from the frontend are rejected with 403 Forbidden.

    This is defense-in-depth: CSP ``connect-src 'self'`` already prevents
    arbitrary fetch() from injected scripts, but if CSP is ever relaxed,
    this gate still blocks direct browser access to plaintext API keys.
    """
    # Accept requests from backend services (server-side httpx, no browser origin)
    sec_fetch_site = request.headers.get("Sec-Fetch-Site", "")
    # Browser-initiated requests always set Sec-Fetch-Site to "same-origin" or "cross-site"
    # Server-side httpx/requests do NOT set Sec-Fetch-Site at all
    if sec_fetch_site:
        logger.warning(
            "Blocked browser request to internal key decryption endpoint "
            "(Sec-Fetch-Site=%s, client=%s)",
            sec_fetch_site,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=403,
            detail="This endpoint is for internal server-side use only.",
        )


def _parse_settings(encrypted_settings: str) -> dict:
    """Parse the encryptedSettings JSON string. Returns empty dict on failure."""
    try:
        data = json.loads(encrypted_settings)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


async def _get_or_create_settings(db: AsyncSession, user_id: str) -> UserSettings:
    """Get existing settings or create default empty settings for the user."""
    result = await db.execute(
        select(UserSettings).filter(UserSettings.userId == user_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(
            id=uuid.uuid4().hex[:16],
            userId=user_id,
            encryptedSettings="{}",
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info("Created default settings for user %s", user_id)
    return settings


def _build_settings_response(settings: UserSettings) -> dict:
    """Build the SettingsResponse dict from a UserSettings object.

    NEVER includes actual key values — only boolean indicators.
    """
    data = _parse_settings(settings.encryptedSettings)
    return {
        "hasOpenRouterKey": bool(data.get("openrouter_key")),
        "hasTavilyKey": bool(data.get("tavily_key")),
        "hasFirecrawlKey": bool(data.get("firecrawl_key")),
        "updatedAt": settings.updatedAt.isoformat() if settings.updatedAt else None,
    }


async def _add_audit_log(
    db: AsyncSession,
    action: str,
    actor_id: str,
    details: Optional[str] = None,
) -> None:
    """Create an audit log entry for settings changes.

    IMPORTANT: Never log actual key values — only action descriptions.
    """
    log = AuditLog(
        id=uuid.uuid4().hex[:16],
        action=action,
        actor=actor_id,
        details=details,
        actorUserId=actor_id,
    )
    db.add(log)
    await db.commit()


# ============================================================
# GET /api/settings — Get current settings (boolean indicators only)
# ============================================================

@router.get("")
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return settings with boolean indicators for each key.

    NEVER returns actual key values. If no settings exist for the user,
    creates default empty settings automatically.
    """
    settings = await _get_or_create_settings(db, current_user["user_id"])
    return _build_settings_response(settings)


# ============================================================
# PUT /api/settings — Update settings (encrypt and store keys)
# ============================================================

@router.put("")
async def update_settings(
    body: SettingsUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Encrypt and store API keys using Fernet (PII_VAULT_MASTER_KEY).

    - Keys are stored as encrypted JSON in UserSettings.encryptedSettings.
    - Format: {"openrouter_key": "fernet_encrypted_value", ...}
    - If a key field is empty string or null, the key is DELETEd from settings.
    - Returns SettingsResponse (boolean indicators, never actual key values).
    """
    settings = await _get_or_create_settings(db, current_user["user_id"])
    data = _parse_settings(settings.encryptedSettings)

    changed_keys: list[str] = []

    # Map of internal storage keys to incoming values
    key_mappings = {
        "openrouter_key": body.openrouter_key,
        "tavily_key": body.tavily_key,
        "firecrawl_key": body.firecrawl_key,
    }

    for field_name, value in key_mappings.items():
        if value is None or value.strip() == "":
            # Delete the key if it exists in stored settings
            if field_name in data:
                del data[field_name]
                changed_keys.append(f"{field_name} (removed)")
        else:
            # Encrypt and store the key
            try:
                encrypted = _encrypt_value(value.strip())
                data[field_name] = encrypted
                changed_keys.append(field_name)
            except Exception as exc:
                logger.error("Failed to encrypt %s for user %s: %s", field_name, current_user["user_id"], exc)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to encrypt {field_name}. Please try again.",
                ) from exc

    # Persist updated settings
    settings.encryptedSettings = json.dumps(data)
    settings.updatedAt = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(settings)

    # Log change (without key values!)
    if changed_keys:
        await _add_audit_log(
            db,
            action="settings:update",
            actor_id=current_user["user_id"],
            details=f"Updated API keys: {', '.join(changed_keys)}",
        )
        logger.info(
            "User %s updated settings: %s",
            current_user["email"], ", ".join(changed_keys),
        )

    return _build_settings_response(settings)


# ============================================================
# GET /api/settings/keys/openrouter — Internal: decrypt OpenRouter key
# ============================================================

@router.get("/keys/openrouter")
async def get_openrouter_key(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """INTERNAL USE ONLY — Decrypt and return the OpenRouter API key.

    This endpoint is restricted to server-side calls only.  Browser requests
    are rejected (CSP blocks inline scripts, but defense-in-depth applies).
    After decrypting, the key should be used immediately and the local
    variable is cleaned up to reduce the window of plaintext exposure.
    """
    _require_internal_request(request)
    result = await db.execute(
        select(UserSettings).filter_by(userId=current_user["user_id"])
    )
    settings = result.scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=404, detail="No API keys configured")

    data = _parse_settings(settings.encryptedSettings)
    encrypted_key = data.get("openrouter_key")
    if not encrypted_key:
        raise HTTPException(status_code=404, detail="OpenRouter key not configured")

    try:
        key_value = _decrypt_value(encrypted_key)
    except InvalidToken:
        logger.error(
            "Failed to decrypt OpenRouter key for user %s — invalid Fernet token "
            "(key may have been encrypted with a different master key)",
            current_user["user_id"],
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt API key. It may have been encrypted with a different master key.",
        )
    except Exception as exc:
        logger.error(
            "Failed to decrypt OpenRouter key for user %s: %s",
            current_user["user_id"], exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt API key.",
        ) from exc

    try:
        return {"key": key_value}
    finally:
        # Attempt memory cleanup (Python doesn't guarantee GC, but reduces window)
        del key_value


# ============================================================
# GET /api/settings/keys/tavily — Internal: decrypt Tavily key
# ============================================================

@router.get("/keys/tavily")
async def get_tavily_key(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """INTERNAL USE ONLY — Decrypt and return the Tavily API key.

    This endpoint is restricted to server-side calls only.  Browser requests
    are rejected.  After decrypting, the key should be used immediately and
    the local variable is cleaned up to reduce the window of plaintext exposure.
    """
    _require_internal_request(request)
    result = await db.execute(
        select(UserSettings).filter_by(userId=current_user["user_id"])
    )
    settings = result.scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=404, detail="No API keys configured")

    data = _parse_settings(settings.encryptedSettings)
    encrypted_key = data.get("tavily_key")
    if not encrypted_key:
        raise HTTPException(status_code=404, detail="Tavily key not configured")

    try:
        key_value = _decrypt_value(encrypted_key)
    except InvalidToken:
        logger.error(
            "Failed to decrypt Tavily key for user %s — invalid Fernet token "
            "(key may have been encrypted with a different master key)",
            current_user["user_id"],
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt API key. It may have been encrypted with a different master key.",
        )
    except Exception as exc:
        logger.error(
            "Failed to decrypt Tavily key for user %s: %s",
            current_user["user_id"], exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt API key.",
        ) from exc

    try:
        return {"key": key_value}
    finally:
        # Attempt memory cleanup (Python doesn't guarantee GC, but reduces window)
        del key_value


# ============================================================
# DELETE /api/settings — Clear all stored settings
# ============================================================

@router.delete("")
async def delete_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all stored encrypted settings for the current user.

    This is a destructive action — all BYOK API keys will be permanently removed.
    """
    result = await db.execute(
        select(UserSettings).filter_by(userId=current_user["user_id"])
    )
    settings = result.scalar_one_or_none()
    if not settings:
        return {"message": "Settings cleared"}

    db.delete(settings)
    await db.commit()

    await _add_audit_log(
        db,
        action="settings:delete",
        actor_id=current_user["user_id"],
        details="Cleared all encrypted API key settings",
    )

    logger.info("User %s cleared all settings", current_user["user_id"])
    return {"message": "Settings cleared"}
