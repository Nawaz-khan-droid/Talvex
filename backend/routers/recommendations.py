"""
FastAPI router for recommendations.
Endpoints:
  GET  /api/recommendations/skill-gap/{persona_id} - Skill gap analysis (LLM-powered)
  GET  /api/recommendations/trades - Trade/role recommendations (LLM-powered)
  GET  /api/recommendations/pipeline - Pipeline telemetry (DB-based)
  POST /api/recommendations/follow-up/{app_id} - Generate follow-up template

Skill-gap and trade-recommendation endpoints now use the OpenRouter LLM client
for intelligent analysis instead of hardcoded role profiles and static skill lists.
Pipeline and follow-up endpoints remain DB/template-based.
"""

import json
import logging
import re
import traceback
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application, JobPersona
from services import matcher
from services.openrouter_client import openrouter_client, OpenRouterError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

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


# Legacy inline prompts (kept as module-level constants for backward compatibility)
# These are NOT used as fallbacks — _get_system_prompt() always goes to the prompt manager.


def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

_SKILL_GAP_SYSTEM = """\
You are a senior career advisor and technical recruiter AI for TALVEX, a career command center.

Analyze the given professional profile and identify skill gaps.

CRITICAL RULES:
1. Return ONLY valid JSON — no markdown, no commentary outside the JSON.
2. All skill names must be real, recognizable technology or professional skills.
   NEVER output raw numbers, fragments, or garbage like "000", "/month", "1." as skill names.
3. Priority levels: "high", "medium", or "low".
4. Market demand scores: 0-100 integers.
5. Estimated weeks: positive integers.

Return JSON:
{
  "gaps": [
    {
      "skill": "string — missing skill name",
      "category": "string — Frontend|Backend|Data & ML|Cloud & DevOps|Databases|Data Analysis|Testing|General",
      "priority": "high|medium|low",
      "marketDemand": 85,
      "learningPath": "string — specific, actionable learning path",
      "estimatedWeeks": 4
    }
  ]
}

Return 10-15 skill gaps sorted by market demand (highest first)."""


_TRADE_RECS_SYSTEM = """\
You are a senior career advisor and technical recruiter AI for TALVEX, a career command center.

Analyze the given professional profile(s) and suggest career role transitions.

CRITICAL RULES:
1. Return ONLY valid JSON — no markdown, no commentary outside the JSON.
2. Salary ranges should be realistic annual USD figures for the US market.
3. All skill names must be real technology/professional skills.
4. NEVER output garbage like "000", "/month" as skill names.

Return JSON:
{
  "recommendations": [
    {
      "targetRole": "string — specific job title",
      "personaId": "string — the persona ID this recommendation is for",
      "personaName": "string — persona name",
      "alignmentScore": 75,
      "missingSkills": ["string — missing skill name", "..."],
      "salaryRange": {"min": 80000, "max": 160000},
      "actionSteps": ["string — specific actionable step", "..."]
    }
  ]
}

Return 4-6 trade recommendations per persona, sorted by alignment score (highest first).
Include at least 1 "reach" role per persona (lower alignment but high growth potential)."""


def _extract_json(raw: str) -> dict[str, Any]:
    """Pull JSON out of a potentially fenced LLM response."""
    # Try fenced code block
    fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", raw)
    if fence:
        return json.loads(fence.group(1).strip())

    # Try first { … last }
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last > first:
        return json.loads(raw[first : last + 1])

    raise ValueError("No JSON object found in LLM response")


def _clamp(value: Any, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return lo


async def _llm_skill_gap(skills: list[str], persona_name: str) -> list[dict[str, Any]]:
    """Call the LLM to analyze skill gaps for a persona."""
    user_msg = (
        f"**Name:** {persona_name}\n"
        f"**Current Skills:** {', '.join(skills)}\n\n"
        f"Identify the most impactful skill gaps and return JSON."
    )

    raw = await openrouter_client.call(
        model_role="architect",
        messages=[
            {"role": "system", "content": _get_system_prompt("skill_gap_analyzer")},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=3000,
        json_mode=True,
    )

    parsed = _extract_json(raw)
    gaps = parsed.get("gaps", [])

    # Sanitize
    valid_categories = {
        "Frontend", "Backend", "Data & ML", "Cloud & DevOps",
        "Databases", "Data Analysis", "Testing", "General",
    }
    valid_priorities = {"high", "medium", "low"}
    sanitized = []
    for g in gaps:
        skill = str(g.get("skill", "")).strip()
        if not skill or len(skill) < 2 or re.match(r"^[\d\/\s,.\-]+$", skill):
            continue
        sanitized.append({
            "skill": skill,
            "category": g.get("category", "General") if g.get("category") in valid_categories else "General",
            "priority": g.get("priority", "medium") if g.get("priority") in valid_priorities else "medium",
            "marketDemand": _clamp(g.get("marketDemand", 50), 0, 100),
            "learningPath": str(g.get("learningPath", "Research and build projects with this skill.")),
            "estimatedWeeks": _clamp(g.get("estimatedWeeks", 4), 1, 52),
        })

    return sanitized[:15]


async def _llm_trade_recs(
    personas: list[tuple[str, str, list[str]]],
) -> list[dict[str, Any]]:
    """Call the LLM to generate trade recommendations for all personas."""
    persona_descriptions = []
    for pid, pname, skills in personas:
        persona_descriptions.append(
            f"- **ID:** {pid}, **Name:** {pname}, **Skills:** {', '.join(skills)}"
        )

    user_msg = (
        "Analyze these professional profiles and suggest career transitions:\n\n"
        + "\n".join(persona_descriptions)
        + "\n\nProvide role recommendations as JSON."
    )

    raw = await openrouter_client.call(
        model_role="architect",
        messages=[
            {"role": "system", "content": _get_system_prompt("trade_recommender")},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=4000,
        json_mode=True,
    )

    parsed = _extract_json(raw)
    recs = parsed.get("recommendations", [])

    # Sanitize — keep only recommendations for known personas
    known_ids = {pid for pid, _, _ in personas}
    sanitized = []
    for r in recs:
        pid = str(r.get("personaId", ""))
        if pid not in known_ids:
            continue
        salary = r.get("salaryRange", {})
        s_min = _clamp(salary.get("min", 50000), 20000, 500000)
        s_max = _clamp(salary.get("max", 120000), 20000, 500000)

        missing = []
        for s in r.get("missingSkills", []):
            sk = str(s).strip()
            if sk and len(sk) >= 2 and not re.match(r"^[\d\/\s,.\-]+$", sk):
                missing.append(sk)

        steps = r.get("actionSteps", [])
        if not isinstance(steps, list):
            steps = ["Update your resume and apply to relevant positions."]

        sanitized.append({
            "targetRole": str(r.get("targetRole", "Unknown Role")),
            "personaId": pid,
            "personaName": str(r.get("personaName", "")),
            "alignmentScore": _clamp(r.get("alignmentScore", 50), 0, 100),
            "missingSkills": missing[:10],
            "salaryRange": {"min": min(s_min, s_max), "max": max(s_min, s_max)},
            "actionSteps": [str(s) for s in steps[:6]],
        })

    sanitized.sort(key=lambda x: x["alignmentScore"], reverse=True)
    return sanitized[:15]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/skill-gap/{persona_id}")
async def get_skill_gap(persona_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get skill gap analysis for a persona (LLM-powered)."""
    result = await db.execute(select(JobPersona).filter(JobPersona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and persona.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this persona")

    skills = matcher.get_personas_skills_json(persona.skillsJson)

    if not skills:
        return {
            "personaId": persona.id,
            "personaName": persona.name,
            "currentSkills": [],
            "skillCount": 0,
            "gaps": [],
        }

    try:
        gaps = await _llm_skill_gap(skills, persona.name)
    except OpenRouterError as exc:
        logger.warning("LLM skill-gap analysis failed, falling back to static matcher: %s", exc)
        gaps = matcher.analyze_skill_gap(skills)

    return {
        "personaId": persona.id,
        "personaName": persona.name,
        "currentSkills": skills,
        "skillCount": len(skills),
        "gaps": gaps,
    }


@router.get("/trades")
async def get_trade_recommendations(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get trade/role recommendations based on current personas (LLM-powered)."""
    stmt = select(JobPersona)
    if not _is_admin(current_user):
        stmt = stmt.filter(JobPersona.userId == current_user["user_id"])
    result = await db.execute(stmt)
    personas = result.scalars().all()

    if not personas:
        return {"recommendations": []}

    persona_data = [
        (p.id, p.name, matcher.get_personas_skills_json(p.skillsJson))
        for p in personas
        if matcher.get_personas_skills_json(p.skillsJson)  # skip empty skill sets
    ]

    if not persona_data:
        return {"recommendations": []}

    try:
        recommendations = await _llm_trade_recs(persona_data)
    except OpenRouterError as exc:
        logger.warning("LLM trade recommendations failed, returning empty: %s", exc)
        return {"recommendations": []}

    return {"recommendations": recommendations}


@router.get("/pipeline")
async def get_pipeline_telemetry(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get pipeline telemetry data (DB-based, no LLM needed)."""
    user_id = None if _is_admin(current_user) else current_user["user_id"]
    filters = [Application.userId == user_id] if user_id else []

    total_apps = (await db.execute(
        select(func.count(Application.id)).filter(*filters)
    )).scalar() or 0
    avg_match = (await db.execute(
        select(func.avg(Application.matchScore)).filter(*filters)
    )).scalar() or 0
    high_match = (await db.execute(
        select(func.count(Application.id)).filter(*filters, Application.matchScore >= 70)
    )).scalar() or 0

    # Status breakdown
    status_results = (await db.execute(
        select(
            Application.status,
            func.count(Application.id).label("count"),
        )
        .filter(*filters)
        .group_by(Application.status)
    )).all()

    status_breakdown = {}
    status_labels = {
        "SCRAPED": "Scraped", "TAILORED": "Tailored", "SUBMITTED": "Submitted",
        "SCREENING": "Screening", "ASSESSMENT": "Assessment", "INTERVIEWING": "Interviewing",
        "OFFER": "Offer", "REJECTED": "Rejected", "GHOSTED": "Ghosted",
    }
    for r in status_results:
        status_breakdown[status_labels.get(r.status, r.status)] = r.count

    # Top target roles
    role_results = (await db.execute(
        select(
            Application.roleTitle,
            func.count(Application.id).label("count"),
            func.avg(Application.matchScore).label("avg_score"),
        )
        .filter(*filters)
        .group_by(Application.roleTitle)
        .order_by(func.count(Application.id).desc())
        .limit(10)
    )).all()

    top_roles = [
        {"role": r.roleTitle, "count": r.count, "avgScore": round(float(r.avg_score), 1) if r.avg_score else 0}
        for r in role_results
    ]

    return {
        "totalApplications": total_apps,
        "averageMatchScore": round(float(avg_match), 1),
        "highMatchCount": high_match,
        "statusBreakdown": status_breakdown,
        "topTargetRoles": top_roles,
    }


@router.post("/follow-up/{app_id}")
async def generate_follow_up(app_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Generate a follow-up template for an application."""
    result = await db.execute(select(Application).filter(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this application")

    now = datetime.utcnow()
    applied_date = app.appliedDate or app.createdAt
    days_since_applied = (now - applied_date).days if applied_date else 0

    # Determine urgency
    if days_since_applied > 14:
        urgency = "urgent"
    elif days_since_applied > 7:
        urgency = "normal"
    else:
        urgency = "low"

    # Select template based on status and context
    status = app.status.upper()

    if status == "SUBMITTED" and days_since_applied >= 7:
        template = (
            f"Subject: Following Up on {app.roleTitle} Application - {app.company}\n\n"
            f"Dear Hiring Team,\n\n"
            f"I hope this message finds you well. I submitted my application for the "
            f"{app.roleTitle} position at {app.company} on "
            f"{(applied_date or now).strftime('%B %d, %Y')}. "
            f"I wanted to follow up to express my continued interest in the role.\n\n"
            f"I'm particularly excited about the opportunity because my experience aligns well "
            f"with what {app.company} is looking for. I'd welcome the chance to discuss "
            f"how my skills and background could contribute to your team.\n\n"
            f"Thank you for considering my application.\n\n"
            f"Best regards"
        )
    elif status == "SCREENING":
        template = (
            f"Subject: Checking In - {app.roleTitle} at {app.company}\n\n"
            f"Dear Hiring Team,\n\n"
            f"I hope you're doing well. I wanted to check on the status of my application "
            f"for the {app.roleTitle} position at {app.company}. "
            f"I understand you may be busy, and I truly appreciate your time.\n\n"
            f"Please let me know if there's any additional information I can provide "
            f"to support my application. I remain very interested in the opportunity.\n\n"
            f"Best regards"
        )
    elif status == "INTERVIEWING":
        template = (
            f"Subject: Thank You - {app.roleTitle} Interview - {app.company}\n\n"
            f"Dear {app.company} Team,\n\n"
            f"Thank you for the opportunity to interview for the {app.roleTitle} position. "
            f"I really enjoyed learning more about the role and the team.\n\n"
            f"After our conversation, I'm even more enthusiastic about the opportunity. "
            f"I believe my experience with the skills and technologies discussed "
            f"would allow me to make a meaningful contribution.\n\n"
            f"I look forward to hearing about the next steps.\n\n"
            f"Best regards"
        )
    else:
        template = (
            f"Subject: Re: {app.roleTitle} Application - {app.company}\n\n"
            f"Dear Hiring Team,\n\n"
            f"I hope this message finds you well. I wanted to follow up on my application "
            f"for the {app.roleTitle} position at {app.company}.\n\n"
            f"I remain very interested in this opportunity and would love to discuss "
            f"how I can contribute to your team. Please feel free to reach out if "
            f"you need any additional information.\n\n"
            f"Best regards"
        )

    return {
        "template": template,
        "urgency": urgency,
        "daysSinceApplied": days_since_applied,
        "followUpCount": app.followUpCount,
    }
