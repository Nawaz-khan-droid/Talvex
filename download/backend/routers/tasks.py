"""
TALVEX Tasks Router

FastAPI router that exposes the async task queue for long-running pipeline
operations (resume optimization, job search, etc.).

Endpoints
---------
POST /api/tasks/submit   — Submit a pipeline task
GET  /api/tasks          — List all tasks
GET  /api/tasks/{task_id} — Get task status and result
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ===================================================================
# Request / Response schemas
# ===================================================================

class SubmitTaskRequest(BaseModel):
    """Body for POST /api/tasks/submit."""
    pipeline: Literal["optimize_resume", "search_jobs", "job_application", "job_search"] = Field(
        ...,
        description="The pipeline to execute.",
    )

    # --- Job Application Pipeline fields ---
    raw_jd: str = Field("", description="Raw job description text.")
    raw_resume: str = Field("", description="Raw resume text.")
    career_stage: str = Field("mid_level", description="Career stage for optimization.")
    template_type: str = Field("chronological", description="Resume template type.")

    # --- Job Search Pipeline fields ---
    query: str = Field("", description="Job search query (e.g. 'Python Developer').")
    location: str = Field("", description="Location filter for job search.")
    user_skills: list[str] = Field(default_factory=list, description="User's skill set for scoring.")


class TaskSubmittedResponse(BaseModel):
    """Response after submitting a task."""
    task_id: str
    status: str
    message: str


class TaskInfoResponse(BaseModel):
    """Response for task status."""
    task_id: str
    status: str
    task_type: str
    submitted_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    result: Any = None


class TaskListResponse(BaseModel):
    """Response for listing all tasks."""
    tasks: list[TaskInfoResponse]
    total: int


# ===================================================================
# Pipeline dispatch function
# ===================================================================

async def _dispatch_pipeline(req: SubmitTaskRequest) -> dict[str, Any]:
    """Route the request to the correct LangGraph pipeline."""
    # Lazy import to avoid circular imports at module load
    from services.agent import run_pipeline

    if req.pipeline in ("optimize_resume", "job_application"):
        return await run_pipeline(
            pipeline_type="job_application",
            raw_jd=req.raw_jd,
            raw_resume=req.raw_resume,
            career_stage=req.career_stage,
            template_type=req.template_type,
        )
    elif req.pipeline in ("search_jobs", "job_search"):
        return await run_pipeline(
            pipeline_type="job_search",
            query=req.query,
            location=req.location,
            user_skills=req.user_skills,
        )
    else:
        return {
            "success": False,
            "errors": [f"Unknown pipeline type: {req.pipeline}"],
        }


# ===================================================================
# Endpoints
# ===================================================================

@router.post("/submit", response_model=TaskSubmittedResponse)
async def submit_task(req: SubmitTaskRequest, current_user: dict = Depends(get_current_user)):
    """
    Submit a pipeline task for async execution.

    Accepted pipeline values:
    - ``optimize_resume`` / ``job_application`` — Full resume optimization pipeline
    - ``search_jobs`` / ``job_search`` — Job search & match pipeline

    Returns a task_id that can be polled for status/results.
    """
    # Lazy-init the task queue on first use
    from services.task_queue import task_queue

    if not task_queue._initialized:
        await task_queue.initialize()

    task_id = await task_queue.submit_task(
        _dispatch_pipeline,
        req,
        task_type=req.pipeline,
    )

    return TaskSubmittedResponse(
        task_id=task_id,
        status="pending",
        message=f"Task submitted successfully. Poll /api/tasks/{task_id} for status.",
    )


@router.get("/{task_id}", response_model=TaskInfoResponse)
async def get_task(task_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get the status and (if completed) result of a task.
    """
    from services.task_queue import task_queue

    info = task_queue.get_task_status(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found. It may have expired.")

    result = None
    if info.status in ("completed", "failed"):
        try:
            result = task_queue.get_task_result(task_id)
        except RuntimeError:
            pass  # task may still be running (race condition)
        except KeyError:
            pass

    return TaskInfoResponse(
        task_id=info.task_id,
        status=info.status,
        task_type=info.task_type,
        submitted_at=info.submitted_at,
        started_at=info.started_at,
        completed_at=info.completed_at,
        error=info.error,
        result=result,
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(current_user: dict = Depends(get_current_user)):
    """
    List all tasks currently in memory.
    """
    from services.task_queue import task_queue

    infos = task_queue.list_tasks()
    return TaskListResponse(
        tasks=[
            TaskInfoResponse(
                task_id=i.task_id,
                status=i.status,
                task_type=i.task_type,
                submitted_at=i.submitted_at,
                started_at=i.started_at,
                completed_at=i.completed_at,
                error=i.error,
                result=None,  # Don't embed results in list view
            )
            for i in infos
        ],
        total=len(infos),
    )
