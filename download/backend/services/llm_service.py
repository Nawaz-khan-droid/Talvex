"""
TALVEX LLM Service

Unified LLM service for classification, generation, and analysis tasks.
All LLM calls route through the centralized ``openrouter_client`` module
— NO local proxy, NO Node.js middleware. Every call is protected by:
  - 180-second timeout via ``asyncio.wait_for``
  - 429 rate-limit retry with exponential backoff (handled by openrouter_client)
  - PII sanitization before any text reaches the LLM (when pii_sanitizer is available)

Graceful degradation: every method has a heuristic fallback that works
WITHOUT the LLM, so the service never crashes even if OpenRouter is down.
"""

import asyncio
import json
import logging
import re
import traceback
from typing import Any

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
# Lazy import of centralized OpenRouter client
# ===================================================================

_OPENROUTER_AVAILABLE = False
openrouter_client = None

try:
    from services.openrouter_client import openrouter_client as _client
    openrouter_client = _client
    _OPENROUTER_AVAILABLE = True
except ImportError:
    logger.warning("openrouter_client not importable — LLM calls will use heuristic fallback.")


# ===================================================================
# Lazy import of PII sanitizer
# ===================================================================

_PII_AVAILABLE = False

try:
    from services.pii_sanitizer import PIISanitizer
    _pii_sanitizer = PIISanitizer()
    _PII_AVAILABLE = True
    logger.info("PII sanitizer loaded — LLM service will scrub PII before calls.")
except ImportError:
    _pii_sanitizer = None
    logger.warning("PII sanitizer not available — raw text will be sent to LLM.")


# ===================================================================
# Lazy import of usage logger
# ===================================================================

try:
    from services.usage_logger import log_api_call as _log_usage
    _USAGE_LOG_AVAILABLE = True
except ImportError:
    _USAGE_LOG_AVAILABLE = False


# ===================================================================
# LLM call helper with 180s timeout + graceful fallback
# ===================================================================

_LLM_TIMEOUT = 180.0  # 3 minutes — matches TIMEOUT_LLM_GENERATION in agent.py


async def _call_llm(
    messages: list[dict[str, str]],
    model_role: str = "parser",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: float = _LLM_TIMEOUT,
    json_mode: bool = False,
) -> str | None:
    """
    Call OpenRouter via the centralized client with 180s timeout.
    Returns the response text, or None on any failure.
    """
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        return None

    try:
        response = await asyncio.wait_for(
            openrouter_client.call(
                model_role=model_role,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            ),
            timeout=timeout,
        )
        return response
    except asyncio.TimeoutError:
        logger.error("LLM call timed out after %.0fs (role=%s).", timeout, model_role)
    except Exception as exc:
        logger.error("LLM call failed (role=%s): %s", model_role, exc)
    return None


def _sanitize(text: str) -> tuple[str, dict[str, str] | None]:
    """Scrub PII from text. Returns (sanitized_text, pii_mapping_or_None)."""
    if _PII_AVAILABLE and _pii_sanitizer is not None:
        return _pii_sanitizer.scrub(text)
    return text, None


def _restore(text: str, mapping: dict[str, str] | None) -> str:
    """Restore PII placeholders back to original values."""
    if _PII_AVAILABLE and _pii_sanitizer is not None and mapping:
        return _pii_sanitizer.rehydrate(text, mapping)
    return text


def _try_parse_json(text: str) -> Any | None:
    """Try to parse text as JSON, tolerating markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


# ===================================================================
# Email Classification Patterns (heuristic fallback)
# ===================================================================

REJECTION_PATTERNS = [
    r"\bregret\b", r"\bunfortunately\b", r"\bnot moving forward\b",
    r"\bdecided not to proceed\b", r"\bnot selected\b", r"\bwon't be proceeding\b",
    r"\bnot be moving forward\b", r"\bnot progress\b", r"\bposition has been filled\b",
    r"\bchosen not to move forward\b", r"\bdecided to go with\b",
    r"\bnot a fit\b", r"\bwent with another candidate\b",
    r"\bwe will not be\b", r"\bwill not be able to offer\b",
]

INTERVIEW_PATTERNS = [
    r"\binterview\b", r"\bnext round\b", r"\bcall with\b",
    r"\bvideo call\b", r"\bmeet with\b", r"\bschedule\b.*\bcall\b",
    r"\bwould like to speak\b", r"\bwould love to chat\b",
    r"\binvite you to\b.*\binterview\b", r"\bdiscuss.*next steps\b",
    r"\bconversation\b.*\brole\b",
]

ASSESSMENT_PATTERNS = [
    r"\bassessment\b", r"\bcoding challenge\b", r"\bcoding test\b",
    r"\bhackerrank\b", r"\bcodility\b", r"\bonline assessment\b",
    r"\btechnical test\b", r"\btake-home\b", r"\bcoding exercise\b",
    r"\btest link\b", r"\bassessment link\b", r"\bcomplete this\b.*\btest\b",
]

GENERAL_PATTERNS = [
    r"\backnowledge\b", r"\breceived your application\b",
    r"\bunder review\b", r"\bthank you for applying\b",
    r"\bthank you for your interest\b", r"\bapplication received\b",
    r"\bconfirming receipt\b", r"\byour application has been received\b",
    r"\bcurrently reviewing\b",
]


def _count_pattern_matches(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))


# ===================================================================
# LLM Service Class
# ===================================================================

class LLMService:
    """Service for LLM-powered analysis with heuristic fallback.

    All LLM calls go through ``openrouter_client`` — there is NO local
    proxy, NO Node.js middleware, NO ``httpx.post`` to localhost:3001.
    """

    def __init__(self) -> None:
        pass

    # ----------------------------------------------------------
    # 1. Email Classification
    # ----------------------------------------------------------

    async def analyze_email(self, email_body: str) -> dict[str, Any]:
        """Classify email as: rejection, interview, assessment, general, uncertain."""
        text = email_body.strip()
        if not text:
            return {"classification": "Uncertain", "confidence": 0.0, "reasoning": "Empty email body."}

        # Sanitize PII before LLM call
        sanitized, pii_map = _sanitize(text)

        messages = [
            {"role": "system", "content": _get_system_prompt("email_classifier")},
            {"role": "user", "content": f"Classify this email:\n\n{sanitized}"},
        ]

        raw = await _call_llm(messages, model_role="parser", temperature=0.1, max_tokens=200, json_mode=True)
        if raw:
            parsed = _try_parse_json(raw)
            if parsed and isinstance(parsed, dict) and "classification" in parsed:
                if _USAGE_LOG_AVAILABLE:
                    _log_usage(service="openrouter", endpoint="email_classification", status="success")
                return parsed

        # Heuristic fallback
        return self._heuristic_email_classification(text)

    def _heuristic_email_classification(self, text: str) -> dict[str, Any]:
        scores = {
            "Rejection": _count_pattern_matches(text, REJECTION_PATTERNS),
            "Interview": _count_pattern_matches(text, INTERVIEW_PATTERNS),
            "Assessment": _count_pattern_matches(text, ASSESSMENT_PATTERNS),
            "General": _count_pattern_matches(text, GENERAL_PATTERNS),
        }
        total = sum(scores.values())
        if total == 0:
            return {"classification": "Uncertain", "confidence": 0.3, "reasoning": "No definitive patterns detected."}

        best = max(scores, key=scores.get)
        confidence = round(min(0.95, 0.4 + scores[best] * 0.15), 2)
        reasoning_map = {
            "Rejection": "Detected rejection keywords (regret, unfortunately, not selected, etc.).",
            "Interview": "Detected interview scheduling language.",
            "Assessment": "Detected assessment/test references.",
            "General": "Detected acknowledgment language.",
        }
        return {"classification": best, "confidence": confidence, "reasoning": reasoning_map.get(best, "")}

    # ----------------------------------------------------------
    # 2. Job Description Analysis
    # ----------------------------------------------------------

    async def analyze_job_description(self, job_description: str) -> dict[str, Any]:
        """Extract structured data from JD. PII sanitized before LLM call."""
        sanitized_jd, _ = _sanitize(job_description)

        messages = [
            {"role": "system", "content": _get_system_prompt("jd_analyzer")},
            {"role": "user", "content": f"Analyze this job description:\n\n{sanitized_jd[:3000]}"},
        ]
        raw = await _call_llm(messages, model_role="parser", temperature=0.3, max_tokens=1000, json_mode=True)
        if raw:
            parsed = _try_parse_json(raw)
            if parsed and isinstance(parsed, dict):
                if _USAGE_LOG_AVAILABLE:
                    _log_usage(service="openrouter", endpoint="jd_analysis", status="success")
                return parsed

        # Heuristic fallback
        return self._heuristic_jd_analysis(job_description)

    def _heuristic_jd_analysis(self, job_description: str) -> dict[str, Any]:
        text = job_description.lower()
        common_skills = [
            "python", "java", "javascript", "typescript", "react", "angular", "vue",
            "node.js", "django", "flask", "spring", "docker", "kubernetes", "aws",
            "azure", "gcp", "sql", "mongodb", "postgres", "redis", "git",
            "ci/cd", "rest api", "graphql", "machine learning", "data analysis",
            "html", "css", "tailwind", "next.js", "go", "rust", "c++", "scala",
            "spark", "kafka", "elasticsearch", "linux", "terraform", "ansible",
        ]
        found_skills = [s for s in common_skills if s in text]

        exp_match = re.search(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)", text)
        experience_level = "Not Specified"
        if exp_match:
            years = int(exp_match.group(1))
            if years <= 2: experience_level = "Entry Level"
            elif years <= 5: experience_level = "Mid Level"
            elif years <= 10: experience_level = "Senior"
            else: experience_level = "Staff / Principal"

        for indicators, level in [
            (["senior", "lead", "principal", "staff", "architect"], "Senior"),
            (["mid-level", "mid level", "intermediate"], "Mid Level"),
            (["entry level", "junior", "fresher", "intern"], "Entry Level"),
        ]:
            if any(ind in text for ind in indicators):
                experience_level = level
                break

        if "remote" in text or "work from home" in text: work_mode = "Remote"
        elif "hybrid" in text: work_mode = "Hybrid"
        elif "on-site" in text or "onsite" in text: work_mode = "On-Site"
        else: work_mode = "Not Specified"

        perk_patterns = [
            (r"health insurance", "Health Insurance"), (r"dental", "Dental Coverage"),
            (r"401k|retirement plan|provident fund", "Retirement Plan"),
            (r"stock|equity|rsu|esop", "Equity/Stock Options"),
            (r"paid time off|pto|vacation", "Paid Time Off"),
            (r"bonus|incentive", "Performance Bonus"),
            (r"learning|education|tuition", "Learning & Development"),
            (r"flexible hours", "Flexible Hours"),
        ]
        perks = [label for pattern, label in perk_patterns if re.search(pattern, text)]

        return {"required_skills": found_skills, "experience_level": experience_level, "work_mode": work_mode, "perks": perks}

    # ----------------------------------------------------------
    # 3. Follow-Up Email Generation
    # ----------------------------------------------------------

    async def generate_follow_up(self, company: str, role: str, days_applied: int, followup_count: int) -> str:
        """Generate a professional follow-up email."""
        messages = [
            {"role": "system", "content": _get_system_prompt("follow_up_email")},
            {"role": "user", "content": (
                f"Company: {company}\nRole: {role}\n"
                f"Days since applied: {days_applied}\nFollow-up number: {followup_count}\n\n"
                "Write a follow-up email:"
            )},
        ]
        raw = await _call_llm(messages, model_role="parser", temperature=0.7, max_tokens=800)
        if raw and len(raw) > 50:
            if _USAGE_LOG_AVAILABLE:
                _log_usage(service="openrouter", endpoint="follow_up_email", status="success")
            return raw.strip()

        return self._heuristic_follow_up(company, role, days_applied, followup_count)

    def _heuristic_follow_up(self, company: str, role: str, days_applied: int, followup_count: int) -> str:
        templates = {
            1: (
                f"Subject: Following Up on {role} Application — {company}\n\n"
                f"Dear Hiring Team at {company},\n\n"
                f"I hope this message finds you well. I wanted to follow up on my application "
                f"for the {role} position that I submitted {days_applied} days ago.\n\n"
                f"I remain very interested in this opportunity and would welcome the chance "
                f"to discuss how my background and skills can contribute to your team.\n\n"
                f"Please let me know if there are any updates regarding my application.\n\n"
                f"Thank you for your time and consideration.\n\nBest regards"
            ),
            2: (
                f"Subject: Re: Following Up — {role} Position at {company}\n\n"
                f"Dear Hiring Team at {company},\n\n"
                f"I am writing to follow up once more regarding the {role} position. "
                f"It has been {days_applied} days since I submitted my application.\n\n"
                f"I understand the hiring process can take time, and I appreciate your "
                f"consideration.\n\n"
                f"Thank you again for your time.\n\nBest regards"
            ),
        }
        return templates.get(followup_count, templates[2])

    # ----------------------------------------------------------
    # 4. Interview Preparation
    # ----------------------------------------------------------

    async def generate_interview_prep(self, job_description: str, company: str, role: str) -> dict[str, Any]:
        """Generate interview preparation questions and tips. PII sanitized."""
        sanitized_jd, _ = _sanitize(job_description)

        messages = [
            {"role": "system", "content": _get_system_prompt("interview_prep")},
            {"role": "user", "content": (
                f"Company: {company}\nRole: {role}\n\n"
                f"Job Description:\n{sanitized_jd[:2000]}\n\n"
                "Generate interview prep:"
            )},
        ]
        raw = await _call_llm(messages, model_role="architect", temperature=0.5, max_tokens=2000, json_mode=True)
        if raw:
            parsed = _try_parse_json(raw)
            if parsed and isinstance(parsed, dict) and "questions" in parsed:
                if _USAGE_LOG_AVAILABLE:
                    _log_usage(service="openrouter", endpoint="interview_prep", status="success")
                return parsed

        return self._heuristic_interview_prep(job_description, company, role)

    def _heuristic_interview_prep(self, job_description: str, company: str, role: str) -> dict[str, Any]:
        questions = [
            {"question": f"Why do you want to work at {company}?", "category": "Behavioral",
             "tip": "Research the company's mission, recent news, and culture."},
            {"question": "Tell me about a time you overcame a significant challenge at work.", "category": "Behavioral",
             "tip": "Use the STAR method (Situation, Task, Action, Result)."},
            {"question": f"What unique value would you bring to the {role} team at {company}?", "category": "Role-Specific",
             "tip": "Connect your specific skills and experiences to the job requirements."},
        ]
        general_tips = [
            f"Research {company} thoroughly — their products, competitors, and recent news.",
            f"Prepare 2-3 thoughtful questions to ask about the {role} team.",
            "Practice your answers out loud to build confidence.",
            "Follow up within 24 hours with a thank-you email.",
        ]
        return {"questions": questions, "general_tips": general_tips}

    # ----------------------------------------------------------
    # 5. Resume Improvement Suggestions
    # ----------------------------------------------------------

    async def improve_resume_suggestions(self, resume_text: str, job_description: str) -> dict[str, Any]:
        """Suggest resume improvements. PII sanitized before LLM call."""
        sanitized_resume, _ = _sanitize(resume_text)
        sanitized_jd, _ = _sanitize(job_description)

        messages = [
            {"role": "system", "content": _get_system_prompt("resume_improver")},
            {"role": "user", "content": (
                f"Resume:\n{sanitized_resume[:2000]}\n\n"
                f"Job Description:\n{sanitized_jd[:2000]}\n\n"
                "Suggest improvements:"
            )},
        ]
        raw = await _call_llm(messages, model_role="architect", temperature=0.5, max_tokens=2000, json_mode=True)
        if raw:
            parsed = _try_parse_json(raw)
            if parsed and isinstance(parsed, dict):
                if _USAGE_LOG_AVAILABLE:
                    _log_usage(service="openrouter", endpoint="resume_improvement", status="success")
                return parsed

        return self._heuristic_resume_improvements(resume_text, job_description)

    def _heuristic_resume_improvements(self, resume_text: str, job_description: str) -> dict[str, Any]:
        resume_lower = resume_text.lower()
        jd_lower = job_description.lower()

        # Missing keywords
        jd_skills = re.findall(r"\b[a-z]+(?:\s[a-z]+)?\b", jd_lower)
        missing_keywords = [kw for kw in jd_skills if kw not in resume_lower and len(kw) > 3][:15]

        suggestions = []
        has_numbers = bool(re.search(r'\d+%|\$\d+|\d+\+?\s*(?:users|customers|clients|projects|team)', resume_text))
        if not has_numbers:
            suggestions.append("Add quantifiable metrics (e.g., 'Improved performance by 30%', 'Managed a team of 5').")

        action_verbs = ["led", "built", "designed", "implemented", "optimized", "developed"]
        if sum(1 for v in action_verbs if v in resume_lower) < 3:
            suggestions.append("Start bullet points with strong action verbs (Built, Led, Designed, Optimized).")

        word_count = len(resume_text.split())
        if word_count < 200:
            suggestions.append("Resume appears very short. Consider adding more detail.")
        elif word_count > 1200:
            suggestions.append("Resume is quite long. Consider trimming to 1-2 pages.")

        if "summary" not in resume_lower and "objective" not in resume_lower:
            suggestions.append("Add a Professional Summary at the top.")

        if missing_keywords:
            suggestions.append(f"Consider incorporating these JD keywords: {', '.join(missing_keywords[:8])}.")

        return {"keyword_gaps": missing_keywords, "suggestions": suggestions}


# Singleton instance
llm_service = LLMService()
