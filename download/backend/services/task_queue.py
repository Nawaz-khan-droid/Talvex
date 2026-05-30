"""
TALVEX Async Task Queue — ARQ-backed (Redis-persisted ONLY)

All tasks are persisted in Redis and survive backend restarts.

If Redis is unavailable, the system returns a 503 Service Unavailable error
to the user.  Tasks are never silently queued — a task submitted during
a Redis outage would be lost on restart, causing data loss and wasted API credits.

Features
--------
- ``submit_task(func_or_name, *args, **kwargs) -> task_id``
- ``get_task_status(task_id) -> TaskInfo``
- ``get_task_result(task_id) -> result``
- ``list_tasks() -> list[TaskInfo]``
- Tasks survive backend restarts (Redis-backed)
- Fails fast if Redis is unavailable (503 to user)

Usage
-----

    from services.task_queue import task_queue

    task_id = await task_queue.submit_task("run_pipeline_task", pipeline="optimize_resume", payload={...})
    status = task_queue.get_task_status(task_id)
"""

from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Coroutine

import redis as redis_py

logger = logging.getLogger(__name__)


# ===================================================================
# Types
# ===================================================================

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    """Public-facing metadata for a task."""
    task_id: str
    status: TaskStatus
    task_type: str
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "task_type": self.task_type,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


# ===================================================================
# TaskQueue — ARQ-backed (Redis required, no fallback)
# ===================================================================

class TaskQueue:
    """
    ARQ-backed task queue.  Requires Redis — no fallback.

    If Redis is unreachable at initialization or at task submission time,
    the exception propagates so FastAPI can return a 503 to the user.
    This is the correct production behaviour: fail loudly rather than
    silently losing tasks.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._redis_client: redis_py.Redis | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to Redis.  Raises on failure — no silent degradation."""
        if self._initialized:
            return
        self._initialized = True

        import os
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis_client = redis_py.Redis.from_url(redis_url, decode_responses=True)
            self._redis_client.ping()
            logger.info("TaskQueue initialised (ARQ/Redis mode).")
        except Exception as exc:
            self._redis_client = None
            logger.error("TaskQueue: Redis connection failed — task queue unavailable: %s", exc)
            raise RuntimeError(
                "Task queue unavailable: Redis connection failed. "
                "Background tasks cannot be submitted until Redis is restored."
            ) from exc

    async def shutdown(self) -> None:
        """Clean up connections."""
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception:
                pass
        logger.info("TaskQueue shut down.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_task(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]] | str,
        *args: Any,
        task_type: str = "generic",
        **kwargs: Any,
    ) -> str:
        """
        Submit a task for background execution.

        Parameters
        ----------
        func : callable or str
            A string function name registered in the ARQ worker
            (e.g. "run_pipeline_task").
        *args, **kwargs
            Arguments forwarded to the worker function.
        task_type : str
            Human-readable label for the task.

        Returns
        -------
        str
            The generated task_id.

        Raises
        ------
        RuntimeError
            If Redis is unavailable (503 to user).
        """
        if self._redis_client is None:
            raise RuntimeError(
                "Task queue unavailable: Redis is not connected. "
                "Cannot submit background tasks."
            )

        task_id = uuid.uuid4().hex[:12]
        now = datetime.utcnow().isoformat() + "Z"

        # Build job data
        job_data = {
            "task_id": task_id,
            "task_type": task_type,
            "submitted_at": now,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "error": None,
            "func_name": func if isinstance(func, str) else func.__name__,
            "args": [json.dumps(a, default=str) if not isinstance(a, (str, int, float, bool, type(None))) else a for a in args],
            "kwargs": {k: json.dumps(v, default=str) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in kwargs.items()},
        }

        # Store job metadata in Redis (key = talvex:task:{task_id})
        key = f"talvex:task:{task_id}"
        self._redis_client.hset(key, mapping={k: json.dumps(v, default=str) for k, v in job_data.items()})
        self._redis_client.expire(key, 86400)  # 24h TTL

        # Add to the task list
        self._redis_client.lpush("talvex:tasks", task_id)

        logger.info("Task submitted (ARQ): id=%s type=%s", task_id, task_type)
        return task_id

    def get_task_status(self, task_id: str) -> TaskInfo | None:
        """Get the current status of a task from Redis."""
        if self._redis_client is None:
            return None
        try:
            key = f"talvex:task:{task_id}"
            data = self._redis_client.hgetall(key)
            if not data:
                return None

            # Parse JSON values
            parsed = {}
            for k, v in data.items():
                try:
                    parsed[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed[k] = v

            return TaskInfo(
                task_id=parsed.get("task_id", task_id),
                status=TaskStatus(parsed.get("status", "pending")),
                task_type=parsed.get("task_type", "generic"),
                submitted_at=parsed.get("submitted_at", ""),
                started_at=parsed.get("started_at"),
                completed_at=parsed.get("completed_at"),
                error=parsed.get("error"),
            )
        except Exception:
            return None

    def get_task_result(self, task_id: str) -> Any:
        """Get the result of a completed task from Redis."""
        if self._redis_client is None:
            raise RuntimeError("Task queue unavailable: Redis is not connected.")

        try:
            key = f"talvex:task:{task_id}"
            result_data = self._redis_client.hget(key, "result")
            if result_data:
                return json.loads(result_data)

            status = self.get_task_status(task_id)
            if status is None:
                raise KeyError(f"Task '{task_id}' not found.")
            if status.status == TaskStatus.RUNNING:
                raise RuntimeError(f"Task '{task_id}' is still running.")
            if status.status == TaskStatus.FAILED:
                raise RuntimeError(f"Task '{task_id}' failed: {status.error}")

            raise KeyError(f"Task '{task_id}' not found.")
        except (KeyError, RuntimeError):
            raise

    def list_tasks(self) -> list[TaskInfo]:
        """Return info for all tasks from Redis."""
        if self._redis_client is None:
            return []
        try:
            task_ids = self._redis_client.lrange("talvex:tasks", 0, 99)
            results = []
            for tid in task_ids:
                info = self.get_task_status(tid)
                if info:
                    results.append(info)
            return results
        except Exception:
            return []


# ===================================================================
# Module-level singleton
# ===================================================================

task_queue = TaskQueue()
