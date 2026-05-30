# Task 9 — LangGraph Agent Orchestration + Async Task Queue

## Agent: Backend Services Agent

## Summary
Implemented Phase 4 backend infrastructure: LangGraph-based agent orchestration for two multi-step career workflows, and an in-memory async task queue for long-running operations.

## Files Created

### 1. `/home/z/my-project/backend/services/agent.py` (~420 lines)
LangGraph agent orchestrator with two pipeline workflows:

**Job Application Pipeline:**
- `pii_scrub` → `jd_parse` → `match_score` → `skill_gap` → (conditional) → `resume_optimize`/`resume_generate` → `pii_rehydrate` → `build_result`
- Conditional edge: if match_score >= 70, skips optimization and goes directly to generate
- Each node wraps existing services (pii_sanitizer, matcher, resume_optimizer, resume_generator)
- Error handling: each node catches exceptions, stores in State["errors"], pipeline continues
- Graceful fallback when OpenRouter key not set
- State defined as TypedDict with all intermediate fields

**Job Search & Match Pipeline:**
- `web_search` → `score_each_job` → `rank_and_filter` → `build_result`
- Uses Tavily client for web search, matcher for scoring
- Filters jobs with score < 20, returns top 10

**Exports:**
- `ApplicationPipelineState`, `JobSearchState` — TypedDict states
- `run_application_pipeline()` — async runner for job application pipeline
- `run_search_pipeline()` — async runner for job search pipeline
- `run_pipeline()` — convenience dispatcher
- `application_pipeline_graph`, `search_pipeline_graph` — compiled LangGraph graphs

### 2. `/home/z/my-project/backend/services/task_queue.py` (~200 lines)
In-memory async task queue:
- `TaskQueue` class with `submit_task()`, `get_task_status()`, `get_task_result()`, `list_tasks()`
- TaskStatus enum: pending → running → completed/failed
- TTL-based auto-cleanup (default 1 hour) with background cleanup loop
- Max task cap (default 1000) with oldest-first eviction
- `initialize()` / `shutdown()` lifecycle methods for FastAPI integration
- Module-level singleton: `task_queue`

### 3. `/home/z/my-project/backend/routers/tasks.py` (~170 lines)
FastAPI router with 3 endpoints:
- `POST /api/tasks/submit` — Submit pipeline task (optimize_resume/search_jobs/job_application/job_search)
- `GET /api/tasks/{task_id}` — Get task status and result
- `GET /api/tasks` — List all tasks
- Pydantic request/response models

## Files Modified

### 4. `/home/z/my-project/backend/main.py`
- Added `tasks` router import and `app.include_router(tasks.router)`
- Added task queue initialization in lifespan startup (`await _tq.initialize()`)
- Added task queue shutdown in lifespan shutdown (`await _tq.shutdown()`)

### 5. `/home/z/my-project/backend/requirements.txt`
- Added `langgraph>=0.2.0`
- Added `openai>=1.0.0` (for OpenRouter client)

## Verification
- All imports verified: `from backend.services.agent import ...` ✓
- All imports verified: `from backend.services.task_queue import ...` ✓
- All imports verified: `from backend.routers.tasks import ...` ✓
- LangGraph graphs compile successfully: `CompiledStateGraph` ✓
- All new files pass Python AST syntax check ✓
- `langgraph>=1.2.1` installed in venv ✓
