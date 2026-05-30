"""
FastAPI router for resume management.
Endpoints:
  POST /api/resume/upload         - Upload and analyze resume (docx/pdf/txt)
  GET  /api/resume/versions/{app_id} - Get resume version history
  POST /api/resume/customize       - Customize resume for a job (returns .docx bytes)
  POST /api/resume/template        - Upload custom .docx template
  GET  /api/resume/templates       - List available templates

Implements basic text extraction, ATS scoring, skill detection, section detection.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
import io
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application, DocumentAnalysis, ResumeVersion, JobPersona
from services import matcher
from services.resume_customizer import resume_customizer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resume", tags=["resume"])

UPLOAD_DIR = "/home/z/my-project/public/uploads"


def _is_admin(current_user: dict) -> bool:
    return current_user.get("role") == "admin"


def _sanitize_filename(filename: str) -> str:
    """Strip directory components and dangerous characters from filenames.

    Prevents path traversal attacks (e.g. '../../../etc/passwd').
    Only keeps the base filename and replaces non-alphanumeric chars
    (except dots and hyphens) with underscores.
    """
    # Take only the basename (no directory traversal)
    base = os.path.basename(filename)
    # Replace anything that isn't alphanumeric, dot, hyphen, or underscore
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in base)
    return safe


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _extract_text_txt(file_path: str) -> str:
    """Extract text from a .txt file."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_text_docx(file_path: str) -> str:
    """Extract text from a .docx file using mammoth."""
    try:
        import mammoth
        with open(file_path, "rb") as f:
            result = mammoth.extract_raw_text(f)
            return result.value
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="mammoth package is required for .docx parsing. Install with: pip install mammoth",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse .docx file: {str(e)}")


def _is_valid_extracted_text(text: str, min_words: int = 20) -> bool:
    """Check if extracted text is actual readable content, not raw PDF binary."""
    if not text or len(text.strip()) < 50:
        return False
    # Raw PDF binary starts with %PDF
    if text.strip().startswith("%PDF"):
        return False
    # Check if it has enough alphabetic characters (binary has mostly symbols)
    alpha_count = sum(1 for c in text if c.isalpha() or c.isspace())
    ratio = alpha_count / max(1, len(text))
    if ratio < 0.5:
        return False
    # Check for minimum word count of real words
    words = [w for w in text.split() if any(c.isalpha() for c in w)]
    return len(words) >= min_words


def _extract_text_pdf(file_path: str) -> tuple[str, bool]:
    """
    Extract text from PDF with cascading fallback:
      1. PyPDF2 (fast, works for text-based PDFs)
      2. pdfminer (better text extraction)
      3. OCR via pdf2image + pytesseract (for scanned/image-based PDFs)
    
    Returns (extracted_text, ocr_used).
    """
    # Attempt 1: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        if _is_valid_extracted_text(text):
            return text, False
    except Exception:
        pass

    # Attempt 2: pdfminer
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        if _is_valid_extracted_text(text):
            return text, False
    except Exception:
        pass

    # Attempt 3: OCR via pdf2image + pytesseract
    try:
        from pdf2image import convert_from_path
        import pytesseract
        import os
        os.environ['PATH'] = '/usr/bin:/home/z/.local/bin:' + os.environ.get('PATH', '')

        images = convert_from_path(file_path, dpi=300)
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
        text = text.strip()

        if _is_valid_extracted_text(text):
            logger.info(f"PDF text extracted via OCR ({len(images)} pages, {len(text)} chars)")
            return text, True
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")

    raise HTTPException(
        status_code=500,
        detail="Failed to extract text from PDF. The file may be corrupted or image-based with no readable text.",
    )


def _extract_text(file_path: str, file_type: str) -> tuple[str, bool]:
    """
    Extract text from file based on type.
    Returns (extracted_text, ocr_used) tuple.
    ocr_used is True only when OCR fallback was used for PDFs.
    """
    if file_type == "txt" or file_type == "text/plain":
        return _extract_text_txt(file_path), False
    elif file_type == "docx" or file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_text_docx(file_path), False
    elif file_type == "pdf" or file_type == "application/pdf":
        return _extract_text_pdf(file_path)
    else:
        return _extract_text_txt(file_path), False


def _detect_sections(text: str) -> list[str]:
    """Detect resume sections in text."""
    text_lower = text.lower()
    standard_sections = [
        "experience", "education", "skills", "summary",
        "objective", "projects", "certifications", "contact",
        "references", "languages", "achievements", "publications",
        "volunteer", "hobbies", "interests",
    ]
    detected = []
    for section in standard_sections:
        # Check for common section header patterns
        patterns = [
            section,
            section.upper(),
            section.title(),
            section.replace(" ", "-"),
            section.replace(" ", "_"),
        ]
        for p in patterns:
            if p in text:
                detected.append(section.title())
                break
    return sorted(set(detected))


def _detect_contact_info(text: str) -> dict:
    """Extract basic contact info from resume text."""
    import re

    contact = {}

    # Email
    email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    if email_match:
        contact["email"] = email_match.group(0)

    # Phone
    phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    if phone_match:
        contact["phone"] = phone_match.group(0).strip()

    # LinkedIn
    linkedin_match = re.search(r"linkedin\.com/in/[a-zA-Z0-9\-_]+", text, re.IGNORECASE)
    if linkedin_match:
        contact["linkedin"] = linkedin_match.group(0)

    # GitHub
    github_match = re.search(r"github\.com/[a-zA-Z0-9\-_]+", text, re.IGNORECASE)
    if github_match:
        contact["github"] = github_match.group(0)

    return contact


def _generate_issues(text: str, word_count: int, sections: list[str]) -> list[str]:
    """Generate a list of issues found in the resume."""
    issues = []

    if word_count < 100:
        issues.append("Resume is very short (under 100 words). Consider adding more detail.")
    if word_count > 1500:
        issues.append("Resume is very long (over 1500 words). Consider trimming to 1-2 pages.")

    if "skills" not in [s.lower() for s in sections]:
        issues.append("No 'Skills' section detected. Add one for better ATS matching.")

    if "experience" not in [s.lower() for s in sections]:
        issues.append("No 'Experience' section detected.")

    if "education" not in [s.lower() for s in sections]:
        issues.append("No 'Education' section detected.")

    if word_count > 0 and not any(c in text for c in ["•", "-", "*", "→"]):
        issues.append("No bullet points detected. Use bullets to improve readability.")

    return issues


def _generate_recommendations(sections: list[str], ats_score: int) -> list[str]:
    """Generate improvement recommendations."""
    recs = []

    if ats_score < 50:
        recs.append("Improve ATS compatibility by adding standard section headers and keywords.")

    if "certifications" not in [s.lower() for s in sections]:
        recs.append("Consider adding a 'Certifications' section to highlight professional credentials.")

    if "projects" not in [s.lower() for s in sections]:
        recs.append("Add a 'Projects' section with quantifiable achievements and metrics.")

    if "achievements" not in [s.lower() for s in sections]:
        recs.append("Include an 'Achievements' section to stand out from other candidates.")

    recs.append("Use action verbs (Built, Led, Designed, Optimized) and quantify results where possible.")

    return recs


@router.post("/upload")
async def upload_resume(
    app_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload and analyze a resume file (docx/pdf/txt)."""
    # Validate application
    result = await db.execute(select(Application).filter(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this application")

    _ensure_upload_dir()

    # Determine file extension — strictly whitelist allowed types
    _ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
    filename = file.filename or "resume.txt"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '.{ext}'. Allowed: .pdf, .docx, .txt",
        )

    # Enforce file size limit (5 MB max for resumes)
    _MAX_UPLOAD_BYTES = 5 * 1024 * 1024
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content)} bytes). Maximum allowed: 5 MB.",
        )
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    file_type_map = {
        "txt": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    file_type = file_type_map[ext]

    # Save file (safe filename: UUID prefix prevents path traversal)
    file_id = uuid.uuid4().hex[:10]
    safe_filename = f"{file_id}_{_sanitize_filename(filename)}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    content_hash = hashlib.sha256(content).hexdigest()

    # Determine version
    version_result = await db.execute(
        select(ResumeVersion)
        .filter(ResumeVersion.appId == app_id)
        .order_by(ResumeVersion.version.desc())
    )
    last_version = version_result.scalar_one_or_none()
    next_version = (last_version.version + 1) if last_version else 1

    # Extract text
    ocr_used = False
    try:
        result = _extract_text(file_path, file_type)
        if isinstance(result, tuple):
            extracted_text, ocr_used = result
        else:
            extracted_text = result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract text: {str(e)}")

    # Analyze
    word_count = len(extracted_text.split())
    detected_skills = matcher.extract_skills_from_text(extracted_text)
    detected_sections = _detect_sections(extracted_text)
    contact_info = _detect_contact_info(extracted_text)
    ats_score = matcher.calculate_ats_score(extracted_text)
    issues = _generate_issues(extracted_text, word_count, detected_sections)
    recommendations = _generate_recommendations(detected_sections, ats_score)

    now = datetime.utcnow()

    # Create ResumeVersion
    version = ResumeVersion(
        id=uuid.uuid4().hex[:25],
        appId=app_id,
        version=next_version,
        filePath=file_path,
        contentHash=content_hash,
        createdAt=now,
    )
    db.add(version)

    # Create/update DocumentAnalysis
    analysis_result = await db.execute(
        select(DocumentAnalysis).filter(DocumentAnalysis.appId == app_id)
    )
    existing_analysis = analysis_result.scalar_one_or_none()
    if existing_analysis:
        existing_analysis.fileName = filename
        existing_analysis.fileType = file_type
        existing_analysis.fileSize = len(content)
        existing_analysis.extractedText = extracted_text
        existing_analysis.contactInfo = json.dumps(contact_info)
        existing_analysis.detectedSkills = json.dumps(detected_skills)
        existing_analysis.detectedSections = json.dumps(detected_sections)
        existing_analysis.atsScore = float(ats_score)
        existing_analysis.wordCount = word_count
        existing_analysis.issues = json.dumps(issues)
        existing_analysis.recommendations = json.dumps(recommendations)
        existing_analysis.ocrUsed = ocr_used
        existing_analysis.analyzedAt = now
    else:
        analysis = DocumentAnalysis(
            id=uuid.uuid4().hex[:25],
            appId=app_id,
            fileName=filename,
            fileType=file_type,
            fileSize=len(content),
            extractedText=extracted_text,
            contactInfo=json.dumps(contact_info),
            detectedSkills=json.dumps(detected_skills),
            detectedSections=json.dumps(detected_sections),
            atsScore=float(ats_score),
            wordCount=word_count,
            issues=json.dumps(issues),
            recommendations=json.dumps(recommendations),
            ocrUsed=ocr_used,
            analyzedAt=now,
        )
        db.add(analysis)

    await db.commit()

    return {
        "success": True,
        "upload": {
            "fileName": filename,
            "fileType": file_type,
            "fileSize": len(content),
            "contentHash": content_hash,
            "filePath": file_path,
            "version": next_version,
        },
        "analysis": {
            "wordCount": word_count,
            "atsScore": ats_score,
            "ocrUsed": False,
            "detectedSections": detected_sections,
            "contactInfo": contact_info,
            "detectedSkills": detected_skills,
            "issues": issues,
            "recommendations": recommendations,
        },
    }


@router.get("/versions/{app_id}")
async def get_resume_versions(app_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Get resume version history for an application."""
    result = await db.execute(select(Application).filter(Application.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this application")

    versions_result = await db.execute(
        select(ResumeVersion)
        .filter(ResumeVersion.appId == app_id)
        .order_by(ResumeVersion.version.desc())
    )
    versions = versions_result.scalars().all()

    return [
        {
            "id": v.id,
            "appId": v.appId,
            "version": v.version,
            "filePath": v.filePath,
            "contentHash": v.contentHash,
            "createdAt": v.createdAt.isoformat() if v.createdAt else None,
        }
        for v in versions
    ]


# ============================================================
# Resume Customization Schemas
# ============================================================

class CustomizeResumeRequest(BaseModel):
    app_id: str = Field(..., alias="appId", description="Application ID to generate resume for")
    template_name: Optional[str] = Field(None, alias="templateName", description="Custom template name (optional, uses default)")
    persona_data: Optional[dict[str, Any]] = Field(None, alias="personaData", description="Override persona data")

    model_config = ConfigDict(populate_by_name=True)


class ExperienceEntry(BaseModel):
    title: str
    company: str
    bullets: list[str]
    dates: str


class EducationEntry(BaseModel):
    degree: str
    institution: str
    dates: Optional[str] = ""


# ============================================================
# Resume Customization Endpoints
# ============================================================

@router.post("/customize")
async def customize_resume(request: CustomizeResumeRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Customize a resume for a specific job application. Returns .docx file bytes."""
    # Get application
    app_result = await db.execute(select(Application).filter(Application.id == request.app_id))
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{request.app_id}' not found")

    # Ownership check
    if not _is_admin(current_user) and app.userId != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You do not have access to this application")

    # Get persona
    persona_result = await db.execute(select(JobPersona).filter(JobPersona.id == app.personaId))
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{app.personaId}' not found")

    # Build persona data from DB
    if request.persona_data:
        persona_data = request.persona_data
    else:
        # Parse persona skills
        try:
            skills = json.loads(persona.skillsJson) if persona.skillsJson else []
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",") if s.strip()]
        except (json.JSONDecodeError, TypeError):
            skills = [s.strip() for s in (persona.skillsJson or "").split(",") if s.strip()]

        # Parse master bullets into experience entries
        try:
            master_bullets = json.loads(persona.masterBullets) if persona.masterBullets else []
        except (json.JSONDecodeError, TypeError):
            master_bullets = [b.strip() for b in (persona.masterBullets or "").split("\n") if b.strip()]

        # Build experience entries from master bullets (group by lines)
        experience = []
        current_entry = None
        for bullet in master_bullets:
            if isinstance(bullet, dict):
                experience.append(bullet)
            elif isinstance(bullet, str):
                # Simple heuristic: treat each line as a bullet for a single experience entry
                if not current_entry:
                    current_entry = {
                        "title": app.roleTitle or "Software Engineer",
                        "company": "Previous Company",
                        "bullets": [],
                        "dates": "2022 - Present",
                    }
                current_entry["bullets"].append(bullet)

        if current_entry and current_entry["bullets"] and not any(
            e["title"] == current_entry["title"] for e in experience
        ):
            experience.append(current_entry)

        if not experience:
            experience = [{
                "title": app.roleTitle or "Software Engineer",
                "company": "Previous Company",
                "bullets": master_bullets if isinstance(master_bullets, list) else [str(master_bullets)],
                "dates": "Recent",
            }]

        persona_data = {
            "name": persona.name,
            "email": "",
            "phone": "",
            "linkedin": "",
            "summary": persona.summaryTemplate or f"Experienced {app.roleTitle or 'professional'} with expertise in {', '.join(skills[:5])}.",
            "skills": skills,
            "experience": experience,
            "education": [{"degree": "Bachelor's Degree", "institution": "University", "dates": ""}],
            "certifications": [],
        }

    # Build job data
    try:
        required_skills = []
        if app.extractedKeywords:
            keywords = json.loads(app.extractedKeywords)
            if isinstance(keywords, list):
                required_skills = keywords[:15]
    except (json.JSONDecodeError, TypeError):
        required_skills = []

    job_data = {
        "title": app.roleTitle,
        "company": app.company,
        "required_skills": required_skills,
        "description": app.jobDescription,
    }

    # Select template
    template_path = None
    if request.template_name:
        templates = resume_customizer.list_templates()
        for t in templates:
            if t["type"] == "custom" and request.template_name.lower() in t["name"].lower():
                template_path = t["path"]
                break

    # Generate customized resume
    try:
        docx_bytes = resume_customizer.customize_resume(
            template_path=template_path,
            persona_data=persona_data,
            job_data=job_data,
        )
    except Exception as e:
        logger.error(f"Resume customization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume customization failed: {str(e)}")

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=resume_{app.company.replace(' ', '_')}.docx"
        },
    )


@router.post("/template")
async def upload_template(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Upload a custom .docx resume template."""
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are accepted as templates.")

    content = await file.read()

    # Validate it's a valid docx (try to open it)
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        # Just verify it has paragraphs
        if not doc.paragraphs:
            raise HTTPException(status_code=400, detail="The uploaded .docx file appears to be empty.")
    except Exception as e:
        if "docx" in str(e).lower() or "zip" in str(e).lower():
            raise HTTPException(status_code=400, detail="Invalid .docx file format.")
        raise HTTPException(status_code=400, detail=f"Could not read .docx file: {str(e)}")

    template_name = name or file.filename.replace(".docx", "")
    path = resume_customizer.save_custom_template(content, template_name)

    return {
        "success": True,
        "templateName": template_name,
        "path": path,
    }


@router.get("/templates")
def list_templates(current_user: dict = Depends(get_current_user)):
    """List all available resume templates."""
    templates = resume_customizer.list_templates()
    return {
        "templates": [
            {
                "name": t["name"],
                "type": t["type"],
            }
            for t in templates
        ],
    }
