"""
FastAPI router for job search and ingestion.
Endpoints:
  POST /api/jobs/search - Search jobs via RapidAPI JSearch
  POST /api/jobs/tavily-search - Search jobs via Tavily API
  POST /api/jobs/ingest - Ingest a job into the application pipeline
  GET /api/jobs/salary - Get salary estimate
  POST /api/jobs/parse-email - Parse job from email body text
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application, JobPersona
from schemas import (
    ApplicationResponse,
    EmailParseRequest,
    EmailParseResponse,
    JobIngestRequest,
    JobSearchRequest,
    SalaryEstimateRequest,
)
from services import jsearch_client, matcher
from services.tavily_client import tavily

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _generate_id() -> str:
    """Generate a unique ID (cuid-like)."""
    import uuid
    return uuid.uuid4().hex[:25]


def _title_case_status(status: str) -> str:
    """Convert SCRAPED -> Scraped etc."""
    return status.title()


class TavilySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Job search query (e.g. 'Python Developer remote')")
    location: str = Field("", description="Optional location filter")
    employment_type: str = Field("", description="full-time, part-time, contract, intern")
    max_results: int = Field(10, ge=1, le=20, description="Maximum number of results")


def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


@router.post("/tavily-search")
async def search_jobs_tavily(request: TavilySearchRequest, current_user: dict = Depends(get_current_user)):
    """Search jobs via Tavily API (web search across job boards)."""
    try:
        results = await tavily.search_jobs(
            job_title=request.query,
            location=request.location,
            employment_type=request.employment_type,
            max_results=request.max_results,
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        logger.error(f"Tavily job search failed: {e}")
        raise HTTPException(status_code=502, detail=f"Tavily search failed: {str(e)}")


@router.post("/search")
async def search_jobs(request: JobSearchRequest, current_user: dict = Depends(get_current_user)):
    """Search jobs via RapidAPI JSearch API."""
    try:
        result = await jsearch_client.search_jobs(
            query=request.query,
            country=request.country,
            num_pages=request.num_pages,
            date_posted=request.date_posted,
        )
        return result
    except Exception as e:
        logger.error(f"Job search failed: {e}")
        raise HTTPException(status_code=502, detail=f"Job search failed: {str(e)}")


@router.post("/ingest", response_model=ApplicationResponse)
async def ingest_job(request: JobIngestRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Ingest a specific job into the application pipeline."""
    # Validate persona exists
    persona = None
    if request.persona_id:
        persona_result = await db.execute(
            select(JobPersona).filter(JobPersona.id == request.persona_id)
        )
        persona = persona_result.scalar_one_or_none()
        if not persona:
            raise HTTPException(status_code=404, detail=f"Persona '{request.persona_id}' not found")

    # Get or use provided app_id
    app_id = request.app_id or _generate_id()

    now = datetime.utcnow()

    # Extract keywords from job description
    keywords = matcher.extract_keywords(request.job_description)
    extracted_keywords = json.dumps(keywords)

    # Calculate match score if persona is available
    match_score = 0.0
    ats_score = 0.0
    if persona:
        skills = matcher.get_personas_skills_json(persona.skillsJson)
        match_result = matcher.calculate_match_score(request.job_description, skills)
        match_score = float(match_result["score"])
        ats_score = float(matcher.calculate_ats_score(request.job_description))

    application = Application(
        id=app_id,
        personaId=request.persona_id or "",
        userId=current_user["user_id"],
        company=request.company,
        roleTitle=request.role_title,
        jobDescription=request.job_description,
        status="SCRAPED",
        matchScore=match_score,
        atsScore=ats_score,
        extractedKeywords=extracted_keywords,
        platform=request.platform,
        jobUrl=request.job_url,
        salaryMin=request.salary_min,
        salaryMax=request.salary_max,
        salaryCurrency=request.salary_currency,
        workMode=request.work_mode,
        tenure=request.tenure,
        perks=request.perks,
        location=request.location,
        companySize=request.company_size,
        sourceEmail=None,
        createdAt=now,
        updatedAt=now,
    )

    db.add(application)
    await db.commit()
    await db.refresh(application)

    return await _format_application(application, persona, db)


@router.get("/salary")
async def get_salary(request: SalaryEstimateRequest, current_user: dict = Depends(get_current_user)):
    """Get estimated salary for a job title at a location."""
    try:
        result = await jsearch_client.get_estimated_salary(
            job_title=request.job_title,
            location=request.location,
        )
        return {"results": result}
    except Exception as e:
        logger.error(f"Salary lookup failed: {e}")
        raise HTTPException(status_code=502, detail=f"Salary lookup failed: {str(e)}")


@router.post("/parse-email", response_model=EmailParseResponse)
async def parse_email(request: EmailParseRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Parse a job from email body text.
    Extracts company, role title, and job description from raw email content.
    """
    body = request.email_body

    # Extract company
    company = ""
    company_patterns = [
        r"(?:company|organization|employer)[:\s]+([^\n,]+)",
        r"(?:at|@)\s+([A-Z][A-Za-z0-9&\s]+?)(?:\s*[,\.\n]|\s+(?:we|our|the|is|has))",
        r"([A-Z][A-Za-z0-9&\s]{3,40})\s+is (?:looking|hiring|seeking)",
    ]
    for pattern in company_patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            company = m.group(1).strip()
            break

    if not company:
        # Try first line that looks like a company name
        for line in body.split("\n"):
            line = line.strip()
            if 3 < len(line) < 50 and re.match(r"^[A-Z]", line) and not re.match(r"^(hi|hello|dear|subject|from|to|date)", line, re.IGNORECASE):
                company = line
                break

    # Extract role title
    role_title = ""
    role_patterns = [
        r"(?:role|position|title|job)[:\s]+([^\n,]+)",
        r"(?:looking for|seeking|hiring|opening)\s+(?:a|an)?\s*([A-Za-z0-9\s/+&-]+?)(?:\s*[,\.\n]|\s+(?:to|for|with|who))",
    ]
    for pattern in role_patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            role_title = m.group(1).strip()
            break

    if not role_title:
        role_title = "Unknown Role"

    # Extract job description (everything after the first substantial paragraph)
    lines = body.split("\n")
    desc_lines = [l.strip() for l in lines if len(l.strip()) > 20]
    job_description = "\n".join(desc_lines[:30]) if desc_lines else body[:2000]

    # Create application
    now = datetime.utcnow()
    keywords = matcher.extract_keywords(job_description)
    extracted_keywords = json.dumps(keywords)

    app_id = _generate_id()
    persona_id = request.persona_id or ""

    application = Application(
        id=app_id,
        personaId=persona_id,
        userId=current_user["user_id"],
        company=company or "Unknown Company",
        roleTitle=role_title,
        jobDescription=job_description,
        status="SCRAPED",
        matchScore=0.0,
        atsScore=float(matcher.calculate_ats_score(job_description)),
        extractedKeywords=extracted_keywords,
        platform="email",
        sourceEmail="parsed",
        createdAt=now,
        updatedAt=now,
    )

    db.add(application)
    await db.commit()
    await db.refresh(application)

    return EmailParseResponse(
        success=True,
        application_id=app_id,
        extracted_fields={
            "company": company or "Unknown Company",
            "role_title": role_title,
            "platform": "email",
            "status": _title_case_status("SCRAPED"),
        },
    )


async def _format_application(
    app: Application,
    persona: JobPersona | None,
    db: AsyncSession,
) -> dict:
    """Format an Application ORM object as a response dict with title case status."""
    app_count = None
    if persona:
        app_count = (await db.execute(
            select(func.count(Application.id)).filter(Application.personaId == persona.id)
        )).scalar()

    return {
        "id": app.id,
        "personaId": app.personaId,
        "company": app.company,
        "roleTitle": app.roleTitle,
        "jobDescription": app.jobDescription,
        "status": _title_case_status(app.status),
        "matchScore": app.matchScore,
        "atsScore": app.atsScore,
        "extractedKeywords": app.extractedKeywords,
        "privacyStatus": app.privacyStatus.title(),
        "appliedDate": app.appliedDate.isoformat() if app.appliedDate else None,
        "lastFollowUp": app.lastFollowUp.isoformat() if app.lastFollowUp else None,
        "createdAt": app.createdAt.isoformat() if app.createdAt else None,
        "updatedAt": app.updatedAt.isoformat() if app.updatedAt else None,
        "platform": app.platform,
        "jobUrl": app.jobUrl,
        "salaryMin": app.salaryMin,
        "salaryMax": app.salaryMax,
        "salaryCurrency": app.salaryCurrency,
        "workMode": app.workMode,
        "tenure": app.tenure,
        "perks": app.perks,
        "location": app.location,
        "companySize": app.companySize,
        "sourceEmail": app.sourceEmail,
        "nextFollowUp": app.nextFollowUp.isoformat() if app.nextFollowUp else None,
        "followUpCount": app.followUpCount,
        "lastResponseAt": app.lastResponseAt.isoformat() if app.lastResponseAt else None,
        "responseType": app.responseType,
        "notes": app.notes,
        "persona": {
            "id": persona.id,
            "name": persona.name,
            "skillsJson": persona.skillsJson,
            "masterBullets": persona.masterBullets,
            "summaryTemplate": persona.summaryTemplate,
            "createdAt": persona.createdAt.isoformat() if persona.createdAt else None,
            "updatedAt": persona.updatedAt.isoformat() if persona.updatedAt else None,
            "applicationCount": app_count,
        } if persona else None,
    }
