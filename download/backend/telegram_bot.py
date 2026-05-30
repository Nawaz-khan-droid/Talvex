"""
TALVEX Telegram Bot — async python-telegram-bot v21+

A secure, rate-limited Telegram bot that acts as the conversational interface
for the TALVEX ATS platform.  Every interaction is guarded by an allow-list
of trusted Telegram user IDs, rate-limited per user, and persisted to SQLite
via the shared chat_history service.

Features:
  * Security gatekeeper (ALLOWED_TELEGRAM_IDS)
  * In-memory per-user rate limiting
  * Chat history persistence (SQLite-backed)
  * Intent detection and routing via the agent service
  * Inline keyboard navigation
  * Processing indicators for specialist agents
  * Commands: /start, /help, /status, /recent, /search, /recommend, /clear
  * Natural-language message handler (routes through agent)
  * Callback query handler (inline button presses)

Environment:
  TELEGRAM_BOT_TOKEN   — Bot token from @BotFather
  ALLOWED_TELEGRAM_IDS — Comma-separated list of trusted Telegram user IDs
  BACKEND_URL          — FastAPI base URL (default: http://localhost:8000)
  TELEGRAM_RATE_LIMIT  — Minimum seconds between requests per user (default: 2)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import httpx

# ---------------------------------------------------------------------------
# Imports — internal services (graceful fallback)
# ---------------------------------------------------------------------------

try:
    from services.chat_history import chat_history
except ImportError:
    chat_history = None  # type: ignore[assignment]

try:
    from services.agent import classify_intent, route_and_execute
except ImportError:
    classify_intent = None  # type: ignore[assignment, misc]
    route_and_execute = None  # type: ignore[assignment, misc]

# ---------------------------------------------------------------------------
# Configuration — load from .env first, then environment
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_TELEGRAM_IDS_RAW: str = os.getenv("ALLOWED_TELEGRAM_IDS", "")
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
TELEGRAM_RATE_LIMIT: float = float(os.getenv("TELEGRAM_RATE_LIMIT", "2"))

# Parse allowed IDs into a set of strings
ALLOWED_IDS: set[str] = {
    uid.strip() for uid in ALLOWED_TELEGRAM_IDS_RAW.split(",") if uid.strip()
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation — log warnings, never crash
# ---------------------------------------------------------------------------

if not TELEGRAM_BOT_TOKEN:
    logger.error(
        "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather and "
        "set it in .env or environment. Bot will idle."
    )
if not ALLOWED_IDS:
    logger.warning(
        "ALLOWED_TELEGRAM_IDS is empty — nobody will be able to use the bot."
    )

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

_http = httpx.AsyncClient(base_url=BACKEND_URL, timeout=30.0)

# ---------------------------------------------------------------------------
# Rate limiter — simple in-memory per-user cooldown
# ---------------------------------------------------------------------------

_last_request_time: dict[str, float] = {}
_RATE_LIMIT = TELEGRAM_RATE_LIMIT
_CLEANUP_THRESHOLD = 300.0  # 5 minutes in seconds


def _is_rate_limited(user_key: str) -> float | None:
    """
    Check if the user is rate-limited.

    Returns the number of seconds the user must wait, or None if not limited.
    Also cleans up stale entries.
    """
    now = time.time()
    # Periodic cleanup of old entries
    if len(_last_request_time) > 1000:
        stale = [
            k for k, t in _last_request_time.items()
            if now - t > _CLEANUP_THRESHOLD
        ]
        for k in stale:
            del _last_request_time[k]

    last = _last_request_time.get(user_key)
    if last is not None:
        elapsed = now - last
        if elapsed < _RATE_LIMIT:
            return _RATE_LIMIT - elapsed

    _last_request_time[user_key] = now
    return None


# ---------------------------------------------------------------------------
# Security gatekeeper
# ---------------------------------------------------------------------------

def _is_authorized(user_id: str | int) -> bool:
    """Return True if the user is in the allowed list."""
    return str(user_id) in ALLOWED_IDS


# ---------------------------------------------------------------------------
# Specialist intents that need a processing indicator
# ---------------------------------------------------------------------------

_SPECIALIST_INTENTS = frozenset({
    "ats_score",
    "resume_build",
    "job_search",
    "research",
    "pdf_parse",
})

# ---------------------------------------------------------------------------
# MarkdownV2 helpers
# ---------------------------------------------------------------------------

_MD_SPECIAL: set[str] = set(r"_*[]()~`>#+-=|{}.!")


def _escape_md(text: str) -> str:
    """Escape all MarkdownV2 special characters."""
    return "".join(f"\\{c}" if c in _MD_SPECIAL else c for c in text)


def _send_md(update: Update, text: str, **kwargs: Any) -> None:
    """
    Send a MarkdownV2 message, automatically escaping the text.

    Extra kwargs are forwarded to reply_text / edit_message_text.
    """
    escaped = _escape_md(text)
    try:
        update.message.reply_text(escaped, parse_mode="MarkdownV2", **kwargs)  # type: ignore[union-attr]
    except Exception:
        # Fallback to plain text if MarkdownV2 fails
        update.message.reply_text(text, **kwargs)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _fetch(endpoint: str) -> dict | list | None:
    """GET a FastAPI endpoint and return JSON, or None on error."""
    try:
        resp = await _http.get(endpoint)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.error("Cannot connect to backend at %s", BACKEND_URL)
        return None
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Backend GET %s returned %s: %s",
            endpoint, exc.response.status_code, exc.response.text[:300],
        )
        return None
    except Exception as exc:
        logger.error("Request to %s failed: %s", endpoint, exc)
        return None


async def _fetch_post(endpoint: str, json: dict | None = None) -> dict | list | None:
    """POST to a FastAPI endpoint and return JSON, or None on error."""
    try:
        resp = await _http.post(endpoint, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        logger.error("Cannot connect to backend at %s", BACKEND_URL)
        return None
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Backend POST %s returned %s: %s",
            endpoint, exc.response.status_code, exc.response.text[:300],
        )
        return None
    except Exception as exc:
        logger.error("Request to %s failed: %s", endpoint, exc)
        return None


# ---------------------------------------------------------------------------
# Inline keyboards
# ---------------------------------------------------------------------------

def _main_keyboard() -> InlineKeyboardMarkup:
    """Build the main inline keyboard with 2x2 buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 ATS Score", callback_data="cb_ats_score"),
            InlineKeyboardButton("📄 Resume Build", callback_data="cb_resume_build"),
        ],
        [
            InlineKeyboardButton("🔍 Job Search", callback_data="cb_job_search"),
            InlineKeyboardButton("❓ Help", callback_data="cb_help"),
        ],
    ])


# ---------------------------------------------------------------------------
# Common pre-checks: auth + rate-limit
# ---------------------------------------------------------------------------

async def _precheck(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    Run security and rate-limit checks before processing any handler.

    Returns True if the request should proceed, False if it was blocked
    (in which case a reply has already been sent).
    """
    # Determine user_id from either message or callback query
    user_id = _get_user_id(update)

    # Security gatekeeper
    if not _is_authorized(user_id):
        logger.warning("Unauthorized access attempt from user_id=%s", user_id)
        await _reply_or_answer(update, "⛔ Access denied.")
        return False

    # Rate limiting
    wait = _is_rate_limited(str(user_id))
    if wait is not None:
        await _reply_or_answer(
            update,
            f"⏳ Slow down! Please wait {wait:.1f} seconds.",
        )
        return False

    return True


def _get_user_id(update: Update) -> str | int:
    """Extract the user ID from either a message or a callback query."""
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    if update.message and update.message.from_user:
        return update.message.from_user.id
    return "unknown"


async def _reply_or_answer(update: Update, text: str) -> None:
    """Reply to a message or answer a callback query with the given text."""
    if update.callback_query:
        await update.callback_query.answer(text)
        # Also edit the message if possible
        try:
            await update.callback_query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(text)


# ---------------------------------------------------------------------------
# Chat history helpers
# ---------------------------------------------------------------------------

async def _record_user_message(chat_id: str, text: str) -> None:
    """Persist a user message to chat history."""
    if chat_history is not None:
        from database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                await chat_history.add_message(db, chat_id, "user", text)
                await db.commit()
        except Exception as exc:
            logger.error("Failed to record user message: %s", exc)


async def _record_assistant_message(
    chat_id: str,
    text: str,
    *,
    intent: str | None = None,
    confidence: float | None = None,
    model_used: str | None = None,
) -> None:
    """Persist an assistant response to chat history."""
    if chat_history is not None:
        from database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                await chat_history.add_message(
                    db,
                    chat_id,
                    "assistant",
                    text,
                    intent=intent,
                    confidence=confidence,
                    model_used=model_used,
                )
                await db.commit()
        except Exception as exc:
            logger.error("Failed to record assistant message: %s", exc)


async def _get_history_context(chat_id: str, limit: int = 20) -> list[dict[str, str]]:
    """Retrieve formatted chat history for LLM context."""
    if chat_history is not None:
        from database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                return await chat_history.get_formatted_context(db, chat_id, limit=limit)
        except Exception as exc:
            logger.error("Failed to get history context: %s", exc)
    return []


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with inline keyboard."""
    if not await _precheck(update, context):
        return

    welcome_text = (
        "Welcome to Talvex ATS Assistant\n\n"
        "I can help you with:\n"
        "- ATS resume scoring\n"
        "- Resume optimization\n"
        "- Job matching & role suggestions\n"
        "- Resume template building\n"
        "- PDF resume parsing & analysis\n"
        "- Career guidance workflows\n\n"
        "Your conversations are private and securely isolated.\n\n"
        "Type a message or choose an option below:"
    )

    await update.message.reply_text(  # type: ignore[union-attr]
        welcome_text,
        reply_markup=_main_keyboard(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all commands with inline keyboard."""
    if not await _precheck(update, context):
        return

    help_text = (
        "❓ TALVEX Bot Commands\n\n"
        "🚀 /start — Welcome message and feature overview\n"
        "📊 /status — Application pipeline summary (total, by status)\n"
        "📋 /recent — Last 5 applications with match scores\n"
        "🔍 /search <query> — Search jobs via Tavily API\n"
        "📈 /recommend — Skill gap analysis via LLM\n"
        "🗑 /clear — Clear your chat history\n"
        "❓ /help — Show this help message\n\n"
        '💡 Tip: Use /search "Python Developer remote" to find jobs.\n\n'
        "You can also just type a natural message and I will figure out "
        "what you need!"
    )

    await update.message.reply_text(  # type: ignore[union-attr]
        help_text,
        reply_markup=_main_keyboard(),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show application pipeline summary."""
    if not await _precheck(update, context):
        return

    data = await _fetch("/api/recommendations/pipeline")
    if not data:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Could not reach the TALVEX backend. "
            "Please make sure the backend is running on port 8000."
        )
        return

    if not isinstance(data, dict):
        data = {}

    total = data.get("totalApplications", 0)
    avg_score = data.get("averageMatchScore", 0)
    high_match = data.get("highMatchCount", 0)
    breakdown = data.get("statusBreakdown", {})

    if total == 0:
        await update.message.reply_text(  # type: ignore[union-attr]
            "📭 No applications in your pipeline yet.\n"
            "Start adding jobs to see your pipeline status!"
        )
        return

    status_emoji: dict[str, str] = {
        "Scraped": "📥", "Tailored": "✏️", "Submitted": "📤",
        "Screening": "👀", "Assessment": "📝", "Interviewing": "🎤",
        "Offer": "🎉", "Rejected": "❌", "Ghosted": "👻",
    }
    status_lines: list[str] = []
    for status, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        emoji = status_emoji.get(status, "📌")
        status_lines.append(f"  {emoji} {status}: {count}")

    breakdown_text = "\n".join(status_lines)
    response = (
        f"📊 *Pipeline Summary*\n\n"
        f"Total Applications: *{_escape_md(str(total))}*\n"
        f"Avg Match Score: *{_escape_md(str(avg_score))}%*\n"
        f"High Match (≥70%): *{_escape_md(str(high_match))}*\n\n"
        f"*By Status:*\n{breakdown_text}"
    )

    await update.message.reply_text(response, parse_mode="MarkdownV2")  # type: ignore[union-attr]


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List last 5 applications with match scores."""
    if not await _precheck(update, context):
        return

    data = await _fetch("/api/applications")
    if not data:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Could not reach the TALVEX backend. "
            "Please make sure the backend is running on port 8000."
        )
        return

    if not isinstance(data, list) or len(data) == 0:
        await update.message.reply_text(  # type: ignore[union-attr]
            "📭 No applications found. "
            "Start adding jobs to see them here!"
        )
        return

    recent = data[:5]
    lines: list[str] = ["📋 *Recent Applications*\n"]

    for i, app in enumerate(recent, 1):
        company = _escape_md(str(app.get("company", "Unknown")))
        role = _escape_md(str(app.get("roleTitle", "Unknown")))
        status = _escape_md(str(app.get("status", "N/A")))
        match = float(app.get("matchScore", 0))
        ats = float(app.get("atsScore", 0))

        score_bar = "🟢" if match >= 70 else ("🟡" if match >= 40 else "🔴")
        lines.append(
            f"*{i}\\. {role}* @ {company}\n"
            f"  {score_bar} Match: {_escape_md(str(match))}% | ATS: {_escape_md(str(ats))}%\n"
            f"  Status: {status}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="MarkdownV2")  # type: ignore[union-attr]


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search jobs via Tavily API through backend."""
    if not await _precheck(update, context):
        return

    if not context.args:
        await update.message.reply_text(  # type: ignore[union-attr]
            "🔍 *Job Search*\n\n"
            "Usage: `/search <query>`\n\n"
            "Examples:\n"
            "  `/search Python Developer remote`\n"
            "  `/search Data Analyst New York`\n"
            "  `/search Frontend React full\\-time`",
            parse_mode="MarkdownV2",
        )
        return

    query = " ".join(context.args)
    escaped_query = _escape_md(query)

    await update.message.reply_text(  # type: ignore[union-attr]
        f"🔍 Searching for *{escaped_query}*\\.\\.\\.",
        parse_mode="MarkdownV2",
    )

    data = await _fetch_post(
        "/api/jobs/tavily-search",
        json={"query": query, "max_results": 5},
    )

    if not data:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Search failed. The backend may be unavailable or the Tavily "
            "API key may not be configured. Check the /status command to "
            "verify the backend is running."
        )
        return

    # Handle different response formats
    jobs: list[dict] = []
    if isinstance(data, list):
        jobs = data
    elif isinstance(data, dict):
        jobs = data.get("results", data.get("jobs", []))

    if not jobs:
        await update.message.reply_text(  # type: ignore[union-attr]
            f"📭 No jobs found for *{escaped_query}*.\n"
            f"Try different keywords or a broader search.",
            parse_mode="MarkdownV2",
        )
        return

    lines = [f"🔍 *Search Results for \"{escaped_query}\"*\n"]
    for i, job in enumerate(jobs[:5], 1):
        title = _escape_md(str(job.get("title", "Unknown")))
        company = _escape_md(str(job.get("company", "")))
        location = _escape_md(str(job.get("location", "")))
        url = str(job.get("url", ""))

        line = f"*{i}\\. {title}*"
        if company:
            line += f" \\- {company}"
        if location:
            line += f" \\| {location}"
        if url:
            line += f"\n  🔗 [View Job]({url})"
        lines.append(line)

    await update.message.reply_text("\n\n".join(lines), parse_mode="MarkdownV2")  # type: ignore[union-attr]


async def cmd_recommend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get skill gap analysis via LLM."""
    if not await _precheck(update, context):
        return

    await update.message.reply_text(  # type: ignore[union-attr]
        "📈 Analyzing skill gaps\\.\\.\\. This may take a moment\\.",
        parse_mode="MarkdownV2",
    )

    personas_data = await _fetch("/api/personas")
    if not personas_data:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Could not reach the TALVEX backend. "
            "Please make sure the backend is running on port 8000."
        )
        return

    if not isinstance(personas_data, list) or len(personas_data) == 0:
        await update.message.reply_text(  # type: ignore[union-attr]
            "📭 No personas found. Create a career persona in the app first "
            "to get skill gap analysis."
        )
        return

    persona = personas_data[0]
    persona_id = persona.get("id", "")
    persona_name = _escape_md(str(persona.get("name", "Unknown")))

    data = await _fetch(f"/api/recommendations/skill-gap/{persona_id}")
    if not data:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Skill gap analysis failed. The LLM service may be unavailable "
            "or the OpenRouter API key may not be configured."
        )
        return

    if not isinstance(data, dict):
        data = {}

    gaps: list[dict] = data.get("gaps", [])
    current_skills: list[str] = data.get("currentSkills", [])

    if not gaps:
        skill_list = ", ".join(_escape_md(s) for s in current_skills[:10])
        await update.message.reply_text(  # type: ignore[union-attr]
            f"✅ Great news! No significant skill gaps found for "
            f"*{persona_name}*.\n\n"
            f"Current skills: {skill_list}",
            parse_mode="MarkdownV2",
        )
        return

    lines = [
        f"📈 *Skill Gap Analysis for {persona_name}*\n",
        f"Current skills: {_escape_md(str(len(current_skills)))} | "
        f"Gaps found: {_escape_md(str(len(gaps)))}\n",
        "*Top Priority Gaps:*\n",
    ]

    priority_emoji: dict[str, str] = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    for i, gap in enumerate(gaps[:5], 1):
        skill = _escape_md(str(gap.get("skill", "Unknown")))
        priority = _escape_md(str(gap.get("priority", "medium")))
        demand = int(gap.get("marketDemand", 50))
        weeks = int(gap.get("estimatedWeeks", 4))
        emoji = priority_emoji.get(str(gap.get("priority", "medium")), "📌")

        lines.append(
            f"{i}\\. {emoji} *{skill}* \\({priority}\\)\n"
            f"  Market demand: {_escape_md(str(demand))}% | "
            f"Est\\. {_escape_md(str(weeks))} weeks to learn"
        )

    if len(gaps) > 5:
        lines.append(f"\n\\.\\.\\.and {_escape_md(str(len(gaps) - 5))} more gaps\\.")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")  # type: ignore[union-attr]


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear chat history for the current user."""
    if not await _precheck(update, context):
        return

    chat_id = str(update.effective_chat.id)  # type: ignore[union-attr]

    if chat_history is not None:
        from database import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as db:
                deleted = await chat_history.clear_user_history(db, chat_id)
                await db.commit()
        except Exception as exc:
            logger.error("Failed to clear chat history: %s", exc)
            deleted = 0
        if deleted > 0:
            await update.message.reply_text(  # type: ignore[union-attr]
                f"🗑 Chat history cleared. Removed {deleted} messages."
            )
        else:
            await update.message.reply_text(  # type: ignore[union-attr]
                "📭 Your chat history is already empty."
            )
    else:
        await update.message.reply_text(  # type: ignore[union-attr]
            "⚠️ Chat history service is unavailable — nothing to clear."
        )


# ---------------------------------------------------------------------------
# Natural language message handler
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle non-command text messages by routing through the agent service.

    Flow:
      1. Security + rate-limit check
      2. Record user message in chat history
      3. Classify intent
      4. If specialist intent → send processing indicator
      5. Route and execute via agent
      6. Record assistant response in chat history
      7. Send reply
    """
    if not await _precheck(update, context):
        return

    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    chat_id = str(update.effective_chat.id)

    # 1. Record user message
    await _record_user_message(chat_id, user_text)

    # 2. Check if agent service is available
    if route_and_execute is None or classify_intent is None:
        await update.message.reply_text(
            "⚠️ The AI agent service is currently unavailable. "
            "Please try again later or use the command buttons."
        )
        return

    # 3. Classify intent
    detected_intent: str | None = None
    confidence: float | None = None
    model_used: str | None = None

    try:
        classification = classify_intent(user_text)
        if isinstance(classification, dict):
            detected_intent = classification.get("intent")
            confidence = classification.get("confidence")
        elif isinstance(classification, str):
            detected_intent = classification

        logger.info(
            "Intent classified for chat_id=%s: intent=%s confidence=%s",
            chat_id, detected_intent, confidence,
        )
    except Exception:
        logger.exception("Intent classification failed for chat_id=%s", chat_id)

    # 4. Send processing indicator for specialist intents
    is_specialist = detected_intent in _SPECIALIST_INTENTS
    processing_msg = None
    if is_specialist:
        try:
            processing_msg = await update.message.reply_text(
                "⏳ Processing your request..."
            )
        except Exception:
            processing_msg = None

    # 5. Route and execute
    history_context = await _get_history_context(chat_id, limit=20)

    try:
        result = await route_and_execute(user_text, chat_id, history_context)
    except Exception as exc:
        logger.exception(
            "route_and_execute failed for chat_id=%s: %s", chat_id, exc
        )
        await update.message.reply_text(
            "⚠️ Something went wrong while processing your request. "
            "Please try again or rephrase your message."
        )
        return

    # 6. Extract response from result
    response_text: str = ""
    if isinstance(result, dict):
        response_text = result.get("response", "")
        if not response_text:
            response_text = result.get("message", "")
        if not response_text:
            response_text = result.get("text", "")
        # Extract metadata for chat history
        if detected_intent is None:
            detected_intent = result.get("intent")
        if confidence is None:
            confidence = result.get("confidence")
        model_used = result.get("model_used")

        # Check for error
        error = result.get("error")
        if error:
            response_text = f"⚠️ {error}"
    elif isinstance(result, str):
        response_text = result
    else:
        response_text = "⚠️ The agent returned an unexpected response format."

    if not response_text:
        response_text = (
            "I'm sorry, I couldn't generate a response. "
            "Could you rephrase your request?"
        )

    # 7. Record assistant response
    await _record_assistant_message(
        chat_id,
        response_text,
        intent=detected_intent,
        confidence=confidence,
        model_used=model_used,
    )

    # 8. Delete processing indicator and send final response
    if processing_msg is not None:
        try:
            await processing_msg.delete()
        except Exception:
            pass

    # Truncate extremely long responses (Telegram limit is 4096 characters)
    if len(response_text) > 4000:
        response_text = response_text[:3900] + "\n\n... (truncated)"

    try:
        await update.message.reply_text(
            response_text, parse_mode="MarkdownV2",
        )
    except Exception:
        # Fallback to plain text if MarkdownV2 parsing fails
        try:
            await update.message.reply_text(response_text)
        except Exception as exc:
            logger.error("Failed to send response: %s", exc)


# ---------------------------------------------------------------------------
# Callback query handler (inline button presses)
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    if not await _precheck(update, context):
        return

    if not update.callback_query:
        return

    query = update.callback_query
    callback_data = query.data

    await query.answer()  # Acknowledge the callback

    response_map: dict[str, str] = {
        "cb_ats_score": "📊 Paste your resume and job description to get an ATS score.",
        "cb_resume_build": "📄 Describe your target role and I'll help build your resume.",
        "cb_job_search": "🔍 What kind of role are you looking for?",
        "cb_help": (
            "❓ TALVEX Bot Commands\n\n"
            "🚀 /start — Welcome message and feature overview\n"
            "📊 /status — Application pipeline summary\n"
            "📋 /recent — Last 5 applications\n"
            "🔍 /search <query> — Search jobs\n"
            "📈 /recommend — Skill gap analysis\n"
            "🗑 /clear — Clear chat history\n"
            "❓ /help — Show this help message"
        ),
    }

    response_text = response_map.get(callback_data, "Unknown button.")

    try:
        await query.edit_message_text(
            response_text,
            parse_mode="MarkdownV2",
        )
    except Exception:
        try:
            await query.edit_message_text(response_text)
        except Exception:
            # If editing fails (message too old, etc.), send a new message
            await query.message.reply_text(response_text)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Global error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify the user — never crash."""
    logger.error(
        "Bot error: %s",
        context.error,
        exc_info=context.error if context.error else None,
    )

    if update is None:
        return

    # Try to notify the user
    try:
        if hasattr(update, "message") and update.message is not None:
            await update.message.reply_text(  # type: ignore[union-attr]
                "⛔ An unexpected error occurred. "
                "Please try again later or check the backend status."
            )
        elif (
            hasattr(update, "callback_query")
            and update.callback_query is not None
        ):
            await update.callback_query.answer(  # type: ignore[union-attr]
                "⛔ An unexpected error occurred."
            )
    except Exception:
        pass  # Never let error handler errors propagate


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Build and start the Telegram bot using long-polling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "Cannot start bot: TELEGRAM_BOT_TOKEN is not set. "
            "Bot will remain idle."
        )
        # Idle forever instead of exiting — lets the process stay alive
        # for container orchestration that expects it.
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    logger.info("Starting TALVEX Telegram Bot (Talvex_ATS_bot)...")
    logger.info("Backend URL: %s", BACKEND_URL)
    logger.info("Allowed user IDs: %s", ALLOWED_IDS if ALLOWED_IDS else "(none)")
    logger.info("Rate limit: %.1fs per user", _RATE_LIMIT)
    logger.info("Agent service: %s", "available" if route_and_execute else "unavailable")
    logger.info("Chat history service: %s", "available" if chat_history else "unavailable")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers (order matters — more specific first)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("recommend", cmd_recommend))
    app.add_handler(CommandHandler("clear", cmd_clear))

    # Register callback query handler (for inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Register natural language message handler (must be LAST — it catches all text)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Global error handler — catches all unhandled exceptions
    app.add_error_handler(error_handler)

    logger.info("TALVEX Telegram Bot is ready. Polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
