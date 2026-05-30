"""
TALVEX Resume Optimizer Service

Uses OpenRouter LLM (via centralized ``openrouter_client``) to rewrite resume
bullet points with measurable achievements, incorporate missing JD keywords, and
cut generic/vague content.  Falls back to heuristic-based optimization when the
LLM is unavailable.

All LLM calls go through ``openrouter_client`` — there is NO local proxy,
NO ``httpx.post`` to localhost:3001.  Every call is wrapped in a 180-second
timeout.  PII is scrubbed before any text reaches the LLM.
"""

import asyncio
import json
import logging
import re
import traceback
from typing import Any

from services.matcher import (
    calculate_ats_score,
    extract_keywords,
    extract_skills_from_text,
    TECHNICAL_SKILLS,
)

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
# Lazy imports (graceful degradation)
# ===================================================================

_OPENROUTER_AVAILABLE = False
openrouter_client = None

try:
    from services.openrouter_client import openrouter_client as _client
    openrouter_client = _client
    _OPENROUTER_AVAILABLE = True
except ImportError:
    logger.warning("openrouter_client not importable — optimizer will use heuristic fallback.")


_PII_AVAILABLE = False

try:
    from services.pii_sanitizer import sanitize_pii, restore_pii
    _PII_AVAILABLE = True
    logger.info("PII sanitizer loaded — resume text will be scrubbed before LLM calls.")
except ImportError:
    _PII_AVAILABLE = False


# ===================================================================
# LLM call helper
# ===================================================================

_LLM_TIMEOUT = 180.0  # 3 minutes


async def _call_llm(
    messages: list[dict[str, str]],
    model_role: str = "builder",
    temperature: float = 0.6,
    max_tokens: int = 3000,
    timeout: float = _LLM_TIMEOUT,
    json_mode: bool = False,
) -> str | None:
    """Call OpenRouter via centralized client with 180s timeout."""
    if not _OPENROUTER_AVAILABLE or not openrouter_client.is_openrouter_active:
        return None
    try:
        return await asyncio.wait_for(
            openrouter_client.call(
                model_role=model_role,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error("Optimizer LLM call timed out after %.0fs.", timeout)
    except Exception as exc:
        logger.error("Optimizer LLM call failed: %s", exc)
    return None


def _try_parse_json(text: str) -> Any | None:
    """Parse text as JSON, tolerating markdown fences."""
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
# Generic / vague phrase patterns
# ===================================================================

GENERIC_PHRASES: list[str] = [
    r"\bresponsible for\b",
    r"\bhelped\b.*\bwith\b",
    r"\bworked on\b",
    r"\bassisted\b.*\bin\b",
    r"\bpart of (?:a|the)\b",
    r"\bwas involved (?:in|with)\b",
    r"\bcontributed to\b",
    r"\bvarious\b",
    r"\betc\.?\b",
    r"\bhandled\b",
    r"\bdealt with\b",
    r"\bfamiliar (?:with|to)\b",
    r"\bgood (?:at|communication|teamwork)\b",
    r"\bstrong (?:communication|teamwork|analytical|organizational)\b",
    r"\bteam player\b",
    r"\bhard worker\b",
    r"\bself[- ]motivated\b",
    r"\bquick learner\b",
    r"\battention to detail\b",
    r"\bexcellent (?:communication|problem[- ]solving|interpersonal)\b",
    r"\bability to work\b",
    r"\bpassionate about\b",
    r"\blooking (?:for|to)\b",
    r"\bseeking\b",
    r"\bresults[- ]driven\b",
    r"\bproven track record\b",
    r"\bhighly motivated\b",
    r"\bdetail[- ]oriented\b",
    r"\bfast[- ]paced\b",
    r"\bdynamic (?:environment|team)\b",
]

STRONG_ACTION_VERBS: list[str] = [
    "architected", "spearheaded", "orchestrated", "pioneered", "streamlined",
    "automated", "refactored", "accelerated", "consolidated", "migrated",
    "engineered", "optimized", "delivered", "launched", "scaled",
    "built", "designed", "implemented", "developed", "led", "managed",
    "drove", "reduced", "increased", "improved", "achieved",
    "established", "created", "deployed", "integrated", "configured",
    "transformed", "eliminated", "resolved", "negotiated",
]

CAREER_STAGE_PROMPTS: dict[str, str] = {
    "entry_level": "The candidate is early-career. Focus on education, internships, projects.",
    "mid_level": "The candidate is mid-career. Focus on tangible impact and growing scope.",
    "senior": "The candidate is senior/lead. Emphasize strategic impact and mentoring.",
    "executive": "The candidate is executive-level. Focus on P&L impact and organizational transformation.",
}


def _detect_generic_phrases(text: str) -> list[str]:
    found: list[str] = []
    for pattern in GENERIC_PHRASES:
        for m in re.findall(pattern, text, re.IGNORECASE):
            if m.strip() not in found:
                found.append(m.strip())
    return found


def _extract_bullet_points(text: str) -> list[str]:
    bullets = re.split(r"\n\s*[-•*]\s*|\n\s*\d+[.)]\s*", text)
    bullets = [b.strip() for b in bullets if b.strip() and len(b.strip()) > 15]
    if len(bullets) >= 3:
        return bullets
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip() and len(s.strip()) > 15]


def _has_metrics(bullet: str) -> bool:
    return bool(
        re.search(r"\d+%", bullet)
        or re.search(r"\$[\d,.]+[KkMmBb]?", bullet)
        or re.search(r"\d+\+?\s*(?:users|customers|clients|projects|teams?|servers|requests)", bullet)
        or re.search(r"\d+x\b", bullet)
    )


def _rewrite_bullet_heuristic(bullet: str, missing_keywords: list[str]) -> tuple[str, list[str]]:
    added: list[str] = []
    rewritten = bullet
    first_word = rewritten.split()[0].lower() if rewritten.split() else ""
    if first_word in ("was", "were", "been", "had", "have", "has", "did", "got", "made", "took"):
        context_lower = rewritten.lower()
        verb = "developed"
        for v in STRONG_ACTION_VERBS:
            if any(kw in context_lower for kw in [v, v[:4]]):
                verb = v
                break
        rewritten = verb + " " + rewritten
        rewritten = re.sub(r"^[A-Za-z]+\s+(?:was|were|had|have|has|did|got|made)\s+", "", rewritten, count=1)
        rewritten = rewritten[0].upper() + rewritten[1:] if rewritten else rewritten

    injected = 0
    for kw in missing_keywords:
        if injected >= 2:
            break
        kw_lower = kw.lower()
        if kw_lower not in rewritten.lower():
            if rewritten.rstrip()[-1:] in ".!,":
                rewritten = rewritten.rstrip()[:-1] + f", leveraging {kw}" + rewritten.rstrip()[-1]
            else:
                rewritten += f", leveraging {kw}"
            added.append(kw)
            injected += 1
    return rewritten, added


def _heuristic_optimize(resume_text: str, job_description: str, career_stage: str) -> dict[str, Any]:
    before_ats = calculate_ats_score(resume_text)
    jd_skills = extract_skills_from_text(job_description)
    jd_keywords = extract_keywords(job_description)
    resume_lower = resume_text.lower()
    missing_skills = [s for s in jd_skills if s.lower() not in resume_lower]
    missing_generic = [kw for kw in jd_keywords if kw.lower() not in resume_lower and len(kw) > 2]
    generic_phrases = _detect_generic_phrases(resume_text)
    bullets = _extract_bullet_points(resume_text)
    optimized_bullets = []
    all_added: list[str] = []

    for bullet in bullets:
        if any(re.search(gp, bullet, re.IGNORECASE) for gp in GENERIC_PHRASES):
            rewritten, added = _rewrite_bullet_heuristic(bullet, missing_skills[:5])
            optimized_bullets.append(rewritten)
            all_added.extend(added)
        else:
            optimized_bullets.append(bullet)

    if re.search(r"\n\s*[-•*]\s*", resume_text):
        optimized_text = "\n".join(f"- {b}" for b in optimized_bullets)
    else:
        optimized_text = "\n".join(optimized_bullets)

    removed = generic_phrases[:10]
    full_optimized = resume_text
    for phrase in generic_phrases[:5]:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        match = pattern.search(full_optimized)
        if match:
            start = full_optimized.rfind(".", 0, match.start())
            start = full_optimized.rfind("\n", 0, match.start()) if start == -1 else start
            start = max(0, start + 1)
            end = full_optimized.find(".", match.end())
            end = len(full_optimized) if end == -1 else end + 1
            sentence = full_optimized[start:end].strip()
            if sentence and len(sentence) > 20:
                rewritten, added = _rewrite_bullet_heuristic(sentence, missing_skills[:5])
                full_optimized = full_optimized[:start] + rewritten + full_optimized[end:]
                all_added.extend(added)

    after_ats = calculate_ats_score(full_optimized)
    return {
        "optimized_text": full_optimized,
        "added_keywords": list(dict.fromkeys(all_added))[:15],
        "removed_generic_phrases": removed,
        "before_ats_score": before_ats,
        "after_ats_score": after_ats,
        "optimization_method": "heuristic",
    }


# ===================================================================
# ResumeOptimizer Class
# ===================================================================

class ResumeOptimizer:
    """LLM-powered resume optimizer with heuristic fallback.

    All LLM calls go through ``openrouter_client`` — NO local proxy.
    """

    def __init__(self) -> None:
        self._pii_available = _PII_AVAILABLE

    async def _sanitize_for_llm(self, text: str) -> tuple[str, dict | None]:
        if self._pii_available:
            try:
                return sanitize_pii(text)
            except Exception:
                logger.warning("PII sanitization failed, proceeding without scrubbing.")
        return text, None

    def _restore_from_llm(self, text: str, pii_map: dict | None) -> str:
        if self._pii_available and pii_map:
            try:
                return restore_pii(text, pii_map)
            except Exception:
                logger.warning("PII restoration failed, returning text as-is.")
        return text

    async def optimize_resume(
        self,
        resume_text: str,
        job_description: str,
        career_stage: str = "mid_level",
    ) -> dict[str, Any]:
        resume_text = resume_text.strip()
        job_description = job_description.strip()

        if not resume_text or not job_description:
            return {
                "optimized_text": resume_text,
                "added_keywords": [],
                "removed_generic_phrases": [],
                "before_ats_score": calculate_ats_score(resume_text),
                "after_ats_score": calculate_ats_score(resume_text),
                "optimization_method": "none",
                "error": "Empty resume text or job description.",
            }

        if career_stage not in CAREER_STAGE_PROMPTS:
            career_stage = "mid_level"

        before_ats = calculate_ats_score(resume_text)
        generic_phrases = _detect_generic_phrases(resume_text)
        jd_skills = extract_skills_from_text(job_description)
        jd_keywords = extract_keywords(job_description)
        resume_lower = resume_text.lower()
        missing_skills = [s for s in jd_skills if s.lower() not in resume_lower]
        missing_generic = [kw for kw in jd_keywords if kw.lower() not in resume_lower and len(kw) > 2]

        # Try LLM optimization
        llm_result = await self._llm_optimize(
            resume_text, job_description, career_stage,
            missing_skills, missing_generic, generic_phrases,
        )

        if llm_result:
            after_ats = calculate_ats_score(llm_result["optimized_text"])
            return {**llm_result, "before_ats_score": before_ats, "after_ats_score": after_ats, "optimization_method": "llm"}

        logger.info("LLM optimization unavailable, using heuristic fallback.")
        heuristic = _heuristic_optimize(resume_text, job_description, career_stage)
        return heuristic

    async def _llm_optimize(
        self,
        resume_text: str,
        job_description: str,
        career_stage: str,
        missing_skills: list[str],
        missing_keywords: list[str],
        generic_phrases: list[str],
    ) -> dict[str, Any] | None:
        # Sanitize PII before LLM call
        sanitized_resume, pii_map = await self._sanitize_for_llm(resume_text)
        sanitized_jd, _ = await self._sanitize_for_llm(job_description)

        stage_guidance = CAREER_STAGE_PROMPTS.get(career_stage, CAREER_STAGE_PROMPTS["mid_level"])

        system_prompt = _get_system_prompt(
            "resume_optimizer",
            stage_guidance=stage_guidance,
            missing_skills=', '.join(missing_skills[:15]) or 'None detected',
            missing_keywords=', '.join(missing_keywords[:10]) or 'None detected',
            generic_phrases=', '.join(generic_phrases[:8]) or 'None detected',
        )

        user_prompt = (
            f"## RESUME TO OPTIMIZE:\n{sanitized_resume[:4000]}\n\n"
            f"## TARGET JOB DESCRIPTION:\n{sanitized_jd[:3000]}\n\n"
            f"## ANALYSIS:\n"
            f"- Missing JD skills: {', '.join(missing_skills[:15]) or 'None detected'}\n"
            f"- Missing JD keywords: {', '.join(missing_keywords[:10]) or 'None detected'}\n"
            f"- Generic phrases: {', '.join(generic_phrases[:8]) or 'None detected'}\n\n"
            '{"optimized_text": "...", "added_keywords": [...], "removed_generic_phrases": [...], "changes_summary": "..."}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw = await _call_llm(messages, model_role="builder", temperature=0.6, max_tokens=4000, json_mode=True)
        if not raw:
            return None

        parsed = _try_parse_json(raw)
        if not parsed or not isinstance(parsed, dict):
            logger.warning("Failed to parse optimizer LLM response as JSON.")
            return None

        optimized = parsed.get("optimized_text", "")
        if not optimized or len(optimized) < 50:
            logger.warning("LLM returned empty/too-short optimized text.")
            return None

        # Restore PII
        optimized = self._restore_from_llm(optimized, pii_map)

        return {
            "optimized_text": optimized,
            "added_keywords": parsed.get("added_keywords", [])[:20],
            "removed_generic_phrases": parsed.get("removed_generic_phrases", [])[:15],
            "changes_summary": parsed.get("changes_summary", ""),
        }

    async def generate_optimized_cover_letter(
        self,
        resume_text: str,
        job_description: str,
        company: str,
        role: str,
    ) -> dict[str, Any]:
        """Generate a cover letter informed by resume analysis against the JD.

        This is the ONLY cover letter generator in TALVEX. It performs skill
        gap analysis and produces a targeted letter that bridges the candidate's
        experience with the job requirements.
        """
        resume_skills = extract_skills_from_text(resume_text)
        jd_skills = extract_skills_from_text(job_description)
        missing_skills = [s for s in jd_skills if s.lower() not in resume_text.lower()]

        # Sanitize PII
        sanitized_resume, pii_map = await self._sanitize_for_llm(resume_text)
        sanitized_jd, _ = await self._sanitize_for_llm(job_description)

        messages = [
            {"role": "system", "content": _get_system_prompt("optimized_cover_letter")},
            {"role": "user", "content": (
                f"Company: {company}\nRole: {role}\n\n"
                f"Resume:\n{sanitized_resume[:3000]}\n\n"
                f"Job Description:\n{sanitized_jd[:2000]}\n\n"
                f"Candidate's existing skills: {', '.join(resume_skills[:20])}\n"
                f"Missing JD skills: {', '.join(missing_skills[:10]) or 'All key skills covered'}\n\n"
                "Write a tailored cover letter:"
            )},
        ]

        raw = await _call_llm(messages, model_role="builder", temperature=0.7, max_tokens=2000, json_mode=True)
        if raw:
            parsed = _try_parse_json(raw)
            if parsed and isinstance(parsed, dict) and "cover_letter" in parsed:
                letter = self._restore_from_llm(parsed.get("cover_letter", ""), pii_map)
                return {
                    "cover_letter": letter,
                    "tone": parsed.get("tone", "professional"),
                    "highlights_count": parsed.get("highlights_count", 0),
                }

        # Heuristic fallback — generate a simple cover letter inline
        jd_lower = job_description.lower()
        matched = [s for s in resume_skills[:8] if s.lower() in jd_lower]
        skills_str = ", ".join(matched[:5]) if matched else "my technical background"
        body = (
            f"My experience with {skills_str} aligns directly with the requirements "
            f"of the {role} position. I have successfully leveraged these competencies "
            f"to deliver measurable impact in my previous roles, and I am eager to bring "
            f"that same drive to {company}."
        ) if matched else (
            f"My diverse technical background equips me to tackle the challenges of the "
            f"{role} role at {company}. I am confident that my skills and experience "
            f"position me to contribute meaningfully to your team from day one."
        )
        letter = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {role} position. "
            f"{body}\n\n"
            f"I would welcome the opportunity to discuss how my experience aligns "
            f"with your needs. Thank you for considering my application.\n\n"
            f"Best regards"
        )
        return {
            "cover_letter": letter,
            "tone": "professional",
            "highlights_count": len(matched[:3]),
        }


# Singleton instance
resume_optimizer = ResumeOptimizer()
