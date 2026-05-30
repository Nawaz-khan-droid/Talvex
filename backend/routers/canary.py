"""
FastAPI router for canary email management.
Endpoints:
  GET  /api/canary - List all canaries
  POST /api/canary - Create canary for an application
  PATCH /api/canary/{id}/flag - Flag canary as leaked
  GET  /api/canary/leaks - Get all flagged leaks
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import get_db
from models import Application, TrackingCanary
from schemas import CanaryCreate, CanaryUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/canary", tags=["canary"])


def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


def _generate_canary_email(company: str) -> str:
    """Generate a unique canary email for leak detection."""
    slug = company.lower().replace(" ", "").replace(".", "")[:20]
    unique = uuid.uuid4().hex[:8]
    return f"talvex.canary.{slug}.{unique}@example.com"


@router.get("")
async def list_canaries(db: AsyncSession = Depends(get_db), current_user: dict | None = Depends(get_optional_user)):
    """List all canary email records."""
    if not current_user:
        return []
    stmt = select(TrackingCanary)

    if not _is_admin(current_user):
        stmt = stmt.join(Application, TrackingCanary.appId == Application.id).filter(
            Application.userId == current_user["user_id"]
        )

    result = await db.execute(stmt.order_by(TrackingCanary.createdAt.desc()))
    canaries = result.scalars().all()
    return [
        {
            "id": c.id,
            "appId": c.appId,
            "canaryEmail": c.canaryEmail,
            "trackingSlug": c.trackingSlug,
            "leakFlagged": bool(c.leakFlagged) if c.leakFlagged is not None else False,
            "leakDetails": c.leakDetails,
            "createdAt": c.createdAt.isoformat() if c.createdAt else None,
        }
        for c in canaries
    ]


@router.post("")
async def create_canary(data: CanaryCreate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Create a canary email for an application."""
    result = await db.execute(select(Application).filter(Application.id == data.app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{data.app_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this application")

    # Check if canary already exists for this app
    existing_result = await db.execute(select(TrackingCanary).filter(TrackingCanary.appId == data.app_id))
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Canary already exists for application '{data.app_id}'.",
        )

    # Check if canary email is already used
    email_result = await db.execute(select(TrackingCanary).filter(TrackingCanary.canaryEmail == data.canary_email))
    if email_result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Canary email '{data.canary_email}' is already in use.",
        )

    tracking_slug = data.tracking_slug or f"{app.company.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"

    canary = TrackingCanary(
        id=uuid.uuid4().hex[:25],
        appId=data.app_id,
        canaryEmail=data.canary_email,
        trackingSlug=tracking_slug,
        leakFlagged=False,
        createdAt=datetime.utcnow(),
    )

    db.add(canary)
    await db.commit()
    await db.refresh(canary)

    return {
        "id": canary.id,
        "appId": canary.appId,
        "canaryEmail": canary.canaryEmail,
        "trackingSlug": canary.trackingSlug,
        "leakFlagged": False,
        "leakDetails": None,
        "createdAt": canary.createdAt.isoformat() if canary.createdAt else None,
    }


@router.patch("/{canary_id}/flag")
async def flag_canary(canary_id: str, data: CanaryUpdate, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Flag a canary as leaked."""
    result = await db.execute(select(TrackingCanary).filter(TrackingCanary.id == canary_id))
    canary = result.scalar_one_or_none()
    if not canary:
        raise HTTPException(status_code=404, detail=f"Canary '{canary_id}' not found")

    # Ownership check — verify the canary's application belongs to current user
    app_result = await db.execute(select(Application).filter(Application.id == canary.appId))
    app = app_result.scalar_one_or_none()
    if app and not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this canary")

    canary.leakFlagged = data.leak_flagged
    canary.leakDetails = data.leak_details

    # If flagged as leaked, update application privacy status
    if data.leak_flagged:
        app_result2 = await db.execute(select(Application).filter(Application.id == canary.appId))
        app = app_result2.scalar_one_or_none()
        if app:
            app.privacyStatus = "LEAKED"
            app.updatedAt = datetime.utcnow()

    await db.commit()
    await db.refresh(canary)

    return {
        "id": canary.id,
        "appId": canary.appId,
        "canaryEmail": canary.canaryEmail,
        "trackingSlug": canary.trackingSlug,
        "leakFlagged": bool(canary.leakFlagged) if canary.leakFlagged is not None else False,
        "leakDetails": canary.leakDetails,
        "createdAt": canary.createdAt.isoformat() if canary.createdAt else None,
    }


@router.get("/leaks")
async def get_leaks(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get all flagged leak canaries."""
    stmt = select(TrackingCanary).filter(TrackingCanary.leakFlagged == True)  # noqa: E712

    if not _is_admin(current_user):
        stmt = stmt.join(Application, TrackingCanary.appId == Application.id).filter(
            Application.userId == current_user["user_id"]
        )

    result = await db.execute(stmt)
    leaks = result.scalars().all()

    result_list = []
    for c in leaks:
        app_result = await db.execute(select(Application).filter(Application.id == c.appId))
        app = app_result.scalar_one_or_none()
        result_list.append({
            "id": c.id,
            "appId": c.appId,
            "canaryEmail": c.canaryEmail,
            "trackingSlug": c.trackingSlug,
            "leakDetails": c.leakDetails,
            "createdAt": c.createdAt.isoformat() if c.createdAt else None,
            "application": {
                "company": app.company if app else "Unknown",
                "roleTitle": app.roleTitle if app else "Unknown",
                "platform": app.platform if app else "Unknown",
            } if app else None,
        })

    return {"leaks": result_list, "total": len(result_list)}
