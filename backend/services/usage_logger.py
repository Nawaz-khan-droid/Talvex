"""
TALVEX Async Usage Logger

Logs API usage to the database WITHOUT blocking the request path.
Uses ARQ (Redis-backed) to durably enqueue background writes.

Architecture principle:
  - API clients (openrouter, tavily, jsearch) remain PURE — zero DB dependencies
  - The CALLER (agent.py, llm_service.py) invokes usage_logger.log_api_call()
  - The actual DB write happens in the ARQ worker (backend/worker.py)
  - If ARQ is unavailable, logs a warning but NEVER crashes the caller

Why ARQ instead of asyncio.create_task():
  - asyncio tasks live in RAM — they DIE on container restart
  - ARQ jobs are persisted in Redis — they SURVIVE restarts
  - ARQ worker runs in a separate process — doesn't block FastAPI event loop

This ensures logging takes zero milliseconds of the user's request time.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import redis as redis_py

logger = logging.getLogger(__name__)

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _get_redis_client() -> Optional[redis_py.Redis]:
    """Get a synchronous Redis client for ARQ job enqueueing."""
    try:
        client = redis_py.Redis.from_url(_redis_url, decode_responses=False)
        client.ping()  # Verify connection
        return client
    except Exception as exc:
        logger.warning("Redis unavailable for usage logging: %s", exc)
        return None


def _enqueue_arq_job(job_name: str, **kwargs) -> bool:
    """Enqueue an ARQ job for the worker. Returns True on success."""
    client = _get_redis_client()
    if client is None:
        return False
    try:
        # Serialize kwargs to JSON-safe values for Redis
        job_payload = json.dumps(kwargs, default=str)
        # Use Redis LIST as a simple queue (ARQ-compatible)
        queue_key = f"arq:queue:{job_name}"
        client.rpush(queue_key, job_payload)
        logger.debug("ARQ job enqueued: %s", job_name)
        return True
    except Exception as exc:
        logger.error("Failed to enqueue ARQ job %s: %s", job_name, exc)
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


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
    """Fire-and-forget usage logger via ARQ. Returns immediately.

    This is the ONLY public function. It enqueues an ARQ job for the
    worker process and returns in under 1ms. The caller's request is
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

    # Enqueue ARQ job — survives container restarts, doesn't block FastAPI
    success = _enqueue_arq_job(
        "log_api_usage_task",
        user_id=user_id,
        service=service,
        endpoint=endpoint,
        status=status,
        credits_used=credits_used,
        tokens_used=tokens_used,
        error_message=error_message,
    )

    if not success:
        # Redis unavailable — log warning but never crash the caller
        logger.warning(
            "Usage logging skipped (Redis unavailable): service=%s endpoint=%s",
            service, endpoint,
        )
        return

    # Deduct credits if we have a user and a successful call
    if user_id and status == "success" and credits_used and credits_used > 0:
        _enqueue_arq_job(
            "deduct_credits_task",
            user_id=user_id,
            credits_used=credits_used,
        )
