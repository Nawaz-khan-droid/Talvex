"""
TALVEX Alembic environment configuration.

Reads DATABASE_URL from the environment (same .env as the app).
Auto-imports all SQLAlchemy models so that --autogenerate detects them.
Supports both online (connected) and offline (SQL script) modes.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Load .env from project root ─────────────────────────────
import os
from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# ── Alembic Config object ───────────────────────────────────
config = context.config

# Override sqlalchemy.url from environment.
# IMPORTANT: Alembic requires a synchronous driver. The app uses asyncpg,
# but Alembic migrations run synchronously via psycopg2.
database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://talvex:t4lv3x_s3cur3@talvex-db:5432/talvex",
)
# Convert asyncpg URL to psycopg2 for Alembic (sync-only)
database_url = database_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", database_url)

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import all models so Alembic can auto-detect them ──────
# The metadata from Base is used by --autogenerate to detect
# schema changes.  We must import models AFTER database.py has
# been loaded (so that Base is defined) but BEFORE we access
# target_metadata.
import sys
# Ensure the backend directory is on sys.path for model imports
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from database import Base  # noqa: E402
import models  # noqa: F401, E402 — triggers all model registrations

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
