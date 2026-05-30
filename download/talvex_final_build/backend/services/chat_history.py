"""
TALVEX Telegram Chat History — PostgreSQL Persistence (via SQLAlchemy)

Replaces the old SQLite-based implementation.  Chat messages are now stored
in the PostgreSQL database alongside all other TALVEX data, ensuring they
are included in Alembic migrations, survive container recreation, and are
backed up with the rest of the database.

Each user (identified by Telegram chat_id) has an isolated message store.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MAX_HISTORY_PER_USER = 200      # Keep last 200 messages per user
_MAX_USERS = 500                 # Maximum distinct users tracked


class ChatHistory:
    """
    PostgreSQL-backed chat history with per-user isolation.

    All methods accept an ``AsyncSession`` and are ``async``.
    The session lifecycle (commit/rollback) is managed by the caller
    or via ``async with AsyncSessionLocal() as db``.

    Usage::

        from database import AsyncSessionLocal
        from services.chat_history import chat_history

        async with AsyncSessionLocal() as db:
            await chat_history.add_message(db, "123456", "user", "Analyze my resume")
            await chat_history.add_message(db, "123456", "assistant", "Here is the analysis...", intent="ats_score")
            messages = await chat_history.get_messages(db, "123456", limit=20)
            await db.commit()
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_message(
        self,
        db: AsyncSession,
        chat_id: str,
        role: str,
        content: str,
        *,
        intent: str | None = None,
        confidence: float | None = None,
        model_used: str | None = None,
    ) -> None:
        """Insert a message into the history."""
        from models import ChatHistory as CH

        now = time.time()
        try:
            db.add(CH(
                chatId=chat_id,
                role=role,
                content=content,
                intent=intent,
                confidence=confidence,
                modelUsed=model_used,
                createdAt=now,
            ))

            # Enforce per-user cap (delete oldest messages beyond limit)
            await self._enforce_user_cap(db, chat_id)
        except Exception as exc:
            logger.error("Failed to insert chat message: %s", exc)
            raise

    async def get_messages(
        self,
        db: AsyncSession,
        chat_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get recent messages for a user, formatted for LLM context.

        Returns list of dicts: [{"role": "user"|"assistant", "content": "..."}]
        """
        from models import ChatHistory as CH

        try:
            result = await db.execute(
                select(CH)
                .where(CH.chatId == chat_id)
                .order_by(CH.createdAt.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            # Return in chronological order (oldest first)
            return [{"role": r.role, "content": r.content} for r in reversed(rows)]
        except Exception as exc:
            logger.error("Failed to fetch chat history: %s", exc)
            return []

    async def get_formatted_context(
        self,
        db: AsyncSession,
        chat_id: str,
        limit: int = 20,
    ) -> list[dict[str, str]]:
        """
        Get messages formatted as OpenAI-compatible message list.

        Returns: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        messages = await self.get_messages(db, chat_id, limit=limit)
        return [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]

    async def clear_user_history(self, db: AsyncSession, chat_id: str) -> int:
        """Delete all messages for a specific user. Returns count deleted."""
        from models import ChatHistory as CH

        try:
            result = await db.execute(
                delete(CH).where(CH.chatId == chat_id)
            )
            return result.rowcount
        except Exception as exc:
            logger.error("Failed to clear user history: %s", exc)
            return 0

    async def get_user_count(self, db: AsyncSession) -> int:
        """Get the number of distinct users with history."""
        from models import ChatHistory as CH

        try:
            result = await db.execute(
                select(func.count(func.distinct(CH.chatId)))
            )
            return result.scalar() or 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Internal: cap enforcement
    # ------------------------------------------------------------------

    async def _enforce_user_cap(self, db: AsyncSession, chat_id: str) -> None:
        """Delete oldest messages beyond the per-user cap."""
        from models import ChatHistory as CH

        # Subquery: IDs of the N most recent messages for this chat_id
        keep_subq = (
            select(CH.id)
            .where(CH.chatId == chat_id)
            .order_by(CH.createdAt.desc())
            .limit(_MAX_HISTORY_PER_USER)
        )
        # Delete messages NOT in the keep list
        await db.execute(
            delete(CH).where(
                CH.chatId == chat_id,
                CH.id.notin_(keep_subq),
            )
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

chat_history = ChatHistory()
