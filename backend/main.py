"""
TALVEX - Job Application Command Center
FastAPI backend application.

Zero Trust Architecture (Phase 7):
  - ASGI middleware stack: IP Blocklist -> Security Headers -> CSRF -> CORS
  - Stateful JWT auth backed by Redis (instant session revocation)
  - RBAC with admin/user roles
  - Per-user daily resource quotas
  - Brute-force protection (5 attempts -> 15 min lockout)
  - Automated IP blocking on repeated violations
  - Prompt injection detection on LLM inputs
  - Encrypted BYOK API key storage (Fernet)
  - CSP, HSTS, X-Content-Type-Options, Permissions-Policy headers
"""

import os
import logging
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import AsyncSessionLocal
from models import User
from sqlalchemy import select

# Configure structured logging with file rotation (Phase 8)
from logging_config import setup_logging
setup_logging(level=logging.INFO)
logger = logging.getLogger("talvex")

# Track server start time for uptime reporting
_start_time = _time.monotonic()

# ============================================================
# Allowed origins for CORS (from environment)
# ============================================================

_ALLOWED_ORIGINS_RAW = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000",  # Default for local development
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in _ALLOWED_ORIGINS_RAW.split(",")
    if origin.strip()
]


async def _bootstrap_admin_user() -> None:
    """Create the admin user from environment variables on startup.

    Reads ADMIN_EMAIL and ADMIN_PASSWORD from the environment. If both are
    set and no admin user exists, creates one. If an admin already exists,
    does nothing. If the env vars are missing, logs a critical warning
    (the app still starts but no admin account is available).

    This is the ONLY way to create an admin account. The public /register
    endpoint hard-codes role='user' and cannot be used to bootstrap admin.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not admin_email or not admin_password:
        logger.critical(
            "ADMIN_EMAIL and/or ADMIN_PASSWORD are not set. "
            "No admin account will be created. "
            "To create an admin, set both environment variables and restart."
        )
        return

    try:
        async with AsyncSessionLocal() as db:
            # Check if any admin already exists
            result = await db.execute(select(User).filter(User.role == "admin"))
            existing_admin = result.scalar_one_or_none()
            if existing_admin:
                logger.info(
                    "Admin user already exists (email=%s). Skipping bootstrap.",
                    existing_admin.email,
                )
                return

            # Check if the ADMIN_EMAIL is already registered as a normal user
            result = await db.execute(select(User).filter(User.email == admin_email))
            existing_user = result.scalar_one_or_none()
            if existing_user:
                # Promote existing user to admin
                from auth import hash_password
                existing_user.role = "admin"
                existing_user.passwordHash = hash_password(admin_password)
                await db.commit()
                logger.info(
                    "Promoted existing user %s to admin role via ADMIN_EMAIL env var.",
                    admin_email,
                )
                return

            # Create a fresh admin user
            import uuid
            from auth import hash_password

            admin = User(
                id=str(uuid.uuid4()),
                email=admin_email,
                passwordHash=hash_password(admin_password),
                displayName="Admin",
                role="admin",
                isActive=True,
            )
            db.add(admin)
            await db.commit()
            logger.info(
                "Admin account created via environment bootstrap: %s", admin_email
            )
    except Exception as exc:
        logger.critical(
            "Failed to bootstrap admin user: %s. "
            "Check ADMIN_EMAIL and ADMIN_PASSWORD environment variables.",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    # Startup: verify database connection
    logger.info("TALVEX Backend starting up (Zero Trust mode)...")
    from services.prompt_manager import validate_prompt_templates
    validate_prompt_templates()

    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Cannot connect to database: {e}") from e

    # Run Alembic migrations on startup (replaces create_all)
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_command
        alembic_cfg = AlembicConfig(str(Path(__file__).parent / "alembic.ini"))
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully.")
    except Exception as e:
        logger.warning(f"Alembic migration failed (may need manual run): {e}")

    # Bootstrap admin user from environment variables (out-of-band, not via public API)
    await _bootstrap_admin_user()

    # Initialize the async task queue
    from services.task_queue import task_queue as _tq
    await _tq.initialize()
    logger.info("Task queue initialised.")

    logger.info("All routers loaded. TALVEX is ready.")
    yield

    # Shutdown: clean up task queue
    await _tq.shutdown()

    # Shutdown: flush Langfuse traces
    try:
        from services.langfuse_client import shutdown as langfuse_shutdown
        langfuse_shutdown()
    except Exception:
        pass

    logger.info("TALVEX Backend shutting down.")


# ============================================================
# Create FastAPI app
# ============================================================

app = FastAPI(
    title="TALVEX - Job Application Command Center",
    description="Backend API for the TALVEX job application pipeline. "
                "Manage job personas, applications, resumes, canary emails, analytics, and recommendations.",
    version="2.0.0",  # Bumped for Zero Trust Phase 7
    lifespan=lifespan,
)

# ============================================================
# ASGI Middleware Stack (order matters: outermost first)
#
# Execution order for a request:
#   IP Blocklist -> Security Headers -> CSRF -> CORS -> Route Handler
#
# Execution order for a response:
#   Route Handler -> CORS -> CSRF -> Security Headers -> IP Blocklist
# ============================================================

from middleware.defense import (
    IPBlocklistMiddleware,
    SecurityHeadersMiddleware,
    CSRFMiddleware,
)

# Layer 1: IP Blocklist (outermost — drop blocked IPs before anything else)
app.add_middleware(IPBlocklistMiddleware)

# Layer 2: Security Headers (CSP, HSTS, X-Content-Type-Options, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Layer 3: CSRF Protection (double-submit cookie pattern)
app.add_middleware(CSRFMiddleware)

# Layer 4: CORS (innermost — after all security checks)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
    max_age=3600,
)


# ============================================================
# Health check (PUBLIC — no auth required)
# ============================================================

@app.get("/", tags=["health"])
def health_check():
    """Health check endpoint — always public."""
    return {
        "status": "healthy",
        "service": "TALVEX Backend",
        "version": "2.0.0",
    }


@app.get("/health", tags=["health"])
async def health_detailed():
    """Detailed health check with database verification."""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "service": "TALVEX Backend",
        "version": "2.0.0",
    }


# ============================================================
# Include routers
# ============================================================

# Auth router (PUBLIC endpoints: register, login, logout)
from auth import router as auth_router
app.include_router(auth_router)

# Admin router (ADMIN-ONLY: user management, system health)
from routers import admin
app.include_router(admin.router)

# Settings router (AUTH REQUIRED: BYOK key storage)
from routers import settings
app.include_router(settings.router)

# Business logic routers (AUTH REQUIRED)
from routers import jobs, applications, personas, resume, canary, analytics, recommendations, llm, search, tasks

app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(personas.router)
app.include_router(resume.router)
app.include_router(canary.router)
app.include_router(analytics.router)
app.include_router(recommendations.router)
app.include_router(llm.router)
app.include_router(search.router)
app.include_router(tasks.router)


# ============================================================
# Global exception handler
# ============================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "status_code": 500,
        },
    )
