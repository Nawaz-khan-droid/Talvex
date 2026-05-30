"""
FastAPI router for analytics.
Endpoints:
  GET /api/analytics - Get full analytics data
  GET /api/analytics/funnel - Conversion funnel data
  GET /api/analytics/platform - By-platform statistics
  GET /api/analytics/salary - Salary trends

All status labels use Title Case: "Scraped", "Tailored", "Submitted", etc.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import get_db
from models import Application, JobPersona, TrackingCanary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

STATUS_ORDER = [
    "SCRAPED", "TAILORED", "SUBMITTED", "SCREENING",
    "ASSESSMENT", "INTERVIEWING", "OFFER", "REJECTED", "GHOSTED",
]

STATUS_LABELS = {
    "SCRAPED": "Scraped",
    "TAILORED": "Tailored",
    "SUBMITTED": "Submitted",
    "SCREENING": "Screening",
    "ASSESSMENT": "Assessment",
    "INTERVIEWING": "Interviewing",
    "OFFER": "Offer",
    "REJECTED": "Rejected",
    "GHOSTED": "Ghosted",
}


def _title_case(status: str) -> str:
    return STATUS_LABELS.get(status, status.title())


def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


def _app_filters(user_id: Optional[str] = None) -> list:
    """Return filter conditions for application queries."""
    if user_id:
        return [Application.userId == user_id]
    return []


async def _build_platform_stats(db: AsyncSession, user_id: Optional[str] = None) -> list[dict]:
    """Build platform breakdown statistics."""
    filters = _app_filters(user_id)

    stmt = (
        select(
            Application.platform,
            func.count(Application.id).label("count"),
            func.avg(Application.matchScore).label("avg_score"),
        )
        .filter(*filters)
        .group_by(Application.platform)
    )

    results = (await db.execute(stmt)).all()

    return [
        {
            "platform": r.platform,
            "count": r.count,
            "avgScore": round(float(r.avg_score), 1) if r.avg_score else 0,
        }
        for r in results
    ]


async def _build_salary_trends(db: AsyncSession, user_id: Optional[str] = None) -> list[dict]:
    """Build salary trend data."""
    filters = _app_filters(user_id)

    stmt = select(Application).filter(
        Application.salaryMin.isnot(None),
        Application.salaryMax.isnot(None),
        *filters,
    )

    result = await db.execute(stmt)
    apps = result.scalars().all()

    # Group by salary range
    ranges = {
        "0-5L": {"min": 0, "max": 500000, "count": 0, "totalMin": 0, "totalMax": 0},
        "5-10L": {"min": 500000, "max": 1000000, "count": 0, "totalMin": 0, "totalMax": 0},
        "10-20L": {"min": 1000000, "max": 2000000, "count": 0, "totalMin": 0, "totalMax": 0},
        "20-40L": {"min": 2000000, "max": 4000000, "count": 0, "totalMin": 0, "totalMax": 0},
        "40L+": {"min": 4000000, "max": float("inf"), "count": 0, "totalMin": 0, "totalMax": 0},
    }

    for app in apps:
        salary_val = app.salaryMax or 0
        for label, r in ranges.items():
            if r["min"] <= salary_val < r["max"]:
                r["count"] += 1
                r["totalMin"] += app.salaryMin or 0
                r["totalMax"] += app.salaryMax or 0
                break

    trends = []
    for label, r in ranges.items():
        if r["count"] > 0:
            trends.append({
                "rangeLabel": label,
                "count": r["count"],
                "avgMin": round(r["totalMin"] / r["count"]),
                "avgMax": round(r["totalMax"] / r["count"]),
            })
        else:
            trends.append({
                "rangeLabel": label,
                "count": 0,
                "avgMin": None,
                "avgMax": None,
            })

    return trends


async def _build_funnel(db: AsyncSession, user_id: Optional[str] = None) -> list[dict]:
    """Build conversion funnel data."""
    filters = _app_filters(user_id)

    stmt = (
        select(
            Application.status,
            func.count(Application.id).label("count"),
        )
        .filter(*filters)
        .group_by(Application.status)
    )

    results = (await db.execute(stmt)).all()

    status_counts = {r.status: r.count for r in results}

    funnel = []
    for status in STATUS_ORDER:
        count = status_counts.get(status, 0)
        funnel.append({
            "label": _title_case(status),
            "count": count,
        })

    return funnel


@router.get("")
async def get_analytics(db: AsyncSession = Depends(get_db), current_user: dict | None = Depends(get_optional_user)):
    """Get full analytics data."""
    if not current_user:
        return {
            "funnel": {}, "avgDaysInState": {}, "scoreDistribution": [],
            "topCompanies": [], "followUpVelocity": 0, "totalApplications": 0,
            "totalPersonas": 0, "overallMatchRate": 0, "leakAlerts": 0,
            "platformBreakdown": [], "followUpAlerts": 0, "responseRate": 0,
        }
    user_id = None if _is_admin(current_user) else current_user["user_id"]
    filters = _app_filters(user_id)

    total_apps = (await db.execute(
        select(func.count(Application.id)).filter(*filters)
    )).scalar() or 0

    persona_filters = [JobPersona.userId == user_id] if user_id else []
    total_personas = (await db.execute(
        select(func.count(JobPersona.id)).filter(*persona_filters)
    )).scalar() or 0

    leak_filters = [TrackingCanary.leakFlagged == True]  # noqa: E712
    if user_id:
        leak_filters.append(Application.userId == user_id)
    leak_stmt = select(func.count(TrackingCanary.id)).filter(
        TrackingCanary.leakFlagged == True  # noqa: E712
    )
    if user_id:
        leak_stmt = leak_stmt.join(Application, TrackingCanary.appId == Application.id).filter(
            Application.userId == user_id
        )
    leak_alerts = (await db.execute(leak_stmt)).scalar() or 0

    # Response rate
    responded = (await db.execute(
        select(func.count(Application.id)).filter(*filters, Application.responseType.isnot(None))
    )).scalar() or 0
    submitted_count = (await db.execute(
        select(func.count(Application.id)).filter(
            *filters,
            Application.status.in_(["SUBMITTED", "SCREENING", "ASSESSMENT", "INTERVIEWING", "OFFER", "REJECTED", "GHOSTED"])
        )
    )).scalar() or 1
    response_rate = round((responded / max(1, submitted_count)) * 100, 1)

    # Overall match rate
    avg_match = (await db.execute(
        select(func.avg(Application.matchScore)).filter(*filters)
    )).scalar() or 0
    overall_match_rate = round(float(avg_match), 1)

    return {
        "funnel": await _build_funnel(db, user_id),
        "totalApplications": total_apps,
        "totalPersonas": total_personas,
        "overallMatchRate": overall_match_rate,
        "platformBreakdown": await _build_platform_stats(db, user_id),
        "salaryTrends": await _build_salary_trends(db, user_id),
        "leakAlerts": leak_alerts,
        "responseRate": response_rate,
    }


@router.get("/funnel")
async def get_funnel(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get conversion funnel data."""
    user_id = None if _is_admin(current_user) else current_user["user_id"]
    return await _build_funnel(db, user_id)


@router.get("/platform")
async def get_platform_stats(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get by-platform statistics."""
    user_id = None if _is_admin(current_user) else current_user["user_id"]
    return await _build_platform_stats(db, user_id)


@router.get("/salary")
async def get_salary_trends(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get salary trends."""
    user_id = None if _is_admin(current_user) else current_user["user_id"]
    return await _build_salary_trends(db, user_id)
