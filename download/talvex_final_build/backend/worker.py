"""
TALVEX ARQ Background Worker

Runs long-running tasks (resume optimization, job scraping) in a separate
process backed by Redis.  Tasks survive backend restarts because job state
is persisted in Redis.

Usage (standalone):
    cd backend && arq worker.WorkerSettings

Usage (Docker):
    docker compose up talvex-worker
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Load .env before any other imports
from dotenv import load_dotenv
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from arq import Worker, cron
from arq.connections import RedisSettings

logger = logging.getLogger("talvex.worker")

# ── Redis connection settings ──────────────────────────────
_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _redis_settings() -> RedisSettings:
    """Parse REDIS_URL into arq RedisSettings."""
    # arq expects host/port, not a URL string.
    # For simple redis://host:port/db format, parse manually.
    url = _redis_url
    # Strip protocol
    if url.startswith("redis://"):
        url = url[len("redis://"):]
    # Strip trailing slash and db number
    if "/" in url:
        host_port, db_str = url.rsplit("/", 1)
        db = int(db_str) if db_str.isdigit() else 0
    else:
        host_port = url
        db = 0

    # Handle password
    password = None
    if "@" in host_port:
        credentials, host_port = host_port.rsplit("@", 1)
        if ":" in credentials:
            _, password = credentials.split(":", 1)

    # Handle host:port
    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 6379

    return RedisSettings(
        host=host,
        port=port,
        database=db,
        password=password,
    )


# ── Worker Functions ────────────────────────────────────────

async def run_pipeline_task(ctx: dict, pipeline: str, payload: dict) -> dict:
    """Execute a LangGraph pipeline (resume optimization, job search, etc.).

    This is the primary worker function.  The backend enqueues jobs here
    via the task_queue wrapper, and polls for results via ARQ's job
    metadata in Redis.

    Parameters
    ----------
    ctx : dict
        ARQ job context (contains redis connection).
    pipeline : str
        Pipeline name: "optimize_resume", "search_jobs", etc.
    payload : dict
        Serialized request payload from the task router.

    Returns
    -------
    dict
        Pipeline result (match scores, recommendations, etc.)
    """
    from services.agent import run_pipeline

    logger.info("ARQ: Starting pipeline=%s", pipeline)

    try:
        result = await run_pipeline(pipeline, payload)
        logger.info("ARQ: Pipeline %s completed successfully.", pipeline)
        return result
    except Exception as exc:
        logger.exception("ARQ: Pipeline %s failed: %s", pipeline, exc)
        raise


async def cleanup_expired_tasks(ctx: dict) -> None:
    """Cron job: clean up expired task results from Redis.

    Runs daily at 03:00 UTC.  Removes ARQ job results older than 24 hours
    to prevent Redis memory bloat.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    redis = ctx["redis"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_ts = int(cutoff.timestamp())
    deleted = 0

    async for key in redis.scan_iter("arq:job:*"):
        job_data = await redis.get(key)
        if job_data:
            try:
                import json
                job = json.loads(job_data) if isinstance(job_data, bytes) else job_data
                if job.get("started", 0) and job["started"] < cutoff_ts:
                    await redis.delete(key)
                    deleted += 1
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

    logger.info("ARQ cron: Cleaned up %d expired job records.", deleted)


# ── Worker Settings ─────────────────────────────────────────

class WorkerSettings:
    """ARQ worker configuration for TALVEX.

    Functions listed in ``functions`` are registered as job handlers
    that the backend can enqueue via ``arq_pool.enqueue_job()``.
    """

    # Registered job functions
    functions = [run_pipeline_task]

    # Cron jobs (daily cleanup at 03:00 UTC)
    cron_jobs = [
        cron(cleanup_expired_tasks, hour=3, minute=0),
    ]

    # Redis connection
    redis_settings = _redis_settings()

    # Worker behaviour
    max_jobs = 10  # concurrent jobs per worker
    job_timeout = 600  # 10 minutes per job (resume generation can be slow)
    keep_result = 86400  # keep results in Redis for 24 hours
    health_check_interval = 60

    # On startup / shutdown
    on_startup = None
    on_shutdown = None

    def __init__(self):
        logger.info(
            "TALVEX ARQ Worker configured: max_jobs=%d, timeout=%ds, keep_result=%ds",
            self.max_jobs, self.job_timeout, self.keep_result,
        )


# ── Direct run entry point ─────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting TALVEX ARQ worker...")
    Worker()  # This is called by `arq worker.WorkerSettings` CLI
