"""
TALVEX Prompt Management System

Centralizes all LLM system prompts into versioned `.md` files under
`backend/prompts/`.  Provides a single ``load_prompt()`` entry-point that:

1. Reads the corresponding ``.md`` template from disk.
2. Injects dynamic variables via ``str.format(**kwargs)``.
3. Raises ``PromptNotFoundException`` when the template is missing.

WHY THIS EXISTS:
--------------
Raw, inline prompt strings scattered across agent.py, llm_service.py,
resume_optimizer.py, and recommendations.py are an architectural liability:

* Prompts are duplicated across files.
* There is no single source of truth for what the LLM is told to do.
* Tweaking a prompt requires editing Python code, not configuration.
* There is no audit trail — you cannot diff prompt changes.

By extracting prompts into dedicated ``.md`` files we gain:

* Separation of "brain" (prompt logic) from "nervous system" (Python code).
* Version-controlled prompt history via git diff.
* Easy A/B testing by swapping template files.
* The ability for non-developers to review and edit prompts.

USAGE:
------
    from services.prompt_manager import load_prompt

    system_prompt = load_prompt("intent_classifier")
    system_prompt = load_prompt("resume_optimizer", stage_guidance="Focus on impact.")

PROMPT REGISTRY:
---------------
The ``PROMPT_REGISTRY`` maps template names to their filenames and metadata.
Add new prompts here when creating new ``.md`` files.

Each prompt template may contain ``{placeholder}`` tokens for dynamic injection
via ``str.format()``.  If a template has placeholders but the caller does not
supply them, a ``KeyError`` will be raised — this is intentional, as it catches
missing data at call time rather than producing malformed prompts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt directory — relative to this file
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# ---------------------------------------------------------------------------
# Prompt registry — maps template_name -> {filename, description, placeholders, json_mode}
# ---------------------------------------------------------------------------

PROMPT_REGISTRY: dict[str, dict[str, Any]] = {
    # === Agent.py prompts ===
    "intent_classifier": {
        "filename": "intent_classifier.md",
        "description": "Classifies user messages into intents (chat, ats_score, etc.)",
        "placeholders": [],  # No dynamic variables
        "json_mode": True,   # Expects JSON response
    },
    "casual_chat": {
        "filename": "casual_chat.md",
        "description": "Conversational chat handler for the SEARCHER model",
        "placeholders": [],
        "json_mode": False,  # Plain text response
    },
    "ats_scorer": {
        "filename": "ats_scorer.md",
        "description": "ATS resume scoring and analysis expert",
        "placeholders": [],
        "json_mode": False,  # Structured text, not JSON
    },
    "resume_builder": {
        "filename": "resume_builder.md",
        "description": "Resume content generator for pre-built HTML templates",
        "placeholders": [],
        "json_mode": False,  # Structured text sections
    },
    "job_search_clarifier": {
        "filename": "job_search_clarifier.md",
        "description": "Asks user for job search criteria",
        "placeholders": [],
        "json_mode": False,
    },
    "clarification": {
        "filename": "clarification.md",
        "description": "Handles ambiguous user messages",
        "placeholders": [],
        "json_mode": False,
    },

    "email_classifier": {
        "filename": "email_classifier.md",
        "description": "Classifies job application emails (rejection, interview, etc.)",
        "placeholders": [],
        "json_mode": True,
    },
    "jd_analyzer": {
        "filename": "jd_analyzer.md",
        "description": "Extracts structured data from job descriptions",
        "placeholders": [],
        "json_mode": True,
    },
    "follow_up_email": {
        "filename": "follow_up_email.md",
        "description": "Professional follow-up email writer",
        "placeholders": [],
        "json_mode": False,  # Plain text email body
    },
    "interview_prep": {
        "filename": "interview_prep.md",
        "description": "Generates interview questions and preparation tips",
        "placeholders": [],
        "json_mode": True,
    },
    "resume_improver": {
        "filename": "resume_improver.md",
        "description": "Suggests resume improvements based on JD gaps",
        "placeholders": [],
        "json_mode": True,
    },

    # === Resume Optimizer prompts ===
    "resume_optimizer": {
        "filename": "resume_optimizer.md",
        "description": "Rewrites resume bullets for ATS optimization",
        "placeholders": ["stage_guidance", "missing_skills", "missing_keywords", "generic_phrases"],
        "json_mode": True,
    },
    "optimized_cover_letter": {
        "filename": "optimized_cover_letter.md",
        "description": "Strategic cover letter with skill gap bridging",
        "placeholders": [],
        "json_mode": True,
    },

    # === Recommendations prompts ===
    "skill_gap_analyzer": {
        "filename": "skill_gap_analyzer.md",
        "description": "Analyzes skill gaps for career growth",
        "placeholders": [],
        "json_mode": True,
    },
    "trade_recommender": {
        "filename": "trade_recommender.md",
        "description": "Suggests career role transitions",
        "placeholders": [],
        "json_mode": True,
    },

    # === Resume Generator prompts ===
    "resume_parser": {
        "filename": "resume_parser.md",
        "description": "Parses raw resume text into structured JSON",
        "placeholders": [],
        "json_mode": True,
    },
}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class PromptNotFoundException(Exception):
    """Raised when a requested prompt template does not exist on disk."""

    def __init__(self, template_name: str, filepath: Path) -> None:
        self.template_name = template_name
        self.filepath = filepath
        super().__init__(
            f"Prompt template '{template_name}' not found at '{filepath}'. "
            f"Available templates: {sorted(PROMPT_REGISTRY.keys())}"
        )


class PromptFormatError(Exception):
    """Raised when dynamic variable injection fails (missing kwargs)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_prompt(template_name: str, **kwargs: str) -> str:
    """
    Load a system prompt template by name and inject dynamic variables.

    Parameters
    ----------
    template_name : str
        The registered name of the prompt template (e.g., ``"intent_classifier"``).
    **kwargs : str
        Dynamic values to inject into the template's ``{placeholder}`` tokens.

    Returns
    -------
    str
        The fully rendered prompt text, ready to use as a system message.

    Raises
    ------
    PromptNotFoundException
        If the template name is not registered or the ``.md`` file does not exist.
    PromptFormatError
        If a required placeholder is missing from ``**kwargs``.
    """
    # Validate template name
    if template_name not in PROMPT_REGISTRY:
        available = sorted(PROMPT_REGISTRY.keys())
        raise PromptNotFoundException(
            template_name,
            _PROMPTS_DIR / f"{template_name}.md",
        )

    registry_entry = PROMPT_REGISTRY[template_name]
    filename = registry_entry["filename"]
    filepath = _PROMPTS_DIR / filename

    # Check file exists
    if not filepath.exists():
        logger.error(
            "Prompt template file missing: '%s' (registered for '%s')",
            filepath, template_name,
        )
        raise PromptNotFoundException(template_name, filepath)

    # Read template
    try:
        raw_text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptNotFoundException(template_name, filepath) from exc

    # Inject dynamic variables
    if kwargs:
        try:
            rendered = raw_text.format(**kwargs)
        except KeyError as exc:
            missing_key = exc.args[0] if exc.args else "unknown"
            raise PromptFormatError(
                f"Prompt '{template_name}' requires placeholder "
                f"'{{{missing_key}}}' but it was not provided. "
                f"Required placeholders: {registry_entry.get('placeholders', [])}"
            ) from exc
    else:
        rendered = raw_text

    logger.debug(
        "Loaded prompt template '%s' from '%s' (%d chars, %d placeholders injected).",
        template_name, filename, len(rendered), len(kwargs),
    )

    return rendered


def get_prompt_metadata(template_name: str) -> dict[str, Any]:
    """
    Return metadata for a registered prompt without loading the template.

    Useful for debugging and admin endpoints.
    """
    if template_name not in PROMPT_REGISTRY:
        raise PromptNotFoundException(template_name, _PROMPTS_DIR / f"{template_name}.md")
    return dict(PROMPT_REGISTRY[template_name])


def list_prompts() -> dict[str, dict[str, Any]]:
    """Return all registered prompt templates and their metadata."""
    return {name: dict(meta) for name, meta in PROMPT_REGISTRY.items()}
