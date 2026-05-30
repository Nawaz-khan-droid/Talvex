"""
FastAPI router for persona management.
Endpoints:
  GET    /api/personas - List all personas
  POST   /api/personas - Create persona
  GET    /api/personas/{id} - Get persona
  PATCH  /api/personas/{id} - Update persona
  DELETE /api/personas/{id} - Delete persona
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import get_db
from models import Application, JobPersona
from schemas import PersonaCreate, PersonaUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/personas", tags=["personas"])


def _user_filter(stmt, user_id: str):
    """Apply a userId filter to an existing statement.

    Returns the statement unchanged if user_id is None (admin override).
    """
    if user_id is not None:
        return stmt.filter(JobPersona.userId == user_id)
    return stmt


def _effective_user_id(current_user: dict):
    """Return the user_id to filter by, or None if the user is an admin.

    Admins bypass ownership checks and can see all personas.
    """
    if current_user.get("role") == "admin":
        return None
    return current_user["user_id"]


async def _format_persona(persona: JobPersona, db: AsyncSession) -> dict:
    """Format a JobPersona ORM object as a response dict."""
    app_count = (await db.execute(
        select(func.count(Application.id)).filter(Application.personaId == persona.id)
    )).scalar()
    return {
        "id": persona.id,
        "name": persona.name,
        "skillsJson": persona.skillsJson,
        "masterBullets": persona.masterBullets,
        "summaryTemplate": persona.summaryTemplate,
        "createdAt": persona.createdAt.isoformat() if persona.createdAt else None,
        "updatedAt": persona.updatedAt.isoformat() if persona.updatedAt else None,
        "applicationCount": app_count,
    }


@router.get("")
async def list_personas(
    db: AsyncSession = Depends(get_db),
    current_user: dict | None = Depends(get_optional_user),
):
    """List all personas belonging to the current user.

    Admin users can see all personas across all users.
    """
    if not current_user:
        return []
    uid = _effective_user_id(current_user)
    stmt = select(JobPersona)
    stmt = _user_filter(stmt, uid)
    result = await db.execute(stmt.order_by(JobPersona.createdAt.desc()))
    personas = result.scalars().all()

    formatted = []
    for p in personas:
        formatted.append(await _format_persona(p, db))
    return formatted


@router.post("")
async def create_persona(
    data: PersonaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new persona owned by the current user."""
    uid = current_user["user_id"]

    # Check for duplicate name within the same user
    existing_result = await db.execute(
        select(JobPersona).filter(JobPersona.name == data.name, JobPersona.userId == uid)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Persona with name '{data.name}' already exists")

    now = datetime.utcnow()
    persona = JobPersona(
        id=uuid.uuid4().hex[:25],
        name=data.name,
        skillsJson=data.skills_json,
        masterBullets=data.master_bullets,
        summaryTemplate=data.summary_template,
        userId=uid,
        createdAt=now,
        updatedAt=now,
    )

    db.add(persona)
    await db.commit()
    await db.refresh(persona)

    return await _format_persona(persona, db)


@router.get("/{persona_id}")
async def get_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single persona by ID.

    Non-admin users can only retrieve personas they own.
    """
    uid = _effective_user_id(current_user)
    stmt = select(JobPersona).filter(JobPersona.id == persona_id)
    stmt = _user_filter(stmt, uid)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")
    return await _format_persona(persona, db)


@router.patch("/{persona_id}")
async def update_persona(
    persona_id: str,
    data: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a persona.

    Non-admin users can only update personas they own.
    """
    uid = _effective_user_id(current_user)
    stmt = select(JobPersona).filter(JobPersona.id == persona_id)
    stmt = _user_filter(stmt, uid)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")

    update_data = data.model_dump(by_alias=False, exclude_unset=True)

    # Map fields to DB columns
    field_map = {
        "name": "name",
        "skills_json": "skillsJson",
        "master_bullets": "masterBullets",
        "summary_template": "summaryTemplate",
    }

    for py_field, db_col in field_map.items():
        if py_field in update_data and update_data[py_field] is not None:
            setattr(persona, db_col, update_data[py_field])

    persona.updatedAt = datetime.utcnow()
    await db.commit()
    await db.refresh(persona)

    return await _format_persona(persona, db)


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a persona (only if no applications reference it).

    Non-admin users can only delete personas they own.
    """
    uid = _effective_user_id(current_user)
    stmt = select(JobPersona).filter(JobPersona.id == persona_id)
    stmt = _user_filter(stmt, uid)
    result = await db.execute(stmt)
    persona = result.scalar_one_or_none()

    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")

    app_count = (await db.execute(
        select(func.count(Application.id)).filter(Application.personaId == persona_id)
    )).scalar()
    if app_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete persona '{persona.name}' - it has {app_count} linked applications.",
        )

    db.delete(persona)
    await db.commit()

    return {"success": True, "deleted": persona_id}
