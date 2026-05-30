"""
FastAPI router for application CRUD and status advancement.
Endpoints:
  GET  /api/applications - List all applications (with optional status filter)
  POST /api/applications - Create new application
  GET  /api/applications/{id} - Get single application
  PATCH /api/applications/{id} - Update application
  POST /api/applications/{id}/advance - Advance status (FSM rules)
  DELETE /api/applications/{id} - Delete application
  GET /api/applications/follow-ups/alerts - Get follow-up alerts

All endpoints require authentication. Every query is scoped to the current
user's data (unless the user has the "admin" role).

All status labels in responses use Title Case.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application, AuditLog, JobPersona
from schemas import ApplicationCreate, ApplicationUpdate, StatusAdvanceRequest
from services import matcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/applications", tags=["applications"])

# ============================================================
# FSM Configuration
# ============================================================

FSM_TRANSITIONS: dict[str, list[dict]] = {
    "SCRAPED": [
        {"to": "TAILORED", "label": "Start Tailoring"},
        {"to": "REJECTED", "label": "Skip / Not Applying", "is_terminal": True},
    ],
    "TAILORED": [
        {"to": "SUBMITTED", "label": "Submit Application"},
        {"to": "REJECTED", "label": "Skip / Not Applying", "is_terminal": True},
    ],
    "SUBMITTED": [
        {"to": "SCREENING", "label": "Under Review / Screening"},
        {"to": "ASSESSMENT", "label": "Assessment / Test Sent"},
        {"to": "INTERVIEWING", "label": "Interview Scheduled"},
        {"to": "GHOSTED", "label": "No Response (Ghosted)", "is_terminal": True},
        {"to": "REJECTED", "label": "Rejected", "is_terminal": True},
    ],
    "SCREENING": [
        {"to": "ASSESSMENT", "label": "Assessment / Test Sent"},
        {"to": "INTERVIEWING", "label": "Interview Scheduled"},
        {"to": "REJECTED", "label": "Rejected After Screening", "is_terminal": True},
        {"to": "GHOSTED", "label": "Ghosted After Screening", "is_terminal": True},
    ],
    "ASSESSMENT": [
        {"to": "INTERVIEWING", "label": "Interview Scheduled"},
        {"to": "REJECTED", "label": "Rejected After Assessment", "is_terminal": True},
        {"to": "GHOSTED", "label": "Ghosted After Assessment", "is_terminal": True},
    ],
    "INTERVIEWING": [
        {"to": "OFFER", "label": "Offer Received", "is_terminal": True},
        {"to": "REJECTED", "label": "Rejected After Interview", "is_terminal": True},
        {"to": "GHOSTED", "label": "Ghosted After Interview", "is_terminal": True},
    ],
}

TERMINAL_STATES = {"OFFER", "REJECTED", "GHOSTED"}


def _title_case(status: str) -> str:
    """Convert SCRAPED -> Scraped etc."""
    return status.title()


def _apply_user_scope(stmt, current_user: dict):
    """Apply user-id scoping to a query/statement unless the user is an admin."""
    if current_user.get("role") != "admin":
        stmt = stmt.filter(Application.userId == current_user["user_id"])
    return stmt


async def _format_application(app: Application, db: AsyncSession) -> dict:
    """Format an Application ORM object as a response dict with title case labels."""
    persona_result = await db.execute(
        select(JobPersona).filter(JobPersona.id == app.personaId)
    )
    persona = persona_result.scalar_one_or_none()

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
        "status": _title_case(app.status),
        "matchScore": app.matchScore,
        "atsScore": app.atsScore,
        "extractedKeywords": app.extractedKeywords,
        "privacyStatus": _title_case(app.privacyStatus),
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


# ============================================================
# Endpoints
# ============================================================

@router.get("")
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by status (e.g., SCRAPED, TAILORED)"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all applications with optional filters."""
    stmt = select(Application)

    # Scope to current user (admins see all)
    stmt = _apply_user_scope(stmt, current_user)

    if status:
        stmt = stmt.filter(Application.status == status.upper())

    if platform:
        stmt = stmt.filter(Application.platform == platform.lower())

    result = await db.execute(stmt.order_by(Application.createdAt.desc()))
    applications = result.scalars().all()

    formatted = []
    for app in applications:
        formatted.append(await _format_application(app, db))
    return formatted


@router.post("")
async def create_application(
    data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new application."""
    # Validate persona
    persona_result = await db.execute(
        select(JobPersona).filter(JobPersona.id == data.persona_id)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{data.persona_id}' not found")

    now = datetime.utcnow()
    keywords = matcher.extract_keywords(data.job_description)
    extracted_keywords = json.dumps(keywords)

    skills = matcher.get_personas_skills_json(persona.skillsJson)
    match_result = matcher.calculate_match_score(data.job_description, skills)
    ats_score = float(matcher.calculate_ats_score(data.job_description))

    application = Application(
        id=uuid.uuid4().hex[:25],
        personaId=data.persona_id,
        userId=current_user["user_id"],
        company=data.company,
        roleTitle=data.role_title,
        jobDescription=data.job_description,
        status=data.status.upper(),
        matchScore=float(match_result["score"]),
        atsScore=ats_score,
        extractedKeywords=extracted_keywords,
        platform=data.platform,
        jobUrl=data.job_url,
        salaryMin=data.salary_min,
        salaryMax=data.salary_max,
        salaryCurrency=data.salary_currency,
        workMode=data.work_mode,
        tenure=data.tenure,
        perks=data.perks,
        location=data.location,
        companySize=data.company_size,
        sourceEmail=data.source_email,
        notes=data.notes,
        createdAt=now,
        updatedAt=now,
    )

    db.add(application)
    await db.commit()
    await db.refresh(application)

    # Audit log
    await _add_audit_log(
        db, application.id, "CREATED", "USER",
        f"Application created for {data.company} - {data.role_title}",
        actor_user_id=current_user["user_id"],
    )

    return await _format_application(application, db)


@router.get("/{app_id}")
async def get_application(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single application by ID."""
    stmt = select(Application).filter(Application.id == app_id)
    stmt = _apply_user_scope(stmt, current_user)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    return await _format_application(app, db)


@router.patch("/{app_id}")
async def update_application(
    app_id: str,
    data: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update an application."""
    stmt = select(Application).filter(Application.id == app_id)
    stmt = _apply_user_scope(stmt, current_user)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    # Map snake_case fields to camelCase columns
    field_mapping = {
        "company": "company",
        "role_title": "roleTitle",
        "job_description": "jobDescription",
        "status": "status",
        "platform": "platform",
        "job_url": "jobUrl",
        "salary_min": "salaryMin",
        "salary_max": "salaryMax",
        "salary_currency": "salaryCurrency",
        "work_mode": "workMode",
        "tenure": "tenure",
        "perks": "perks",
        "location": "location",
        "company_size": "companySize",
        "source_email": "sourceEmail",
        "notes": "notes",
        "applied_date": "appliedDate",
        "privacy_status": "privacyStatus",
        "next_follow_up": "nextFollowUp",
        "follow_up_count": "followUpCount",
        "last_response_at": "lastResponseAt",
        "response_type": "responseType",
        "match_score": "matchScore",
        "ats_score": "atsScore",
        "extracted_keywords": "extractedKeywords",
    }

    update_data = data.model_dump(by_alias=False, exclude_unset=True)
    changes = []

    for py_field, db_col in field_mapping.items():
        if py_field in update_data and update_data[py_field] is not None:
            old_val = getattr(app, db_col)
            new_val = update_data[py_field]
            if old_val != new_val:
                setattr(app, db_col, new_val)
                changes.append(f"{db_col}: {old_val} -> {new_val}")

    app.updatedAt = datetime.utcnow()

    if changes:
        await db.commit()
        await db.refresh(app)
        await _add_audit_log(
            db, app.id, "UPDATED", "USER", "; ".join(changes),
            actor_user_id=current_user["user_id"],
        )

    return await _format_application(app, db)


@router.post("/{app_id}/advance")
async def advance_status(
    app_id: str,
    data: StatusAdvanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Advance application status using FSM rules."""
    stmt = select(Application).filter(Application.id == app_id)
    stmt = _apply_user_scope(stmt, current_user)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    current = app.status.upper()
    target = data.target_status.upper()

    # Check if already terminal
    if current in TERMINAL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Application is in terminal state '{_title_case(current)}' and cannot be advanced.",
        )

    # Check valid transition
    transitions = FSM_TRANSITIONS.get(current, [])
    valid_transition = None
    for t in transitions:
        if t["to"] == target:
            valid_transition = t
            break

    if not valid_transition:
        valid_targets = [t["to"] for t in transitions]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {_title_case(current)} to {_title_case(target)}. "
                   f"Valid targets: {', '.join(_title_case(t) for t in valid_targets)}",
        )

    # Apply transition
    previous = app.status
    app.status = target
    app.updatedAt = datetime.utcnow()

    if target == "SUBMITTED" and not app.appliedDate:
        app.appliedDate = datetime.utcnow()

    await db.commit()
    await db.refresh(app)

    await _add_audit_log(
        db, app.id, "STATUS_CHANGE", "USER",
        f"Status: {_title_case(previous)} -> {_title_case(target)} ({valid_transition['label']})",
        actor_user_id=current_user["user_id"],
    )

    return {
        "applicationId": app.id,
        "previousStatus": _title_case(previous),
        "newStatus": _title_case(target),
        "label": valid_transition["label"],
        "isTerminal": valid_transition.get("is_terminal", False),
    }


@router.delete("/{app_id}")
async def delete_application(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete an application and all related records."""
    stmt = select(Application).filter(Application.id == app_id)
    stmt = _apply_user_scope(stmt, current_user)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    # Delete related records first (already scoped by app_id foreign key)
    await db.execute(delete(AuditLog).where(AuditLog.appId == app_id))
    from models import ResumeVersion, DocumentAnalysis, TrackingCanary
    await db.execute(delete(ResumeVersion).where(ResumeVersion.appId == app_id))
    await db.execute(delete(DocumentAnalysis).where(DocumentAnalysis.appId == app_id))
    await db.execute(delete(TrackingCanary).where(TrackingCanary.appId == app_id))

    db.delete(app)
    await db.commit()

    return {"success": True, "deleted": app_id}


# ============================================================
# Helpers
# ============================================================

async def _add_audit_log(
    db: AsyncSession,
    app_id: str,
    action: str,
    actor: str,
    details: str,
    actor_user_id: Optional[str] = None,
):
    """Add an audit log entry."""
    log = AuditLog(
        id=uuid.uuid4().hex[:25],
        appId=app_id,
        action=action,
        actor=actor,
        details=details,
        timestamp=datetime.utcnow(),
        actorUserId=actor_user_id,
    )
    db.add(log)
    await db.commit()


# ============================================================
# Follow-Up Alerts Endpoint
# ============================================================

@router.get("/follow-ups/alerts")
async def get_follow_up_alerts(
    days_threshold: int = Query(7, description="Minimum days since last follow-up to trigger alert"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get applications that need follow-up attention.
    Returns applications that have been in SUBMITTED, SCREENING, ASSESSMENT, or INTERVIEWING
    states for more than `days_threshold` days without a follow-up.
    """
    now = datetime.now(timezone.utc)
    threshold_ms = int((now.timestamp() - days_threshold * 86400) * 1000)

    # Get active states that need follow-up
    active_states = ["SUBMITTED", "SCREENING", "ASSESSMENT", "INTERVIEWING"]

    # Query applications that need follow-up
    stmt = select(Application).filter(
        Application.status.in_(active_states)
    )

    # Scope to current user (admins see all)
    stmt = _apply_user_scope(stmt, current_user)

    result = await db.execute(stmt.order_by(Application.createdAt.desc()))
    applications = result.scalars().all()

    alerts = []
    for app in applications:
        # Calculate days since applied
        if app.appliedDate:
            if hasattr(app.appliedDate, 'timestamp'):
                applied_ms = int(app.appliedDate.timestamp() * 1000)
            else:
                applied_ms = int(app.appliedDate)
            days_since = int((now.timestamp() * 1000 - applied_ms) / 86400000)
        elif app.createdAt:
            if hasattr(app.createdAt, 'timestamp'):
                created_ms = int(app.createdAt.timestamp() * 1000)
            else:
                created_ms = int(app.createdAt)
            days_since = int((now.timestamp() * 1000 - created_ms) / 86400000)
        else:
            continue

        # Check if it's past the threshold
        if days_since < days_threshold:
            continue

        # Calculate days since last follow-up
        days_since_followup = None
        if app.lastFollowUp:
            if hasattr(app.lastFollowUp, 'timestamp'):
                followup_ms = int(app.lastFollowUp.timestamp() * 1000)
            else:
                followup_ms = int(app.lastFollowUp)
            days_since_followup = int((now.timestamp() * 1000 - followup_ms) / 86400000)

        # Skip if followed up recently
        if days_since_followup is not None and days_since_followup < days_threshold:
            continue

        # Determine urgency
        if days_since >= 14:
            urgency = "High"
        elif days_since >= 10:
            urgency = "Medium"
        else:
            urgency = "Low"

        alerts.append({
            "applicationId": app.id,
            "company": app.company,
            "roleTitle": app.roleTitle,
            "status": _title_case(app.status),
            "platform": app.platform,
            "daysSinceApplied": days_since,
            "daysSinceLastFollowUp": days_since_followup,
            "followUpCount": app.followUpCount,
            "urgency": urgency,
            "appliedDate": app.appliedDate.isoformat() if app.appliedDate else None,
            "jobUrl": app.jobUrl,
            "nextFollowUp": app.nextFollowUp.isoformat() if app.nextFollowUp else None,
        })

    return {
        "alerts": alerts,
        "total": len(alerts),
        "thresholdDays": days_threshold,
    }
