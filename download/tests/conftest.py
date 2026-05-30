"""
Shared fixtures and configuration for the TALVEX test suite.

Validates:
  - Phase 5: Critical Fixes & Cleanup
  - Phase 6: Architecture Migration (Separate Frontend + Backend)
  - Material 3 Design Token Adoption
  - Ghost Subsystem Purge
  - Rate Limiting
  - PII Sanitization Pipeline
  - OpenRouter Client Integration
  - Timeout Standardization
"""

import os
import sys
import ast
import re
import time
import asyncio
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup — backend/ is the Python source root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

# Add backend/ to sys.path so we can import services directly
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# File content readers (cached)
# ---------------------------------------------------------------------------
_file_cache: dict[str, str] = {}

def read_service_file(relative_path: str) -> str:
    """Read a file from backend/services/ (cached)."""
    abs_path = str(BACKEND_DIR / "services" / relative_path)
    if abs_path not in _file_cache:
        with open(abs_path, "r") as f:
            _file_cache[abs_path] = f.read()
    return _file_cache[abs_path]


def read_router_file(relative_path: str) -> str:
    """Read a file from backend/routers/ (cached)."""
    abs_path = str(BACKEND_DIR / "routers" / relative_path)
    if abs_path not in _file_cache:
        with open(abs_path, "r") as f:
            _file_cache[abs_path] = f.read()
    return _file_cache[abs_path]


def read_source_file(relative_path: str) -> str:
    """Read a file from project root (cached)."""
    abs_path = str(PROJECT_ROOT / relative_path)
    if abs_path not in _file_cache:
        with open(abs_path, "r") as f:
            _file_cache[abs_path] = f.read()
    return _file_cache[abs_path]


# ---------------------------------------------------------------------------
# Code analysis helpers
# ---------------------------------------------------------------------------

def find_all_python_files(directory: Path, exclude_patterns: list[str] | None = None) -> list[Path]:
    """Recursively find all .py files in a directory."""
    exclude = exclude_patterns or ["__pycache__", ".pytest_cache", "node_modules"]
    results = []
    for path in directory.rglob("*.py"):
        if any(part in path.parts for part in exclude):
            continue
        results.append(path)
    return results


def grep_pattern_in_file(file_path: str, pattern: str) -> list[tuple[int, str]]:
    """Grep for pattern in a file, returning (line_number, line_text) tuples."""
    matches = []
    try:
        with open(file_path, "r") as f:
            for i, line in enumerate(f, 1):
                if re.search(pattern, line):
                    matches.append((i, line.rstrip()))
    except (FileNotFoundError, PermissionError):
        pass
    return matches


def grep_pattern_in_directory(
    directory: Path,
    pattern: str,
    exclude_dirs: list[str] | None = None,
) -> list[tuple[str, int, str]]:
    """Grep for pattern across all .py files in a directory."""
    exclude = exclude_dirs or ["__pycache__", ".pytest_cache", "node_modules"]
    results = []
    for path in find_all_python_files(directory, exclude):
        for line_num, line_text in grep_pattern_in_file(str(path), pattern):
            # Skip comment-only matches for certain patterns
            results.append((str(path.relative_to(PROJECT_ROOT)), line_num, line_text))
    return results


# ---------------------------------------------------------------------------
# Async test support
# ---------------------------------------------------------------------------

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Service import fixtures (lazy — only import if available)
# ---------------------------------------------------------------------------

@pytest.fixture
def pii_sanitizer():
    """Import and return PIISanitizer class."""
    from services.pii_sanitizer import PIISanitizer
    return PIISanitizer


@pytest.fixture
def pii_vault():
    """Import and return PIIVault singleton."""
    from services.pii_sanitizer import pii_vault
    return pii_vault


@pytest.fixture
def rate_limiter_module():
    """Import and return the rate_limiter module."""
    from services import rate_limiter
    return rate_limiter


@pytest.fixture
def openrouter_client_module():
    """Import and return the openrouter_client module."""
    from services import openrouter_client
    return openrouter_client


@pytest.fixture
def llm_service_module():
    """Import and return the llm_service module."""
    from services import llm_service
    return llm_service


@pytest.fixture
def resume_optimizer_module():
    """Import and return the resume_optimizer module."""
    from services import resume_optimizer
    return resume_optimizer


@pytest.fixture
def agent_module():
    """Import and return the agent module."""
    from services import agent
    return agent
