"""
TALVEX Agent Orchestrator

Central nervous system for the TALVEX ATS Assistant — a Telegram career
command center.  Provides:

1. **Intent Detection** — Classifies inbound user messages into one of
   several intents (chat, ats_score, resume_build, job_search, pdf_parse,
   research, status, help) using the lightweight SEARCHER model on OpenRouter.

2. **Route & Execute** — Dispatches classified messages to the appropriate
   specialist agent or handles them directly as conversational chat.

3. **Job Application Pipeline** — Multi-step workflow: PII scrub → JD parse
   → match score → skill gap → (optional) resume optimize → HTML generate
   → PII rehydrate → result assembly.

4. **Job Search & Match** — Tavily job search → per-listing scoring →
   rank & filter → result assembly.

Both pipelines run to full completion (no streaming).  Each node catches
exceptions and stores them in ``State["errors"]`` so the pipeline can
continue even when individual steps fail.

Graceful fallback: works even when the OpenRouter key is not set — LLM-
dependent nodes degrade gracefully with error messages instead of crashing
the entire pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime
from typing import Any, Literal, TypedDict

logger = logging.getLogger(__name__)

# ===================================================================
# Prompt Management System — centralized prompt templates
# NO INLINE FALLBACKS. If a template is missing, the request MUST fail loudly.
# ===================================================================

from services.prompt_manager import load_prompt


def _get_system_prompt(template_name: str, **kwargs: str) -> str:
    """Load a system prompt from the prompt manager. No fallback — fail loudly.

    Raises PromptNotFoundException if the template is missing.
    All errors are logged with full traceback for diagnostics.
    """
    try:
        return load_prompt(template_name, **kwargs)
    except Exception as exc:
        logger.error(
            "[PROMPT] Failed to load prompt '%s': %s\n%s",
            template_name, exc, traceback.format_exc(),
        )
        raise


# ===================================================================
# Intent constants
# ===================================================================

INTENT_CHAT = "chat"
INTENT_ATS_SCORE = "ats_score"
INTENT_RESUME_BUILD = "resume_build"
INTENT_JOB_SEARCH = "job_search"
INTENT_PDF_PARSE = "pdf_parse"
INTENT_STATUS = "status"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"

VALID_INTENTS = [
    INTENT_CHAT,
    INTENT_ATS_SCORE,
    INTENT_RESUME_BUILD,
    INTENT_JOB_SEARCH,
    INTENT_PDF_PARSE,
    INTENT_STATUS,
    INTENT_HELP,
]

INTENT_DESCRIPTIONS = {
    INTENT_CHAT: (
        "Casual conversation, greetings, general questions "
        "\u2014 handled directly by the router model"
    ),
    INTENT_ATS_SCORE: (
        "ATS resume scoring, keyword matching, improvement "
        "suggestions, job alignment analysis"
    ),
    INTENT_RESUME_BUILD: (
        "Resume content generation, filling pre-built templates, "
        "formatting sections, bullet point writing"
    ),
    INTENT_JOB_SEARCH: (
        "Job matching, recommendation filtering, application "
        "guidance, salary research"
    ),
    INTENT_PDF_PARSE: (
        "PDF/DOCX text extraction, resume data structuring, "
        "section identification"
    ),
    INTENT_STATUS: "Application pipeline summary, statistics",
    INTENT_HELP: "Show available commands and features",
}

CONFIDENCE_THRESHOLD = 0.75

# ===================================================================
# Lazy imports of existing TALVEX services
# ===================================================================

try:
    from services.pii_sanitizer import sanitize_pii, restore_pii
    _PII_AVAILABLE = True
except ImportError:
    _PII_AVAILABLE = False

try:
    from services.matcher import (
        calculate_match_score_enhanced,
        analyze_skill_gap,
        extract_skills_from_text,
    )
    _MATCHER_AVAILABLE = True
except ImportError:
    _MATCHER_AVAILABLE = False

try:
    from services.resume_optimizer import resume_optimizer
    _OPTIMIZER_AVAILABLE = True
except ImportError:
    _OPTIMIZER_AVAILABLE = False

try:
    from services.resume_generator import ResumeGenerator
    resume_generator = ResumeGenerator()
    _GENERATOR_AVAILABLE = True
except ImportError:
    _GENERATOR_AVAILABLE = False
    resume_generator = None

try:
    from services.tavily_client import tavily
    _TAVILY_AVAILABLE = True
except ImportError:
    _TAVILY_AVAILABLE = False

try:
    from services.jsearch_client import search_jobs as jsearch_search
    _JSEARCH_AVAILABLE = True
except ImportError:
    _JSEARCH_AVAILABLE = False

try:
    from services.openrouter_client import openrouter_client
    _OPENROUTER_AVAILABLE = True
except ImportError:
    _OPENROUTER_AVAILABLE = False

try:
    from templates.template_registry import (
        get_template as _get_template_html,
        list_templates as _list_templates,
        validate_template as _validate_template,
        TEMPLATE_REGISTRY as _TEMPLATE_REGISTRY,
    )
    _TEMPLATE_REGISTRY_AVAILABLE = True
except ImportError:
    _TEMPLATE_REGISTRY_AVAILABLE = False

try:
    from langgraph.graph import END, StateGraph
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    logger.warning(
        "LangGraph not importable — pipelines will use sequential async fallback."
    )

try:
    from services.usage_logger import log_api_call
    _USAGE_LOGGER_AVAILABLE = True
except ImportError:
    _USAGE_LOGGER_AVAILABLE = False


# ===================================================================
# State definitions
# ===================================================================

class ApplicationPipelineState(TypedDict, total=False):
    """State for the Job Application Pipeline workflow."""
    # Inputs
    raw_jd: str
    raw_resume: str
    career_stage: str  # "entry_level" | "mid_level" | "senior" | "executive"
    template_type: str  # "chronological" | "functional" | "combination" | "targeted"

    # Intermediate
    scrubbed_resume: str
    pii_mapping: dict[str, str]
    parsed_jd: dict[str, Any]
    match_score: dict[str, Any]
    skill_gaps: list[dict[str, Any]]
    optimized_resume: dict[str, Any]
    generated_html: str
    final_resume: str

    # Output
    result: dict[str, Any]
    errors: list[str]

    # Metadata
    pipeline_id: str
    started_at: str
    completed_at: str


class JobSearchState(TypedDict, total=False):
    """State for the Job Search & Match workflow."""
    # Inputs
    query: str
    location: str
    user_skills: list[str]

    # Intermediate
    job_listings: list[dict[str, Any]]
    scored_jobs: list[dict[str, Any]]
    top_jobs: list[dict[str, Any]]

    # Output
    result: dict[str, Any]
    errors: list[str]

    # Metadata
    pipeline_id: str
    started_at: str
    completed_at: str


# ===================================================================
# Timeout tiers (seconds)
# ===================================================================

TIMEOUT_LLM_GENERATION = 180.0   # Resume builder / optimizer (3 minutes)
TIMEOUT_LLM_CLASSIFY   = 30.0    # Intent classification
TIMEOUT_LLM_CHAT       = 60.0    # Conversational responses
TIMEOUT_EXTERNAL_API   = 45.0    # Tavily / external services


# ===================================================================
# Helper: safely call services
# ===================================================================

def _safe_call(caption: str, fn, *args, **kwargs) -> Any:
    """Call *fn* and return (result, error_string | None)."""
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:
        msg = f"[{caption}] {type(exc).__name__}: {exc}"
        logger.exception(msg)
        return None, msg


async def _safe_call_async(
    caption: str,
    fn,
    *args,
    timeout: float | None = None,
    **kwargs,
) -> tuple[Any, str | None]:
    """Call an async *fn* with an optional timeout and return (result, error_string | None).

    If *timeout* is provided and the call exceeds it, an ``asyncio.TimeoutError``
    is caught and returned as an error string instead of propagating.  This prevents
    a hung LLM API call from blocking the entire pipeline indefinitely.
    """
    try:
        if timeout is not None:
            result = await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
        else:
            result = await fn(*args, **kwargs)
        return result, None
    except asyncio.TimeoutError:
        msg = f"[{caption}] Timeout after {timeout:.0f}s"
        logger.error(msg)
        return None, msg
    except Exception as exc:
        msg = f"[{caption}] {type(exc).__name__}: {exc}"
        logger.exception(msg)
        return None, msg


# ===================================================================
# Intent detection
# ===================================================================

async def classify_intent(
    message: str,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Classify a user message into an intent using the SEARCHER model.

    Parameters
    ----------
    message : str
        The user's message text.
    chat_history : list[dict], optional
        Recent conversation history for additional context.
        Each dict has ``"role"`` and ``"content"`` keys.

    Returns
    -------
    dict with keys:
        - ``intent`` (str): One of the ``INTENT_*`` constants.
        - ``confidence`` (float): 0.0 – 1.0 confidence score.
        - ``reasoning`` (str): One-sentence explanation.
    """
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        logger.warning("OpenRouter not available — falling back to INTENT_UNKNOWN.")
        return {
            "intent": INTENT_UNKNOWN,
            "confidence": 0.0,
            "reasoning": "OpenRouter client is not configured or API key is missing.",
        }

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _get_system_prompt("intent_classifier")},
    ]

    # Append recent chat history for context (last 6 turns max)
    if chat_history:
        recent = chat_history[-6:]
        for turn in recent:
            if isinstance(turn, dict) and "role" in turn and "content" in turn:
                messages.append({
                    "role": turn["role"],
                    "content": turn["content"],
                })

    messages.append({"role": "user", "content": message})

    try:
        raw_response = await _safe_call_async(
            "Intent Classifier",
            openrouter_client.call,
            model_role="searcher",
            messages=messages,
            temperature=0.1,
            max_tokens=150,
            json_mode=True,  # Intent classifier MUST return JSON
            timeout=TIMEOUT_LLM_CLASSIFY,
        )
        response_text, err = raw_response
        if err:
            logger.error("Intent classification failed: %s", err)
            return {
                "intent": INTENT_UNKNOWN,
                "confidence": 0.0,
                "reasoning": f"LLM call failed: {err}",
            }
    except Exception as exc:
        logger.error("Intent classification error: %s", exc)
        return {
            "intent": INTENT_UNKNOWN,
            "confidence": 0.0,
            "reasoning": f"Unexpected error: {exc}",
        }

    # Parse the JSON response — tolerate markdown fences or extraneous text
    cleaned = response_text.strip()
    # Strip code fences if present
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]  # remove opening fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]  # remove closing fence
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(
            "Intent classifier returned invalid JSON: %s", response_text[:200]
        )
        return {
            "intent": INTENT_UNKNOWN,
            "confidence": 0.0,
            "reasoning": "Classifier returned invalid JSON.",
        }

    intent = parsed.get("intent", INTENT_UNKNOWN)
    confidence = float(parsed.get("confidence", 0.0))
    reasoning = str(parsed.get("reasoning", ""))

    # Validate intent value
    if intent not in VALID_INTENTS:
        logger.warning("Classifier returned unknown intent '%s' — falling back.", intent)
        intent = INTENT_UNKNOWN

    # Clamp confidence
    confidence = max(0.0, min(1.0, confidence))

    # Low confidence fallback
    if confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            "Intent '%s' below confidence threshold (%.2f < %.2f) — "
            "falling back to INTENT_UNKNOWN.",
            intent, confidence, CONFIDENCE_THRESHOLD,
        )
        intent = INTENT_UNKNOWN

    logger.info(
        "Intent classified: %s (confidence=%.2f, reasoning=%s)",
        intent, confidence, reasoning,
    )
    return {"intent": intent, "confidence": confidence, "reasoning": reasoning}


# ===================================================================
# Agent execution functions — one per intent
# ===================================================================

async def _handle_chat(
    message: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    """Handle casual conversation directly via the SEARCHER model."""
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        return (
            "I'm the TALVEX ATS Assistant, but my conversational model "
            "isn't available right now.  Please make sure the OPENROUTER_API_KEY "
            "is configured.  In the meantime, try /help to see what I can do."
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _get_system_prompt("casual_chat")},
    ]

    if chat_history:
        recent = chat_history[-10:]
        for turn in recent:
            if isinstance(turn, dict) and "role" in turn and "content" in turn:
                messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": message})

    response_text, err = await _safe_call_async(
        "Chat Handler",
        openrouter_client.call,
        model_role="searcher",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
        timeout=TIMEOUT_LLM_CHAT,
    )
    if err:
        if _USAGE_LOGGER_AVAILABLE:
            log_api_call(service="openrouter", endpoint="chat", status="error", error_message=str(err))
        return f"Sorry, I had trouble responding: {err}"

    if _USAGE_LOGGER_AVAILABLE:
        log_api_call(service="openrouter", endpoint="chat", status="success")

    return response_text


async def _handle_ats_score(
    message: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Handle ATS scoring intent.

    If a raw JD and resume are provided in *context*, runs the full
    application pipeline.  Otherwise, asks the user for the required inputs
    via the ARCHITECT model.
    """
    ctx = context or {}

    # If both JD and resume are in context, run the full pipeline
    raw_jd = ctx.get("raw_jd", "")
    raw_resume = ctx.get("raw_resume", "")
    career_stage = ctx.get("career_stage", "mid_level")
    template_type = ctx.get("template_type", "chronological")

    if raw_jd and raw_resume:
        logger.info("Running full application pipeline for ATS scoring.")
        result = await run_application_pipeline(
            raw_jd=raw_jd,
            raw_resume=raw_resume,
            career_stage=career_stage,
            template_type=template_type,
        )
        return _format_pipeline_result(result, "ATS Score Analysis")

    # Otherwise, ask the user for inputs using the ARCHITECT model
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        return (
            "To run an ATS score analysis, I need:\n\n"
            "1. Your resume (paste text or upload a file)\n"
            "2. A job description (paste text or share a URL)\n\n"
            "Please share both and I'll analyze your match."
        )

    messages = [
        {"role": "system", "content": _get_system_prompt("ats_scorer")},
        {"role": "user", "content": message},
    ]
    response_text, err = await _safe_call_async(
        "ATS Score Handler",
        openrouter_client.call,
        model_role="architect",
        messages=messages,
        temperature=0.5,
        max_tokens=2000,
        timeout=TIMEOUT_LLM_GENERATION,
    )
    if err:
        if _USAGE_LOGGER_AVAILABLE:
            log_api_call(service="openrouter", endpoint="ats_score", status="error", error_message=str(err))
        return (
            "I'd love to score your resume! To do a full ATS analysis, "
            "please share:\n\n"
            "1. Your resume (text or file)\n"
            "2. The job description you're targeting\n\n"
            "Then I can give you a detailed ATS match report."
        )

    if _USAGE_LOGGER_AVAILABLE:
        log_api_call(service="openrouter", endpoint="ats_score", status="success")

    return response_text


async def _handle_resume_build(
    message: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Handle resume build intent.

    Uses the BUILDER model to generate structured content that fills
    pre-built templates from the template registry.  Does NOT generate
    HTML/CSS from scratch — the templates are pre-built.
    """
    ctx = context or {}

    # If resume text and JD are in context, generate the full resume
    raw_resume = ctx.get("raw_resume", "")
    raw_jd = ctx.get("raw_jd", "")
    template_type = ctx.get("template_type", "chronological")
    career_stage = ctx.get("career_stage", "mid_level")

    if raw_resume:
        logger.info("Generating resume with template_type=%s.", template_type)

        # Build a detailed prompt with template context
        template_sections = []
        if _TEMPLATE_REGISTRY_AVAILABLE and template_type in _TEMPLATE_REGISTRY:
            meta = _TEMPLATE_REGISTRY[template_type]
            template_sections = meta.get("section_order", [])

        builder_prompt = (
            f"Generate structured resume content for the '{template_type}' "
            f"template.\n\n"
            f"Template section order: {', '.join(template_sections) or 'standard'}\n"
            f"Career stage: {career_stage}\n\n"
        )
        if raw_jd:
            builder_prompt += (
                f"Target Job Description:\n---\n{raw_jd}\n---\n\n"
            )
        builder_prompt += (
            f"Source Resume Content:\n---\n{raw_resume}\n---\n\n"
            "Generate improved, ATS-optimized content for each section. "
            "Write achievement-oriented bullet points. Output structured "
            "content only — the HTML template will be applied separately."
        )

        if _OPENROUTER_AVAILABLE and openrouter_client.is_openrouter_active:
            messages = [
                {"role": "system", "content": _get_system_prompt("resume_builder")},
                {"role": "user", "content": builder_prompt},
            ]
            response_text, err = await _safe_call_async(
                "Resume Builder",
                openrouter_client.call,
                model_role="builder",
                messages=messages,
                temperature=0.6,
                max_tokens=3000,
                timeout=TIMEOUT_LLM_GENERATION,
            )
            if err:
                return f"Resume build failed: {err}"
            return response_text

        # Fallback: run the existing pipeline if no OpenRouter for builder
        result = await run_application_pipeline(
            raw_jd=raw_jd or "No job description provided.",
            raw_resume=raw_resume,
            career_stage=career_stage,
            template_type=template_type,
        )
        return _format_pipeline_result(result, "Resume Build")

    # No resume provided — ask the user
    available_templates = []
    if _TEMPLATE_REGISTRY_AVAILABLE:
        available_templates = _list_templates()
        template_names = ", ".join(
            f"{t['name']} ({t['type']})" for t in available_templates
        )
    else:
        template_names = "chronological, functional, combination, targeted"

    return (
        "I can build your resume using professional templates.  Here's what "
        "I need:\n\n"
        "1. Your current resume or career details (paste text or upload)\n"
        "2. Target job description (optional, for keyword optimization)\n"
        "3. Preferred template type:\n\n"
        f"   {template_names}\n\n"
        "Share your details and I'll generate a polished, ATS-optimized "
        "resume."
    )


async def _handle_job_search(
    message: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Handle job search intent.

    If a query is available in *context*, runs the search pipeline.
    Otherwise, asks the user for their search criteria.
    """
    ctx = context or {}
    query = ctx.get("query", "")
    location = ctx.get("location", "")
    user_skills = ctx.get("user_skills", [])

    if query:
        logger.info("Running job search pipeline: query='%s', location='%s'.", query, location)
        result = await run_search_pipeline(
            query=query,
            location=location,
            user_skills=user_skills,
        )
        if _USAGE_LOGGER_AVAILABLE:
            search_errors = result.get("errors", [])
            status = "error" if search_errors else "success"
            log_api_call(service="jsearch", endpoint="search", status=status)
        return _format_search_result(result)

    # No query in context — try the SEARCHER model to extract intent details
    if _OPENROUTER_AVAILABLE and openrouter_client.is_openrouter_active:
        messages = [
            {
                "role": "system",
                "content": _get_system_prompt("job_search_clarifier"),
            },
            {"role": "user", "content": message},
        ]
        response_text, err = await _safe_call_async(
            "Job Search Handler",
            openrouter_client.call,
            model_role="searcher",
            messages=messages,
            temperature=0.5,
            max_tokens=500,
            timeout=TIMEOUT_LLM_CHAT,
        )
        if err:
            return _fallback_job_search_prompt()
        return response_text

    return _fallback_job_search_prompt()


async def _handle_pdf_parse(
    message: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Handle PDF/DOCX parse intent.

    If parsed text is already in *context*, formats it.  Otherwise,
    instructs the user to upload a file.
    """
    ctx = context or {}
    parsed_text = ctx.get("parsed_text", "")

    if parsed_text:
        return (
            "I've extracted the following content from your document:\n\n"
            f"---\n{parsed_text[:2000]}\n---\n\n"
            "What would you like to do with this? I can:\n"
            "• Run an ATS score analysis\n"
            "• Build an optimized resume\n"
            "• Search for matching jobs\n\n"
            "Just let me know!"
        )

    return (
        "To parse a resume, please upload a PDF or DOCX file.  I'll "
        "extract the text, structure it into sections (experience, skills, "
        "education), and then you can run an ATS score or build an "
        "optimized resume from it."
    )


async def _handle_status() -> str:
    """Return a status summary of available services."""
    services = [
        ("PII Sanitizer", _PII_AVAILABLE),
        ("Matcher (ATS Scoring)", _MATCHER_AVAILABLE),
        ("Resume Optimizer", _OPTIMIZER_AVAILABLE),
        ("Resume Generator", _GENERATOR_AVAILABLE),
        ("JSearch Premium", _JSEARCH_AVAILABLE),
        ("Tavily Job Search", _TAVILY_AVAILABLE),
        ("OpenRouter LLM", _OPENROUTER_AVAILABLE),
        ("Template Registry", _TEMPLATE_REGISTRY_AVAILABLE),
    ]

    status_lines = [
        "TALVEX ATS Assistant — Service Status\n",
    ]
    for name, available in services:
        icon = "✅" if available else "❌"
        status_lines.append(f"{icon} {name}")

    if _OPENROUTER_AVAILABLE and openrouter_client.is_openrouter_active:
        models = openrouter_client.models
        if models:
            status_lines.append("\nModel Configuration:")
            for role, model_id in models.items():
                status_lines.append(f"  • {role}: {model_id}")
    else:
        status_lines.append("\nOpenRouter not configured — LLM features unavailable.")

    return "\n".join(status_lines)


def _handle_help() -> str:
    """Return the help text listing all available commands and features."""
    help_text = (
        "TALVEX ATS Assistant — Commands & Features\n\n"
        "Just type naturally! I'll figure out what you need. "
        "Here are some examples:\n\n"
        "📋 **ATS Score Analysis**\n"
        "   \"Score my resume against this JD\"\n"
        "   \"How does my resume match this job?\"\n\n"
        "📝 **Resume Builder**\n"
        "   \"Build me a resume for a software engineer role\"\n"
        "   \"Rewrite my resume for this job posting\"\n\n"
        "🔍 **Job Search**\n"
        "   \"Find Python developer jobs in New York\"\n"
        "   \"Search for remote data analyst positions\"\n\n"
        "📄 **PDF/Resume Parsing**\n"
        "   Upload a PDF or DOCX file to get started\n\n"
        "📈 **Status**\n"
        "   \"Show system status\"\n\n"
        "💡 **Pro Tips**\n"
        "• Upload a resume file to parse it automatically\n"
        "• Share a job description URL or paste the text\n"
        "• Combine requests: \"Score my resume and find matching jobs\"\n\n"
        "Type anything to get started!"
    )
    return help_text


async def _handle_clarification(message: str) -> str:
    """
    Handle low-confidence intent by asking the user to clarify,
    using the SEARCHER model for a natural response.
    """
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        return (
            "I'm not sure exactly what you need. Could you be more specific? "
            "For example:\n\n"
            "• \"Score my resume\" — ATS analysis\n"
            "• \"Build a resume\" — Resume builder\n"
            "• \"Find jobs\" — Job search\n"
            "• \"/help\" — See all commands"
        )

    messages = [
        {
            "role": "system",
            "content": _get_system_prompt("clarification"),
        },
        {"role": "user", "content": message},
    ]

    response_text, err = await _safe_call_async(
        "Clarification Handler",
        openrouter_client.call,
        model_role="searcher",
        messages=messages,
        temperature=0.5,
        max_tokens=300,
        timeout=TIMEOUT_LLM_CHAT,
    )
    if err:
        return (
            "I'm not quite sure what you're looking for. Could you try "
            "rephrasing? Type /help to see what I can do."
        )

    return response_text


# ===================================================================
# Response formatters
# ===================================================================

def _format_pipeline_result(result: dict[str, Any], title: str) -> str:
    """Format an application pipeline result into a readable response."""
    if not result:
        return "Pipeline completed but returned no results."

    errors = result.get("errors", [])
    success = result.get("success", False)

    lines = [f"**{title}**\n"]

    if success:
        score = result.get("match_score", 0)
        lines.append(f"Match Score: {score}/100")

        optimization = result.get("optimization", {})
        method = optimization.get("method", "none")
        before = optimization.get("before_ats", 0)
        after = optimization.get("after_ats", 0)
        if method != "none":
            lines.append(
                f"\nOptimization ({method}): ATS {before} → {after}"
            )

        gaps = result.get("skill_gaps", [])
        if gaps:
            lines.append(f"\nTop {min(len(gaps), 5)} Skill Gaps:")
            for gap in gaps[:5]:
                gap_name = gap.get("skill", gap.get("name", "Unknown"))
                importance = gap.get("importance", "")
                lines.append(f"  • {gap_name} {importance}")

        added = optimization.get("added_keywords", [])
        if added:
            lines.append(f"\nKeywords Added: {', '.join(added[:10])}")

        has_html = bool(result.get("resume_html", ""))
        if has_html:
            lines.append("\nYour optimized resume HTML has been generated.")

    else:
        lines.append("Pipeline completed with errors.")

    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for err in errors[:5]:
            lines.append(f"  ⚠ {err}")

    return "\n".join(lines)


def _format_search_result(result: dict[str, Any]) -> str:
    """Format a search pipeline result into a readable response."""
    if not result:
        return "Search completed but returned no results."

    errors = result.get("errors", [])
    success = result.get("success", False)
    total_searched = result.get("total_searched", 0)
    returned = result.get("returned", 0)
    top_jobs = result.get("top_jobs", [])

    lines = ["**Job Search Results**\n"]

    if success and top_jobs:
        lines.append(
            f"Found {total_searched} listings, {returned} matched your profile:\n"
        )
        for i, job in enumerate(top_jobs[:5], 1):
            title = job.get("title", "Unknown Position")
            company = job.get("company", "Unknown Company")
            score = job.get("match_score", 0)
            url = job.get("url", "")

            job_line = f"{i}. **{title}** @ {company} (Match: {score}%)"
            if url:
                job_line += f"\n   {url}"
            lines.append(job_line)

        if returned > 5:
            lines.append(f"\n... and {returned - 5} more matches.")
    elif success:
        lines.append(
            f"Searched {total_searched} jobs but none matched your profile. "
            "Try broadening your search criteria or skills list."
        )
    else:
        lines.append("Search encountered errors.")

    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for err in errors[:3]:
            lines.append(f"  ⚠ {err}")

    return "\n".join(lines)


def _fallback_job_search_prompt() -> str:
    """Return a prompt asking the user for job search details."""
    return (
        "I can search for jobs matching your skills.  Tell me:\n\n"
        "1. **Job title or keywords** (e.g. \"Python developer\", \"data analyst\")\n"
        "2. **Location** (optional — city, state, or \"remote\")\n"
        "3. **Your key skills** (for match scoring)\n\n"
        "Example: \"Find me Python developer jobs in Austin, TX. "
        "Skills: Python, Django, PostgreSQL, Docker\""
    )


# ===================================================================
# Route and execute
# ===================================================================

async def route_and_execute(
    message: str,
    chat_id: str | int | None = None,
    chat_history: list[dict[str, str]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify the user's intent and dispatch to the appropriate handler.

    Parameters
    ----------
    message : str
        The user's message text.
    chat_id : str | int, optional
        Telegram chat ID for logging/tracking.
    chat_history : list[dict], optional
        Recent conversation history for context.
    context : dict, optional
        Additional context (resume text, JD, parsed file, etc.).

    Returns
    -------
    dict with keys:
        - ``response`` (str): The reply text to send to the user.
        - ``intent`` (str): The classified intent.
        - ``confidence`` (float): Intent classification confidence.
        - ``model_used`` (str): Which model/agent handled the request.
    """
    ctx = context or {}
    log_prefix = f"[Chat {chat_id}] " if chat_id else ""

    # --- Step 1: Classify intent ---
    classification = await classify_intent(message, chat_history)
    intent = classification["intent"]
    confidence = classification["confidence"]

    logger.info(
        "%sRouted message (intent=%s, confidence=%.2f): %.100s",
        log_prefix, intent, confidence, message,
    )

    # --- Step 2: Dispatch based on intent ---
    response = ""
    model_used = "none"

    if intent == INTENT_CHAT and confidence >= CONFIDENCE_THRESHOLD:
        response = await _handle_chat(message, chat_history)
        model_used = "searcher"

    elif intent == INTENT_ATS_SCORE:
        response = await _handle_ats_score(message, ctx)
        model_used = "architect"

    elif intent == INTENT_RESUME_BUILD:
        response = await _handle_resume_build(message, ctx)
        model_used = "builder"

    elif intent == INTENT_JOB_SEARCH:
        response = await _handle_job_search(message, ctx)
        model_used = "searcher + jsearch/tavily"

    elif intent == INTENT_PDF_PARSE:
        response = await _handle_pdf_parse(message, ctx)
        model_used = "parser"

    elif intent == INTENT_STATUS:
        response = await _handle_status()
        model_used = "system"

    elif intent == INTENT_HELP:
        response = _handle_help()
        model_used = "system"

    else:
        # Low confidence or INTENT_UNKNOWN — ask for clarification
        response = await _handle_clarification(message)
        model_used = "searcher"
        # Reset intent to unknown for clarity
        intent = INTENT_UNKNOWN
        confidence = classification["confidence"]

    return {
        "response": response,
        "intent": intent,
        "confidence": confidence,
        "model_used": model_used,
    }


# ===================================================================
# Job Application Pipeline — node functions
# ===================================================================

def _pii_scrub(state: ApplicationPipelineState) -> dict:
    """Node: Scrub PII from the raw resume."""
    errors: list[str] = list(state.get("errors", []))

    if not _PII_AVAILABLE:
        errors.append("[PII Scrub] pii_sanitizer not available — skipping.")
        return {
            "scrubbed_resume": state.get("raw_resume", ""),
            "pii_mapping": {},
            "errors": errors,
        }

    raw = state.get("raw_resume", "")
    result, err = _safe_call("PII Scrub", sanitize_pii, raw)
    if err:
        errors.append(err)
        return {"scrubbed_resume": raw, "pii_mapping": {}, "errors": errors}

    scrubbed_text, pii_mapping = result
    return {"scrubbed_resume": scrubbed_text, "pii_mapping": pii_mapping, "errors": errors}


def _jd_parse(state: ApplicationPipelineState) -> dict:
    """Node: Parse job description into structured data."""
    errors: list[str] = list(state.get("errors", []))
    jd = state.get("raw_jd", "")

    parsed: dict[str, Any] = {
        "skills_required": [],
        "requirements": [],
        "perks": [],
        "title": "",
        "company": "",
    }

    if not jd:
        errors.append("[JD Parse] Empty job description.")
        return {"parsed_jd": parsed, "errors": errors}

    # Extract skills from JD text using matcher
    if _MATCHER_AVAILABLE:
        skills, err = _safe_call("JD Parse", extract_skills_from_text, jd)
        if err:
            errors.append(err)
        else:
            parsed["skills_required"] = skills

    # Try LLM-based parsing for deeper extraction (graceful fallback)
    if _OPENROUTER_AVAILABLE and openrouter_client.is_openrouter_active:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop — skip LLM parse
            errors.append("[JD Parse] No event loop available for LLM parse — using heuristic extraction only.")
        else:
            # We can't easily call async code from a sync LangGraph node,
            # so we'll schedule it in a future and just mark it.
            # For the pipeline we keep heuristic extraction as primary.
            pass

    parsed["raw_length"] = len(jd)
    return {"parsed_jd": parsed, "errors": errors}


def _match_score(state: ApplicationPipelineState) -> dict:
    """Node: Calculate match score between resume and JD."""
    errors: list[str] = list(state.get("errors", []))
    scrubbed = state.get("scrubbed_resume", "")
    jd = state.get("raw_jd", "")

    if not scrubbed or not jd:
        errors.append("[Match Score] Empty resume or JD — skipping.")
        return {"match_score": {"overallScore": 0}, "errors": errors}

    if _MATCHER_AVAILABLE:
        score, err = _safe_call("Match Score", calculate_match_score_enhanced, scrubbed, jd)
        if err:
            errors.append(err)
            return {"match_score": {"overallScore": 0}, "errors": errors}
        return {"match_score": score, "errors": errors}

    errors.append("[Match Score] matcher service not available.")
    return {"match_score": {"overallScore": 0}, "errors": errors}


def _skill_gap(state: ApplicationPipelineState) -> dict:
    """Node: Analyze skill gaps."""
    errors: list[str] = list(state.get("errors", []))
    scrubbed = state.get("scrubbed_resume", "")
    parsed_jd = state.get("parsed_jd", {})
    jd_skills = parsed_jd.get("skills_required", [])

    if not _MATCHER_AVAILABLE:
        errors.append("[Skill Gap] matcher service not available.")
        return {"skill_gaps": [], "errors": errors}

    # Extract resume skills
    resume_skills, err = _safe_call("Skill Gap (resume)", extract_skills_from_text, scrubbed)
    if err:
        errors.append(err)
        resume_skills = []

    # Analyze gaps against JD skills (or full market)
    gaps, err = _safe_call(
        "Skill Gap (analysis)",
        analyze_skill_gap,
        resume_skills,
        jd_skills if jd_skills else None,
    )
    if err:
        errors.append(err)
        return {"skill_gaps": [], "errors": errors}

    # Return top 20 most important gaps
    return {"skill_gaps": gaps[:20], "errors": errors}


def _resume_optimize(state: ApplicationPipelineState) -> dict:
    """Node: Optimize the resume for the JD (async-friendly)."""
    # This node stores a marker; the actual async work is handled in the
    # pipeline runner which can await the optimizer.
    return {}


async def _resume_optimize_async(state: ApplicationPipelineState) -> dict:
    """Async version of resume optimization — used by the async runner."""
    errors: list[str] = list(state.get("errors", []))
    scrubbed = state.get("scrubbed_resume", "")
    jd = state.get("raw_jd", "")
    career_stage = state.get("career_stage", "mid_level")

    if not _OPTIMIZER_AVAILABLE:
        errors.append("[Resume Optimize] resume_optimizer not available — skipping optimization.")
        return {"optimized_resume": {"optimized_text": scrubbed, "optimization_method": "none"}, "errors": errors}

    result, err = await _safe_call_async(
        "Resume Optimize",
        resume_optimizer.optimize_resume,
        resume_text=scrubbed,
        job_description=jd,
        career_stage=career_stage,
        timeout=TIMEOUT_LLM_GENERATION,
    )
    if err:
        errors.append(err)
        return {"optimized_resume": {"optimized_text": scrubbed, "optimization_method": "none"}, "errors": errors}

    return {"optimized_resume": result, "errors": errors}


async def _resume_generate_async(state: ApplicationPipelineState) -> dict:
    """Async: Generate styled HTML resume."""
    errors: list[str] = list(state.get("errors", []))
    optimized = state.get("optimized_resume", {})
    text_to_use = optimized.get("optimized_text", "") or state.get("scrubbed_resume", "")
    jd = state.get("raw_jd", "")
    template = state.get("template_type", "chronological")

    if not _GENERATOR_AVAILABLE or resume_generator is None:
        errors.append("[Resume Generate] resume_generator not available.")
        return {"generated_html": "", "errors": errors}

    result, err = await _safe_call_async(
        "Resume Generate",
        resume_generator.generate,
        resume_text=text_to_use,
        job_description=jd,
        template_type=template,
        timeout=TIMEOUT_LLM_GENERATION,
    )
    if err:
        errors.append(err)
        return {"generated_html": "", "errors": errors}

    html = getattr(result, "html", "") or ""
    return {"generated_html": html, "errors": errors}


def _pii_rehydrate(state: ApplicationPipelineState) -> dict:
    """Node: Rehydrate PII into the generated HTML."""
    errors: list[str] = list(state.get("errors", []))
    html = state.get("generated_html", "")
    pii_mapping = state.get("pii_mapping", {})

    if not html:
        errors.append("[PII Rehydrate] No generated HTML to rehydrate.")
        return {"final_resume": html, "errors": errors}

    if not _PII_AVAILABLE or not pii_mapping:
        return {"final_resume": html, "errors": errors}

    final, err = _safe_call("PII Rehydrate", restore_pii, html, pii_mapping)
    if err:
        errors.append(err)
        return {"final_resume": html, "errors": errors}

    return {"final_resume": final, "errors": errors}


def _build_application_result(state: ApplicationPipelineState) -> dict:
    """Node: Assemble the final result dict."""
    match = state.get("match_score", {})
    gaps = state.get("skill_gaps", [])
    optimized = state.get("optimized_resume", {})
    errors = state.get("errors", [])

    overall_score = match.get("overallScore", 0) if isinstance(match, dict) else 0

    result: dict[str, Any] = {
        "pipeline": "job_application",
        "match_score": overall_score,
        "match_details": match if isinstance(match, dict) else {},
        "skill_gaps": gaps,
        "optimization": {
            "method": optimized.get("optimization_method", "none") if isinstance(optimized, dict) else "none",
            "before_ats": optimized.get("before_ats_score", 0) if isinstance(optimized, dict) else 0,
            "after_ats": optimized.get("after_ats_score", 0) if isinstance(optimized, dict) else 0,
            "added_keywords": optimized.get("added_keywords", []) if isinstance(optimized, dict) else [],
            "removed_generic_phrases": optimized.get("removed_generic_phrases", []) if isinstance(optimized, dict) else [],
        },
        "resume_html": state.get("final_resume", ""),
        "errors": errors,
        "success": len(errors) == 0,
    }

    return {
        "result": result,
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }


# Conditional edge: skip optimization if match_score >= 70
def _should_optimize(state: ApplicationPipelineState) -> Literal["resume_optimize", "resume_generate"]:
    match = state.get("match_score", {})
    score = match.get("overallScore", 0) if isinstance(match, dict) else 0
    if score >= 70:
        logger.info("Match score %d >= 70 — skipping optimization.", score)
        return "resume_generate"
    return "resume_optimize"


# ===================================================================
# LangGraph Pipeline Builders
# ===================================================================

def _build_application_graph():
    """Build and compile the application pipeline as a LangGraph StateGraph.

    Uses mixed sync/async nodes.  When invoked via ``.ainvoke()` LangGraph
    runs sync nodes in a threadpool and async nodes natively.
    Includes a conditional edge that skips resume optimization when
    the match score is already >= 70.
    """
    if not _LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(ApplicationPipelineState)

    graph.add_node("pii_scrub", _pii_scrub)
    graph.add_node("jd_parse", _jd_parse)
    graph.add_node("match_score", _match_score)
    graph.add_node("skill_gap", _skill_gap)
    graph.add_node("resume_optimize", _resume_optimize_async)
    graph.add_node("resume_generate", _resume_generate_async)
    graph.add_node("pii_rehydrate", _pii_rehydrate)
    graph.add_node("result_assembly", _build_application_result)

    graph.set_entry_point("pii_scrub")
    graph.add_edge("pii_scrub", "jd_parse")
    graph.add_edge("jd_parse", "match_score")
    graph.add_edge("match_score", "skill_gap")
    graph.add_conditional_edges(
        "skill_gap",
        _should_optimize,
        {"resume_optimize": "resume_optimize", "resume_generate": "resume_generate"},
    )
    graph.add_edge("resume_optimize", "resume_generate")
    graph.add_edge("resume_generate", "pii_rehydrate")
    graph.add_edge("pii_rehydrate", "result_assembly")
    graph.add_edge("result_assembly", END)

    compiled = graph.compile()
    logger.info("Application pipeline compiled via LangGraph StateGraph.")
    return compiled


def _build_search_graph():
    """Build and compile the search pipeline as a LangGraph StateGraph.
    """
    if not _LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(JobSearchState)

    graph.add_node("web_search", _web_search)
    graph.add_node("score_each_job", _score_each_job)
    graph.add_node("rank_and_filter", _rank_and_filter)
    graph.add_node("result_assembly", _build_search_result)

    graph.set_entry_point("web_search")
    graph.add_edge("web_search", "score_each_job")
    graph.add_edge("score_each_job", "rank_and_filter")
    graph.add_edge("rank_and_filter", "result_assembly")
    graph.add_edge("result_assembly", END)

    compiled = graph.compile()
    logger.info("Search pipeline compiled via LangGraph StateGraph.")
    return compiled


# Module-level compiled graph singletons (lazy-initialized)
_application_graph = None
_search_graph = None


def _get_application_graph():
    global _application_graph
    if _application_graph is None:
        _application_graph = _build_application_graph()
    return _application_graph


def _get_search_graph():
    global _search_graph
    if _search_graph is None:
        _search_graph = _build_search_graph()
    return _search_graph


# ===================================================================
# Job Search & Match — node functions
# ===================================================================

async def _web_search(state: JobSearchState) -> dict:
    """Node: Search for jobs using priority routing.
    
    Priority routing strategy:
      1. Platform-specific search (user says "Search LinkedIn") → Tavily with site: prefix
      2. Generic job search (user says "Find me AI jobs") → JSearch first (rich metadata), Tavily fallback
      3. URL paste → Jina Reader (existing behavior, handled upstream)
    
    JSearch returns structured data: salary, experience level, benefits.
    Tavily returns web results: better for platform-specific dorking.
    """
    errors: list[str] = list(state.get("errors", []))
    query = state.get("query", "")
    location = state.get("location", "")

    if not query:
        errors.append("[Web Search] Empty query — skipping.")
        return {"job_listings": [], "errors": errors}

    all_listings: list[dict[str, Any]] = []

    # ── Tier 1: Check if user wants platform-specific search ──
    _PLATFORM_KEYWORDS = {
        "linkedin": "site:linkedin.com",
        "indeed": "site:indeed.com",
        "naukri": "site:naukri.com",
        "glassdoor": "site:glassdoor.com",
        "wellfound": "site:wellfound.com",
        "angel": "site:wellfound.com",
    }
    
    query_lower = query.lower()
    platform_filter = None
    for platform, site_prefix in _PLATFORM_KEYWORDS.items():
        if platform in query_lower:
            platform_filter = site_prefix
            # Strip the platform name from the query for cleaner search
            query_clean = query_lower.replace(platform, "").strip()
            if not query_clean:
                query_clean = query  # fallback if stripping left nothing
            break

    if platform_filter and _TAVILY_AVAILABLE:
        # Platform-specific: Use Tavily (which uses Google under the hood)
        # JSearch CANNOT do Google Dorking — it's a structured DB API
        logger.info(
            "[Web Search] Platform-specific search: %s via Tavily (dorking)",
            platform_filter,
        )
        
        tavily_results, err = await _safe_call_async(
            "Tavily Platform Search",
            tavily.search_jobs,
            job_title=query_clean,
            location=location,
            max_results=15,
            timeout=TIMEOUT_EXTERNAL_API,
        )
        if err:
            errors.append(f"[Tavily] {err}")
        elif tavily_results:
            all_listings.extend(tavily_results)
    
    # ── Tier 2: Generic search → JSearch (premium) with Tavily fallback ──
    if not platform_filter:
        # Try JSearch first for rich metadata (salary, experience, benefits)
        if _JSEARCH_AVAILABLE:
            logger.info("[Web Search] Using JSearch (premium) for: '%s'", query)
            
            # Determine country from location
            country = "us"  # default
            if location:
                loc_lower = location.lower()
                if any(c in loc_lower for c in ["india", "indian", "naukri", "bangalore", "mumbai", "hyderabad", "chennai", "delhi"]):
                    country = "in"
                elif any(c in loc_lower for c in ["uk", "london", "manchester", "britain"]):
                    country = "gb"
                elif any(c in loc_lower for c in ["germany", "berlin", "munich"]):
                    country = "de"
                elif any(c in loc_lower for c in ["canada", "toronto", "vancouver"]):
                    country = "ca"
                elif "remote" in loc_lower:
                    country = "us"  # JSearch remote defaults to US
            
            jsearch_results, err = await _safe_call_async(
                "JSearch Premium",
                jsearch_search,
                query=query,
                country=country,
                num_pages=1,
                date_posted="month",
                timeout=TIMEOUT_EXTERNAL_API,
            )
            if err:
                errors.append(f"[JSearch] {err}")
                logger.warning("[Web Search] JSearch failed, falling back to Tavily: %s", err)
            elif jsearch_results:
                raw_jobs = jsearch_results.get("results", [])
                # Normalize JSearch results to match our internal schema
                for job in raw_jobs:
                    normalized = {
                        "title": job.get("jobTitle", ""),
                        "company": job.get("employerName", ""),
                        "location": _format_jsearch_location(job),
                        "url": job.get("jobApplyLink", ""),
                        "description": job.get("jobDescription", "")[:500],
                        "source_platform": "jsearch",
                        "posted_date": job.get("jobPostedAtDatetimeUTC", ""),
                        # JSearch exclusive metadata
                        "salary_min": job.get("jobMinSalary"),
                        "salary_max": job.get("jobMaxSalary"),
                        "salary_currency": job.get("jobSalaryCurrency", "USD"),
                        "employment_type": job.get("jobEmploymentType", ""),
                        "is_remote": job.get("jobIsRemote", False),
                        "qualifications": job.get("jobQualifications", ""),
                    }
                    all_listings.append(normalized)
                
                logger.info("[Web Search] JSearch returned %d results.", len(raw_jobs))
        
        # Tavily fallback if JSearch returned nothing or isn't available
        if not all_listings and _TAVILY_AVAILABLE:
            logger.info("[Web Search] Falling back to Tavily for: '%s'", query)
            tavily_results, err = await _safe_call_async(
                "Tavily Fallback",
                tavily.search_jobs,
                job_title=query,
                location=location,
                max_results=15,
                timeout=TIMEOUT_EXTERNAL_API,
            )
            if err:
                errors.append(f"[Tavily] {err}")
            elif tavily_results:
                all_listings.extend(tavily_results)

    return {"job_listings": all_listings, "errors": errors}


def _format_jsearch_location(job: dict) -> str:
    """Format JSearch location fields into a single string."""
    parts = []
    for field in ["jobCity", "jobState", "jobCountry"]:
        val = job.get(field, "")
        if val and val not in parts:
            parts.append(val)
    if job.get("jobIsRemote"):
        parts.append("Remote")
    return ", ".join(parts) if parts else "Not specified"


def _score_each_job(state: JobSearchState) -> dict:
    """Node: Score each job listing against the user's skills."""
    errors: list[str] = list(state.get("errors", []))
    listings = state.get("job_listings", [])
    user_skills = state.get("user_skills", [])

    if not _MATCHER_AVAILABLE or not listings:
        return {"scored_jobs": listings, "errors": errors}

    scored: list[dict[str, Any]] = []
    for job in listings:
        description = job.get("description", "") or ""
        title = job.get("title", "") or ""

        # Use matcher to score
        jd_text = f"{title}\n{description}"
        if not jd_text.strip():
            scored.append({**job, "match_score": 0})
            continue

        match_result, err = _safe_call(
            "Score Job",
            calculate_match_score_enhanced,
            " ".join(user_skills),  # treat user skills as "resume"
            jd_text,
        )
        if err:
            errors.append(err)
            scored.append({**job, "match_score": 0})
            continue

        score = match_result.get("overallScore", 0) if isinstance(match_result, dict) else 0
        scored.append({
            **job,
            "match_score": score,
            "match_details": match_result,
        })

    return {"scored_jobs": scored, "errors": errors}


def _rank_and_filter(state: JobSearchState) -> dict:
    """Node: Rank jobs by score and return top results."""
    scored = state.get("scored_jobs", [])

    # Sort by match_score descending
    ranked = sorted(scored, key=lambda j: j.get("match_score", 0), reverse=True)

    # Filter: only jobs with score >= 20
    filtered = [j for j in ranked if j.get("match_score", 0) >= 20]

    # Take top 10
    top = filtered[:10]

    return {"top_jobs": top}


def _build_search_result(state: JobSearchState) -> dict:
    """Node: Assemble final search result."""
    top = state.get("top_jobs", [])
    errors = state.get("errors", [])

    result: dict[str, Any] = {
        "pipeline": "job_search",
        "total_searched": len(state.get("job_listings", [])),
        "total_scored": len(state.get("scored_jobs", [])),
        "returned": len(top),
        "top_jobs": top,
        "errors": errors,
        "success": len(errors) == 0,
    }

    return {
        "result": result,
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }


# ===================================================================
# Pipeline runners
# ===================================================================

async def run_application_pipeline(
    raw_jd: str,
    raw_resume: str,
    career_stage: str = "mid_level",
    template_type: str = "chronological",
) -> dict[str, Any]:
    """
    Run the full Job Application Pipeline asynchronously.

    Tries LangGraph StateGraph first (if available).  Falls back to
    manual sequential orchestration for environments where LangGraph
    is not installed.

    Parameters
    ----------
    raw_jd : str
        Raw job description text or URL content.
    raw_resume : str
        Raw resume text.
    career_stage : str
        "entry_level", "mid_level", "senior", or "executive".
    template_type : str
        Resume template to use.

    Returns
    -------
    dict with keys: success, match_score, skill_gaps, optimization,
    resume_html, errors.
    """
    pipeline_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow().isoformat() + "Z"
    logger.info("[Pipeline %s] Starting Job Application Pipeline.", pipeline_id)

    initial_state: ApplicationPipelineState = {
        "raw_jd": raw_jd,
        "raw_resume": raw_resume,
        "career_stage": career_stage,
        "template_type": template_type,
        "pipeline_id": pipeline_id,
        "started_at": started_at,
        "errors": [],
    }

    # Try LangGraph first
    graph = _get_application_graph()
    if graph is not None:
        logger.info("[Pipeline %s] Running via LangGraph StateGraph.", pipeline_id)
        try:
            final_state = await graph.ainvoke(initial_state)
            return final_state.get("result", {})
        except Exception as exc:
            logger.error(
                "[Pipeline %s] LangGraph failed: %s — falling back to sequential.",
                pipeline_id, exc,
            )

    # Sequential fallback
    logger.info("[Pipeline %s] Running sequentially.", pipeline_id)
    state = dict(initial_state)  # copy
    state.update(_pii_scrub(state))
    state.update(_jd_parse(state))
    state.update(_match_score(state))
    score_val = state.get("match_score", {})
    overall = score_val.get("overallScore", 0) if isinstance(score_val, dict) else 0
    state.update(_skill_gap(state))

    if overall < 70:
        logger.info("[Pipeline %s] Score %d < 70 — optimizing.", pipeline_id, overall)
        state.update(await _resume_optimize_async(state))
    else:
        logger.info("[Pipeline %s] Score %d >= 70 — skipping optimization.", pipeline_id, overall)
        state["optimized_resume"] = {
            "optimized_text": state.get("scrubbed_resume", ""),
            "optimization_method": "none",
        }

    state.update(await _resume_generate_async(state))
    state.update(_pii_rehydrate(state))
    state.update(_build_application_result(state))

    logger.info(
        "[Pipeline %s] Sequential pipeline complete. Errors: %d.",
        pipeline_id, len(state.get("errors", [])),
    )
    return state.get("result", {})


async def run_search_pipeline(
    query: str,
    location: str = "",
    user_skills: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the Job Search & Match pipeline asynchronously.

    Tries LangGraph StateGraph first (if available).  Falls back to
    manual sequential orchestration.

    Parameters
    ----------
    query : str
        Job search query (e.g. "Python Developer").
    location : str
        Geographic location filter.
    user_skills : list[str], optional
        User's skill set for scoring.

    Returns
    -------
    dict with keys: success, total_searched, returned, top_jobs, errors.
    """
    pipeline_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow().isoformat() + "Z"
    logger.info("[Pipeline %s] Starting Job Search Pipeline.", pipeline_id)

    initial_state: JobSearchState = {
        "query": query,
        "location": location,
        "user_skills": user_skills or [],
        "pipeline_id": pipeline_id,
        "started_at": started_at,
        "errors": [],
    }

    # Try LangGraph first
    graph = _get_search_graph()
    if graph is not None:
        logger.info("[Pipeline %s] Running via LangGraph StateGraph.", pipeline_id)
        try:
            final_state = await graph.ainvoke(initial_state)
            return final_state.get("result", {})
        except Exception as exc:
            logger.error(
                "[Pipeline %s] LangGraph failed: %s — falling back to sequential.",
                pipeline_id, exc,
            )

    # Sequential fallback
    logger.info("[Pipeline %s] Running sequentially.", pipeline_id)
    state = dict(initial_state)
    state.update(await _web_search(state))
    logger.info("[Pipeline %s] Web search — %d listings.", pipeline_id, len(state.get("job_listings", [])))
    state.update(_score_each_job(state))
    state.update(_rank_and_filter(state))
    state.update(_build_search_result(state))
    logger.info(
        "[Pipeline %s] Sequential search complete. Errors: %d.",
        pipeline_id, len(state.get("errors", [])),
    )
    return state.get("result", {})


# ===================================================================
# Convenience dispatcher
# ===================================================================

async def run_pipeline(
    pipeline_type: str,
    **kwargs,
) -> dict[str, Any]:
    """
    Dispatch to the correct pipeline based on *pipeline_type*.

    Parameters
    ----------
    pipeline_type : str
        "job_application" or "job_search".
    **kwargs
        Pipeline-specific arguments.

    Returns
    -------
    dict — the pipeline result.
    """
    if pipeline_type == "job_application":
        return await run_application_pipeline(
            raw_jd=kwargs.get("raw_jd", ""),
            raw_resume=kwargs.get("raw_resume", ""),
            career_stage=kwargs.get("career_stage", "mid_level"),
            template_type=kwargs.get("template_type", "chronological"),
        )
    elif pipeline_type == "job_search":
        return await run_search_pipeline(
            query=kwargs.get("query", ""),
            location=kwargs.get("location", ""),
            user_skills=kwargs.get("user_skills", []),
        )
    else:
        return {
            "pipeline": pipeline_type,
            "success": False,
            "errors": [f"Unknown pipeline type: {pipeline_type}. Use 'job_application' or 'job_search'."],
        }


# ===================================================================
# Module initialisation
# ===================================================================

logger.info(
    "TALVEX agent initialised — intent detection + pipeline runners ready. "
    "PII=%s, Matcher=%s, Optimizer=%s, Generator=%s, JSearch=%s, Tavily=%s, "
    "OpenRouter=%s, Templates=%s",
    _PII_AVAILABLE, _MATCHER_AVAILABLE, _OPTIMIZER_AVAILABLE,
    _GENERATOR_AVAILABLE, _JSEARCH_AVAILABLE, _TAVILY_AVAILABLE, _OPENROUTER_AVAILABLE,
    _TEMPLATE_REGISTRY_AVAILABLE,
)
