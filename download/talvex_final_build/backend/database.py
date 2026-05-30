"""
SQLAlchemy ASYNC database setup for TALVEX backend.
Connects to PostgreSQL (or SQLite for local dev) via DATABASE_URL env var.
Uses AsyncSession pattern for non-blocking database operations in FastAPI.
"""

import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, async_scoped_session
from sqlalchemy.orm import declarative_base, scoped_session
import asyncio

# Load .env from project root
from dotenv import load_dotenv
_project_root = Path(__file__).resolve().parent.parent
_load_env_path = _project_root / ".env"
if _load_env_path.exists():
    load_dotenv(_load_env_path)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Local development fallback to SQLite (async via aiosqlite)
    f"sqlite+aiosqlite:///{_project_root / 'db' / 'custom.db'}"
)

# SQLAlchemy async engine configuration
engine_kwargs: dict = {"echo": False}

# PostgreSQL-specific settings
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

# SQLite-specific settings
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    """Dependency for FastAPI to get an async DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_raw_db():
    """Get a raw async session (not scoped) for background tasks."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
