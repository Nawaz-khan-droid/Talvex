"""
TALVEX Admin Router — User management and system operations.
All endpoints require admin role.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_admin_user, get_redis_client
from models import User, AuditLog, Application, ApiUsageLog, UserCreditBalance
from schemas import UserAdminResponse, UserUpdateByAdmin

logger = logging.getLogger("talvex.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Track server start time for uptime calculation
_START_TIME = time.time()
_VERSION = "1.0.0"


# ============================================================
# Helpers
# ============================================================

def _user_admin_dict(user: User) -> dict:
    """Convert a User ORM object to a dict matching UserAdminResponse schema.

    NEVER includes passwordHash.
    """
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.displayName,
        "role": user.role,
        "is_active": user.isActive,
        "created_at": user.createdAt.isoformat() if user.createdAt else None,
        "updated_at": user.updatedAt.isoformat() if user.updatedAt else None,
    }


async def _add_audit_log(
    db: AsyncSession,
    action: str,
    actor_id: str,
    details: Optional[str] = None,
) -> None:
    """Create an audit log entry for admin actions."""
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
# GET /api/admin/users — List users (paginated, searchable)
# ============================================================

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by email substring"),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of all users. Supports optional email search filter."""
    conditions = []
    if search:
        conditions.append(User.email.ilike(f"%{search}%"))

    # Count
    total = (await db.execute(
        select(func.count(User.id)).filter(*conditions)
    )).scalar()

    # Fetch users
    stmt = (
        select(User)
        .filter(*conditions)
        .order_by(User.createdAt.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    return {
        "users": [_user_admin_dict(u) for u in users],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


# ============================================================
# GET /api/admin/users/{user_id} — Get single user
# ============================================================

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return detailed information for a single user."""
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_admin_dict(user)


# ============================================================
# PATCH /api/admin/users/{user_id} — Update user (admin)
# ============================================================

@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateByAdmin,
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role, active status, or display name.

    An admin cannot change their own role to prevent self-lockout.
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes: list[str] = []

    # Prevent self-role-change to avoid lockout
    if body.role is not None and user_id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own role to prevent self-lockout.",
        )

    if body.role is not None and body.role != user.role:
        user.role = body.role
        changes.append(f"role -> {body.role}")

    if body.is_active is not None and body.is_active != user.isActive:
        user.isActive = body.is_active
        changes.append(f"is_active -> {body.is_active}")

    if body.display_name is not None and body.display_name != user.displayName:
        user.displayName = body.display_name
        changes.append("display_name updated")

    if not changes:
        return _user_admin_dict(user)

    user.updatedAt = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    await _add_audit_log(
        db,
        action="admin:user_update",
        actor_id=current_user["user_id"],
        details=f"Updated user {user.email}: {', '.join(changes)}",
    )

    logger.info(
        "Admin %s updated user %s: %s",
        current_user["email"], user.email, ", ".join(changes),
    )
    return _user_admin_dict(user)


# ============================================================
# DELETE /api/admin/users/{user_id} — Soft-delete (deactivate)
# ============================================================

@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a user by setting is_active=False. Never hard-deletes.

    An admin cannot deactivate themselves.
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate yourself.",
        )

    if not user.isActive:
        raise HTTPException(
            status_code=400,
            detail="User is already deactivated.",
        )

    user.isActive = False
    user.updatedAt = datetime.now(timezone.utc)
    await db.commit()

    await _add_audit_log(
        db,
        action="admin:user_deactivate",
        actor_id=current_user["user_id"],
        details=f"Deactivated user {user.email}",
    )

    logger.info("Admin %s deactivated user %s", current_user["user_id"], user.id)
    return {"message": "User deactivated"}


# ============================================================
# GET /api/admin/audit-log — Paginated audit logs
# ============================================================

@router.get("/audit-log")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None, description="Filter by actor user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated audit logs with optional filters.

    Includes the actor user's email when available.
    """
    conditions = []
    if user_id:
        conditions.append(AuditLog.actorUserId == user_id)
    if action:
        conditions.append(AuditLog.action == action)

    # Count
    total = (await db.execute(
        select(func.count(AuditLog.id)).filter(*conditions)
    )).scalar()

    # Fetch logs
    stmt = (
        select(AuditLog)
        .filter(*conditions)
        .order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Build results with actor email when available
    results = []
    for log in logs:
        actor_email: Optional[str] = None
        if log.actorUserId:
            actor_result = await db.execute(select(User).filter(User.id == log.actorUserId))
            actor_user = actor_result.scalar_one_or_none()
            actor_email = actor_user.email if actor_user else None

        results.append({
            "id": log.id,
            "app_id": log.appId,
            "action": log.action,
            "actor": log.actor,
            "actor_user_id": log.actorUserId,
            "actor_email": actor_email,
            "details": log.details,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        })

    return {
        "logs": results,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


# ============================================================
# GET /api/admin/system/health — System health check
# ============================================================

@router.get("/system/health")
async def system_health(
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return system health information including DB, Redis, uptime, and counts."""
    redis_client = get_redis_client()

    # --- Check database ---
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    # --- Check Redis ---
    try:
        redis_client.ping()
        redis_status = "connected"
    except Exception:
        redis_status = "disconnected"

    # Overall status is healthy only when DB is connected
    overall = "healthy" if db_status == "connected" else "degraded"

    # --- Count blocked IPs (talvex:ip_block:* keys) ---
    blocked_ips = 0
    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="talvex:ip_block:*", count=200)
            blocked_ips += len(keys)
            if cursor == 0:
                break
    except Exception:
        pass

    # --- Aggregate counts ---
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_applications = (await db.execute(select(func.count(Application.id)))).scalar() or 0

    uptime_seconds = int(time.time() - _START_TIME)

    return {
        "status": overall,
        "database": db_status,
        "redis": redis_status,
        "uptime_seconds": uptime_seconds,
        "total_users": total_users,
        "total_applications": total_applications,
        "blocked_ips": blocked_ips,
        "version": _VERSION,
    }


# ============================================================
# GET /api/admin/system/quota/{user_id} — User quota usage
# ============================================================

@router.get("/system/quota/{user_id}")
async def user_quota(
    user_id: str,
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current quota usage for all actions for a given user.

    Useful for debugging rate-limiting issues. Scans Redis for
    ``talvex:quota:{user_id}:*`` keys and reports per-action usage
    against configured limits.
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    redis_client = get_redis_client()

    # Import configured quota limits from auth module
    from auth import QUOTA_LIMITS

    # Scan all quota keys for this user
    quota_data: dict[str, dict] = {}
    pattern = f"talvex:quota:{user_id}:*"

    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match=pattern, count=200)
            if keys:
                values = redis_client.mget(keys)
                for key, value in zip(keys, values):
                    if value is not None:
                        # Key format: talvex:quota:{user_id}:{action}:{YYYY-MM-DD}
                        parts = key.split(":")
                        if len(parts) >= 4:
                            action = parts[3]
                            count = int(value)
                            limit = QUOTA_LIMITS.get(action, 0)
                            if action not in quota_data or count > quota_data[action]["used"]:
                                quota_data[action] = {
                                    "used": count,
                                    "limit": limit,
                                    "remaining": max(0, limit - count),
                                }
            if cursor == 0:
                break
    except Exception as exc:
        logger.warning("Failed to scan quota keys for user %s: %s", user_id, exc)

    return {
        "user_id": user_id,
        "email": user.email,
        "quotas": quota_data,
    }


# ============================================================
# POST /api/admin/system/unblock-ip — Unblock an IP
# ============================================================

@router.post("/system/unblock-ip")
async def unblock_ip(
    body: dict,
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an IP address from the blocklist.

    Expects JSON body with ``{"ip": "<ip_address>"}``.
    """
    ip = body.get("ip")
    if not ip or not isinstance(ip, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'ip' field")

    redis_client = get_redis_client()
    key = f"talvex:ip_block:{ip}"

    try:
        removed = redis_client.delete(key)
    except Exception as exc:
        logger.error("Failed to unblock IP %s: %s", ip, exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to unblock IP",
        ) from exc

    await _add_audit_log(
        db,
        action="admin:ip_unblock",
        actor_id=current_user["user_id"],
        details=f"Unblocked IP: {ip} (existed={bool(removed)})",
    )

    logger.info(
        "Admin %s unblocked IP %s (key existed: %s)",
        current_user["email"], ip, bool(removed),
    )
    return {"unblocked": True}


# ============================================================
# GET /api/admin/stats/overview — System-wide overview
# ============================================================

@router.get("/stats/overview")
async def stats_overview(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """System-wide statistics: totals, active users, error rates, service usage."""
    from models import ApiUsageLog, User, Application

    cutoff = time.time() - (days * 86400)

    # Total API calls in period
    total_calls = (await db.execute(
        select(func.count(ApiUsageLog.id)).filter(ApiUsageLog.createdAt >= cutoff)
    )).scalar() or 0

    # Error count
    error_calls = (await db.execute(
        select(func.count(ApiUsageLog.id)).filter(
            ApiUsageLog.createdAt >= cutoff,
            ApiUsageLog.status == "error",
        )
    )).scalar() or 0

    # Rate limited count
    rate_limited_calls = (await db.execute(
        select(func.count(ApiUsageLog.id)).filter(
            ApiUsageLog.createdAt >= cutoff,
            ApiUsageLog.status == "rate_limited",
        )
    )).scalar() or 0

    # Active users (users with at least 1 API call in period)
    active_users = (await db.execute(
        select(func.count(func.distinct(ApiUsageLog.userId))).filter(
            ApiUsageLog.createdAt >= cutoff,
            ApiUsageLog.userId.isnot(None),
        )
    )).scalar() or 0

    # Total users
    total_users = (await db.execute(
        select(func.count(User.id))
    )).scalar() or 0

    # Total applications
    total_applications = (await db.execute(
        select(func.count(Application.id))
    )).scalar() or 0

    # Total credits consumed
    total_credits = (await db.execute(
        select(func.coalesce(func.sum(ApiUsageLog.creditsUsed), 0)).filter(
            ApiUsageLog.createdAt >= cutoff,
        )
    )).scalar() or 0

    # Per-service call counts
    service_counts_result = await db.execute(
        select(ApiUsageLog.service, func.count(ApiUsageLog.id).label("count"))
        .filter(ApiUsageLog.createdAt >= cutoff)
        .group_by(ApiUsageLog.service)
    )
    service_breakdown = {row[0]: row[1] for row in service_counts_result}

    # Unique services used
    unique_services = len(service_breakdown)

    return {
        "period_days": days,
        "total_api_calls": total_calls,
        "successful_calls": total_calls - error_calls - rate_limited_calls,
        "error_calls": error_calls,
        "rate_limited_calls": rate_limited_calls,
        "error_rate": round(error_calls / max(total_calls, 1) * 100, 2),
        "active_users": active_users,
        "total_users": total_users,
        "total_applications": total_applications,
        "total_credits_consumed": round(total_credits, 2),
        "service_breakdown": service_breakdown,
        "unique_services": unique_services,
    }


# ============================================================
# GET /api/admin/stats/api-usage — Per-service call counts
# ============================================================

@router.get("/stats/api-usage")
async def stats_api_usage(
    days: int = Query(30, ge=1, le=365),
    service: Optional[str] = Query(None, description="Filter by service name"),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-service API call counts with detailed breakdowns."""
    from models import ApiUsageLog

    cutoff = time.time() - (days * 86400)

    conditions = [ApiUsageLog.createdAt >= cutoff]
    if service:
        conditions.append(ApiUsageLog.service == service)

    # Per-service breakdown
    service_stats = await db.execute(
        select(
            ApiUsageLog.service,
            func.count(ApiUsageLog.id).label("total_calls"),
            func.sum(ApiUsageLog.creditsUsed).label("total_credits"),
            func.sum(ApiUsageLog.tokensUsed).label("total_tokens"),
            func.count(func.nullif(ApiUsageLog.status, "success")).label("error_count"),
        )
        .filter(*conditions)
        .group_by(ApiUsageLog.service)
        .order_by(func.count(ApiUsageLog.id).desc())
    )

    result = []
    for row in service_stats:
        total = row[1] or 0
        errors = row[4] or 0
        result.append({
            "service": row[0],
            "total_calls": total,
            "total_credits": round(row[2] or 0, 2),
            "total_tokens": int(row[3] or 0),
            "error_count": errors,
            "error_rate": round(errors / max(total, 1) * 100, 2),
        })

    # Per-endpoint breakdown for each service
    endpoint_stats = await db.execute(
        select(
            ApiUsageLog.service,
            ApiUsageLog.endpoint,
            func.count(ApiUsageLog.id).label("count"),
        )
        .filter(*conditions)
        .group_by(ApiUsageLog.service, ApiUsageLog.endpoint)
        .order_by(func.count(ApiUsageLog.id).desc())
        .limit(50)
    )

    endpoints = [
        {"service": row[0], "endpoint": row[1], "count": row[2]}
        for row in endpoint_stats
    ]

    return {
        "period_days": days,
        "services": result,
        "top_endpoints": endpoints,
    }


# ============================================================
# GET /api/admin/stats/credits — Credit usage tracking
# ============================================================

@router.get("/stats/credits")
async def stats_credits(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100, description="Top N spenders"),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Credit usage analytics: top spenders, daily consumption."""
    from models import ApiUsageLog, UserCreditBalance, User

    cutoff = time.time() - (days * 86400)

    # Top spenders
    top_spenders = await db.execute(
        select(
            ApiUsageLog.userId,
            func.sum(ApiUsageLog.creditsUsed).label("total_spent"),
            func.count(ApiUsageLog.id).label("total_calls"),
        )
        .filter(
            ApiUsageLog.createdAt >= cutoff,
            ApiUsageLog.userId.isnot(None),
        )
        .group_by(ApiUsageLog.userId)
        .order_by(func.sum(ApiUsageLog.creditsUsed).desc())
        .limit(limit)
    )

    spenders = []
    for row in top_spenders:
        uid = row[0]
        # Get user email
        user_result = await db.execute(select(User.email).filter(User.id == uid))
        email = user_result.scalar_one_or_none()

        # Get current balance
        balance_result = await db.execute(
            select(UserCreditBalance).filter(UserCreditBalance.userId == uid)
        )
        bal = balance_result.scalar_one_or_none()

        spenders.append({
            "user_id": uid,
            "email": email,
            "credits_spent": round(row[1] or 0, 2),
            "total_calls": row[2] or 0,
            "current_balance": round(bal.balance, 2) if bal else 100.0,
            "lifetime_used": round(bal.totalUsed, 2) if bal else round(row[1] or 0, 2),
        })

    # Total credits consumed in period
    total_consumed = (await db.execute(
        select(func.coalesce(func.sum(ApiUsageLog.creditsUsed), 0)).filter(
            ApiUsageLog.createdAt >= cutoff,
        )
    )).scalar() or 0

    # Average daily consumption
    avg_daily = round(total_consumed / max(days, 1), 2)

    return {
        "period_days": days,
        "total_credits_consumed": round(total_consumed, 2),
        "average_daily_consumption": avg_daily,
        "top_spenders": spenders,
    }


# ============================================================
# GET /api/admin/stats/users/active — Most active users
# ============================================================

@router.get("/stats/users/active")
async def stats_active_users(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Most active users ranked by API call volume."""
    from models import ApiUsageLog, User

    cutoff = time.time() - (days * 86400)

    active = await db.execute(
        select(
            ApiUsageLog.userId,
            func.count(ApiUsageLog.id).label("call_count"),
            func.sum(ApiUsageLog.creditsUsed).label("credits_used"),
            func.count(func.nullif(ApiUsageLog.status, "success")).label("error_count"),
            func.min(ApiUsageLog.createdAt).label("first_call"),
            func.max(ApiUsageLog.createdAt).label("last_call"),
        )
        .filter(
            ApiUsageLog.createdAt >= cutoff,
            ApiUsageLog.userId.isnot(None),
        )
        .group_by(ApiUsageLog.userId)
        .order_by(func.count(ApiUsageLog.id).desc())
        .limit(limit)
    )

    users = []
    for row in active:
        uid = row[0]
        user_result = await db.execute(select(User.email, User.isActive).filter(User.id == uid))
        user_data = user_result.one_or_none()

        users.append({
            "user_id": uid,
            "email": user_data[0] if user_data else "unknown",
            "is_active": user_data[1] if user_data else False,
            "total_calls": row[1] or 0,
            "credits_used": round(row[2] or 0, 2),
            "error_count": row[3] or 0,
            "first_call": row[4],
            "last_call": row[5],
        })

    return {
        "period_days": days,
        "active_users": users,
    }


# ============================================================
# GET /api/admin/stats/errors — Recent errors
# ============================================================

@router.get("/stats/errors")
async def stats_errors(
    limit: int = Query(50, ge=1, le=200),
    service: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent errors by service for debugging."""
    from models import ApiUsageLog

    conditions = [ApiUsageLog.status.in_(["error", "rate_limited"])]
    if service:
        conditions.append(ApiUsageLog.service == service)

    errors = await db.execute(
        select(ApiUsageLog)
        .filter(*conditions)
        .order_by(ApiUsageLog.createdAt.desc())
        .limit(limit)
    )

    results = []
    for log in errors.scalars():
        results.append({
            "id": log.id,
            "user_id": log.userId,
            "service": log.service,
            "endpoint": log.endpoint,
            "status": log.status,
            "error_message": log.errorMessage,
            "credits_used": log.creditsUsed,
            "created_at": log.createdAt,
        })

    # Error frequency by service
    error_freq = await db.execute(
        select(
            ApiUsageLog.service,
            func.count(ApiUsageLog.id).label("count"),
        )
        .filter(*conditions)
        .group_by(ApiUsageLog.service)
        .order_by(func.count(ApiUsageLog.id).desc())
    )

    frequency = [{"service": row[0], "error_count": row[1]} for row in error_freq]

    return {"errors": results, "error_frequency": frequency}


# ============================================================
# GET /api/admin/stats/rate-limits — Rate limit monitoring
# ============================================================

@router.get("/stats/rate-limits")
async def stats_rate_limits(
    current_user: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate limit hit counts from ApiUsageLog."""
    from models import ApiUsageLog

    # Rate limited calls in last 24h
    cutoff_24h = time.time() - 86400

    rate_limited_24h = (await db.execute(
        select(func.count(ApiUsageLog.id)).filter(
            ApiUsageLog.status == "rate_limited",
            ApiUsageLog.createdAt >= cutoff_24h,
        )
    )).scalar() or 0

    # Rate limited calls in last 7 days
    cutoff_7d = time.time() - (7 * 86400)

    rate_limited_7d = (await db.execute(
        select(func.count(ApiUsageLog.id)).filter(
            ApiUsageLog.status == "rate_limited",
            ApiUsageLog.createdAt >= cutoff_7d,
        )
    )).scalar() or 0

    # Per-service rate limit breakdown
    rl_by_service = await db.execute(
        select(
            ApiUsageLog.service,
            func.count(ApiUsageLog.id).label("count"),
        )
        .filter(
            ApiUsageLog.status == "rate_limited",
            ApiUsageLog.createdAt >= cutoff_7d,
        )
        .group_by(ApiUsageLog.service)
        .order_by(func.count(ApiUsageLog.id).desc())
    )

    service_breakdown = [{"service": row[0], "rate_limit_hits": row[1]} for row in rl_by_service]

    # Most rate-limited users
    rl_users = await db.execute(
        select(
            ApiUsageLog.userId,
            func.count(ApiUsageLog.id).label("hit_count"),
        )
        .filter(
            ApiUsageLog.status == "rate_limited",
            ApiUsageLog.createdAt >= cutoff_7d,
            ApiUsageLog.userId.isnot(None),
        )
        .group_by(ApiUsageLog.userId)
        .order_by(func.count(ApiUsageLog.id).desc())
        .limit(10)
    )

    top_users = [{"user_id": row[0], "rate_limit_hits": row[1]} for row in rl_users]

    return {
        "rate_limited_last_24h": rate_limited_24h,
        "rate_limited_last_7d": rate_limited_7d,
        "service_breakdown": service_breakdown,
        "top_rate_limited_users": top_users,
    }
