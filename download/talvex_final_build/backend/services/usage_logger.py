"""
TALVEX Async Usage Logger

Logs API usage to the database WITHOUT blocking the request path.
Uses fire-and-forget asyncio.create_task() to write in the background.

Architecture principle:
  - API clients (openrouter, tavily, jsearch) remain PURE — zero DB dependencies
  - The CALLER (agent.py, llm_service.py) invokes usage_logger.log_api_call()
  - The actual DB write happens in a fire-and-forget background coroutine
  - If the write fails, it logs an error but NEVER crashes the caller

This ensures logging takes zero milliseconds of the user's request time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def _write_usage_to_db(
    user_id: Optional[str],
    service: str,
    endpoint: str,
    status: str,
    credits_used: float,
    tokens_used: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Background coroutine that writes usage to the database.

    This runs in a fire-and-forget asyncio task. If it fails,
    the error is logged but the caller is NEVER affected.
    """
    try:
        from database import AsyncSessionLocal
        from models import ApiUsageLog

        async with AsyncSessionLocal() as db:
            log_entry = ApiUsageLog(
                userId=user_id,
                service=service,
                endpoint=endpoint,
                status=status,
                creditsUsed=credits_used,
                tokensUsed=tokens_used,
                errorMessage=error_message,
                createdAt=time.time(),
            )
            db.add(log_entry)
            await db.commit()

            logger.debug(
                "Usage logged: user=%s service=%s endpoint=%s status=%s credits=%.4f",
                user_id, service, endpoint, status, credits_used,
            )
    except Exception as exc:
        # NEVER propagate — this is fire-and-forget
        logger.error(
            "Failed to log API usage (user=%s, service=%s): %s",
            user_id, service, exc,
        )


async def _deduct_credits(
    user_id: str,
    credits_used: float,
) -> None:
    """Background coroutine that deducts credits from user balance."""
    try:
        from database import AsyncSessionLocal
        from models import UserCreditBalance
        from sqlalchemy import select

        if credits_used <= 0:
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserCreditBalance).filter(UserCreditBalance.userId == user_id)
            )
            balance = result.scalar_one_or_none()

            if balance:
                balance.balance = max(0.0, balance.balance - credits_used)
                balance.totalUsed = (balance.totalUsed or 0.0) + credits_used
                balance.lastUpdated = int(datetime.now(timezone.utc).timestamp() * 1000)
            else:
                # Create balance record if it doesn't exist
                balance = UserCreditBalance(
                    userId=user_id,
                    balance=max(0.0, 100.0 - credits_used),
                    totalUsed=credits_used,
                )
                db.add(balance)

            await db.commit()
    except Exception as exc:
        logger.error("Failed to deduct credits for user=%s: %s", user_id, exc)


# ===================================================================
# Credit costs per service (credits per call)
# ===================================================================

CREDIT_COSTS: dict[str, float] = {
    "openrouter": 1.0,       # 1 credit per LLM call
    "jsearch": 0.5,           # 0.5 credits per search
    "tavily": 0.3,            # 0.3 credits per search
    "resume_generate": 2.0,   # 2 credits per resume generation
    "ats_score": 1.0,         # 1 credit per ATS analysis
}


def get_credit_cost(service: str) -> float:
    """Get the credit cost for a given service. Returns 0.0 if unknown."""
    return CREDIT_COSTS.get(service, 0.0)


# ===================================================================
# Public API
# ===================================================================

def log_api_call(
    user_id: Optional[str] = None,
    service: str = "",
    endpoint: str = "",
    status: str = "success",
    credits_used: Optional[float] = None,
    tokens_used: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Fire-and-forget usage logger. Returns immediately.

    This is the ONLY public function. It schedules a background task
    and returns in under 1 microsecond. The caller's request is
    never blocked by database I/O.

    Parameters
    ----------
    user_id : str, optional
        The user who triggered the API call. May be None for anonymous/system calls.
    service : str
        The service name: "openrouter", "jsearch", "tavily", etc.
    endpoint : str
        The specific API endpoint called.
    status : str
        "success", "error", or "rate_limited".
    credits_used : float, optional
        If None, auto-calculated from CREDIT_COSTS table.
    tokens_used : int, optional
        Token count from the LLM response (if applicable).
    error_message : str, optional
        Error details if the call failed.
    """
    # Auto-calculate credits if not provided
    if credits_used is None:
        credits_used = get_credit_cost(service)

    # Fire and forget — the caller returns immediately
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running (shouldn't happen in FastAPI context)
        logger.warning(
            "log_api_call called outside async context (service=%s). Skipping.", service
        )
        return

    asyncio.create_task(
        _write_usage_to_db(
            user_id=user_id,
            service=service,
            endpoint=endpoint,
            status=status,
            credits_used=credits_used,
            tokens_used=tokens_used,
            error_message=error_message,
        )
    )

    # Deduct credits if we have a user and a successful call
    if user_id and status == "success" and credits_used and credits_used > 0:
        asyncio.create_task(_deduct_credits(user_id, credits_used))
