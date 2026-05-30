"""
TALVEX Structured Logging Configuration (Phase 8)

Configures rotating file handlers with size limits to prevent
log files from consuming all disk space.

Usage (in main.py or worker.py):
    from logging_config import setup_logging
    setup_logging(level=logging.INFO)
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_dir: str = "/app/logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB per file
    backup_count: int = 3,
) -> None:
    """Configure root logger with console + rotating file handlers.

    Parameters
    ----------
    level : int
        Logging level (e.g. logging.INFO, logging.DEBUG).
    log_dir : str
        Directory for log files. Created if it doesn't exist.
    max_bytes : int
        Maximum size of each log file before rotation (default 10 MB).
    backup_count : int
        Number of rotated backup files to keep (default 3).
    """
    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers (avoid duplicates on hot-reload)
    root_logger.handlers.clear()

    # ── Console handler (stdout) ────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ── Rotating file handler ──────────────────────────────
    log_file = log_path / "talvex-backend.log"
    try:
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except (PermissionError, OSError) as exc:
        # If we can't write to the log directory (e.g. in dev without /app/logs),
        # fall back to a temp directory or skip file logging.
        fallback_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "talvex-logs"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        try:
            fallback_file = fallback_dir / "talvex-backend.log"
            file_handler = RotatingFileHandler(
                filename=str(fallback_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception:
            # Last resort: skip file logging entirely
            pass

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("arq").setLevel(logging.INFO)
