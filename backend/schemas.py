"""
Pydantic v2 schemas for TALVEX API request/response serialization.
All field names use snake_case (Python convention).
Configured for ORM mode to work with SQLAlchemy models.
"""

from datetime import datetime
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Shared / Utility
# ============================================================

def _title_case_status(status: Optional[str]) -> Optional[str]:
    """Convert SCRAPED -> Scraped etc."""
    if not status:
        return status
    return status.title()


_PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|\[INST\]|</s>", re.IGNORECASE),
]


def detect_prompt_injection_patterns(text: str) -> list[str]:
    if not text:
        return []
    return [pattern.pattern for pattern in _PROMPT_INJECTION_PATTERNS if pattern.search(text)]


def sanitize_and_validate_llm_text(text: str, field_name: str = "input") -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    matches = detect_prompt_injection_patterns(normalized)
    if matches:
        raise ValueError(
            f"{field_name} contains suspicious prompt-injection patterns: {', '.join(matches[:3])}"
        )
    return normalized


# ============================================================
# Persona Schemas
# ============================================================

class PersonaCreate(BaseModel):
    name: str
    skills_json: str = Field(..., alias="skillsJson")
    master_bullets: str = Field(..., alias="masterBullets")
    summary_template: Optional[str] = Field(None, alias="summaryTemplate")

    model_config = ConfigDict(populate_by_name=True)


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    skills_json: Optional[str] = Field(None, alias="skillsJson")
    master_bullets: Optional[str] = Field(None, alias="masterBullets")
    summary_template: Optional[str] = Field(None, alias="summaryTemplate")

    model_config = ConfigDict(populate_by_name=True)


class PersonaResponse(BaseModel):
    id: str
    name: str
    skills_json: str = Field(alias="skillsJson")
    master_bullets: str = Field(alias="masterBullets")
    summary_template: Optional[str] = Field(None, alias="summaryTemplate")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    application_count: int = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# Application Schemas
# ============================================================

class ApplicationCreate(BaseModel):
    persona_id: str = Field(..., alias="personaId")
    company: str
    role_title: str = Field(..., alias="roleTitle")
    job_description: str = Field(..., alias="jobDescription")
    status: str = "SCRAPED"
    platform: str = "manual"
    job_url: Optional[str] = Field(None, alias="jobUrl")
    salary_min: Optional[int] = Field(None, alias="salaryMin")
    salary_max: Optional[int] = Field(None, alias="salaryMax")
    salary_currency: str = Field("INR", alias="salaryCurrency")
    work_mode: Optional[str] = Field(None, alias="workMode")
    tenure: Optional[str] = None
    perks: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = Field(None, alias="companySize")
    source_email: Optional[str] = Field(None, alias="sourceEmail")
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role_title: Optional[str] = Field(None, alias="roleTitle")
    job_description: Optional[str] = Field(None, alias="jobDescription")
    status: Optional[str] = None
    platform: Optional[str] = None
    job_url: Optional[str] = Field(None, alias="jobUrl")
    salary_min: Optional[int] = Field(None, alias="salaryMin")
    salary_max: Optional[int] = Field(None, alias="salaryMax")
    salary_currency: Optional[str] = Field(None, alias="salaryCurrency")
    work_mode: Optional[str] = Field(None, alias="workMode")
    tenure: Optional[str] = None
    perks: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = Field(None, alias="companySize")
    source_email: Optional[str] = Field(None, alias="sourceEmail")
    notes: Optional[str] = None
    applied_date: Optional[datetime] = Field(None, alias="appliedDate")
    privacy_status: Optional[str] = Field(None, alias="privacyStatus")
    next_follow_up: Optional[datetime] = Field(None, alias="nextFollowUp")
    follow_up_count: Optional[int] = Field(None, alias="followUpCount")
    last_response_at: Optional[datetime] = Field(None, alias="lastResponseAt")
    response_type: Optional[str] = Field(None, alias="responseType")
    match_score: Optional[float] = Field(None, alias="matchScore")
    ats_score: Optional[float] = Field(None, alias="atsScore")
    extracted_keywords: Optional[str] = Field(None, alias="extractedKeywords")

    model_config = ConfigDict(populate_by_name=True)


class ApplicationResponse(BaseModel):
    id: str
    persona_id: str = Field(alias="personaId")
    company: str
    role_title: str = Field(alias="roleTitle")
    job_description: str = Field(alias="jobDescription")
    status: str
    match_score: float = Field(alias="matchScore")
    ats_score: float = Field(alias="atsScore")
    extracted_keywords: Optional[str] = Field(None, alias="extractedKeywords")
    privacy_status: str = Field(alias="privacyStatus")
    applied_date: Optional[datetime] = Field(None, alias="appliedDate")
    last_follow_up: Optional[datetime] = Field(None, alias="lastFollowUp")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    platform: str
    job_url: Optional[str] = Field(None, alias="jobUrl")
    salary_min: Optional[int] = Field(None, alias="salaryMin")
    salary_max: Optional[int] = Field(None, alias="salaryMax")
    salary_currency: str = Field(alias="salaryCurrency")
    work_mode: Optional[str] = Field(None, alias="workMode")
    tenure: Optional[str] = None
    perks: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = Field(None, alias="companySize")
    source_email: Optional[str] = Field(None, alias="sourceEmail")
    next_follow_up: Optional[datetime] = Field(None, alias="nextFollowUp")
    follow_up_count: int = Field(alias="followUpCount")
    last_response_at: Optional[datetime] = Field(None, alias="lastResponseAt")
    response_type: Optional[str] = Field(None, alias="responseType")
    notes: Optional[str] = None
    persona: Optional[PersonaResponse] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# Canary Schemas
# ============================================================

class CanaryCreate(BaseModel):
    app_id: str = Field(..., alias="appId")
    canary_email: str = Field(..., alias="canaryEmail")
    tracking_slug: Optional[str] = Field(None, alias="trackingSlug")

    model_config = ConfigDict(populate_by_name=True)


class CanaryUpdate(BaseModel):
    leak_flagged: bool = Field(..., alias="leakFlagged")
    leak_details: Optional[str] = Field(None, alias="leakDetails")

    model_config = ConfigDict(populate_by_name=True)


class CanaryResponse(BaseModel):
    id: str
    app_id: str = Field(alias="appId")
    canary_email: str = Field(alias="canaryEmail")
    tracking_slug: Optional[str] = Field(None, alias="trackingSlug")
    leak_flagged: bool = Field(alias="leakFlagged")
    leak_details: Optional[str] = Field(None, alias="leakDetails")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# Resume / Document Analysis Schemas
# ============================================================

class ResumeVersionResponse(BaseModel):
    id: str
    app_id: str = Field(alias="appId")
    version: int
    file_path: str = Field(alias="filePath")
    content_hash: str = Field(alias="contentHash")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentAnalysisResponse(BaseModel):
    id: str
    app_id: str = Field(alias="appId")
    file_name: str = Field(alias="fileName")
    file_type: str = Field(alias="fileType")
    file_size: int = Field(alias="fileSize")
    extracted_text: str = Field(alias="extractedText")
    contact_info: Optional[str] = Field(None, alias="contactInfo")
    detected_skills: Optional[str] = Field(None, alias="detectedSkills")
    detected_sections: Optional[str] = Field(None, alias="detectedSections")
    ats_score: float = Field(alias="atsScore")
    word_count: int = Field(alias="wordCount")
    issues: Optional[str] = Field(None, alias="issues")
    recommendations: Optional[str] = Field(None, alias="recommendations")
    ocr_used: bool = Field(alias="ocrUsed")
    analyzed_at: datetime = Field(alias="analyzedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# Audit Log Schemas
# ============================================================

class AuditLogResponse(BaseModel):
    id: str
    app_id: Optional[str] = Field(None, alias="appId")
    action: str
    actor: str
    actor_user_id: Optional[str] = Field(None, alias="actorUserId")
    details: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# JSearch API Schemas
# ============================================================

class JobSearchRequest(BaseModel):
    query: str
    country: str = "us"
    num_pages: int = Field(1, ge=1, le=10, alias="numPages")
    date_posted: Optional[str] = Field(None, alias="datePosted")

    model_config = ConfigDict(populate_by_name=True)


class JobIngestRequest(BaseModel):
    app_id: Optional[str] = Field(None, alias="appId")
    persona_id: Optional[str] = Field(None, alias="personaId")
    company: str
    role_title: str = Field(..., alias="roleTitle")
    job_description: str = Field(..., alias="jobDescription")
    job_url: Optional[str] = Field(None, alias="jobUrl")
    platform: str = "manual"
    location: Optional[str] = None
    salary_min: Optional[int] = Field(None, alias="salaryMin")
    salary_max: Optional[int] = Field(None, alias="salaryMax")
    salary_currency: str = Field("INR", alias="salaryCurrency")
    work_mode: Optional[str] = Field(None, alias="workMode")
    tenure: Optional[str] = None
    perks: Optional[str] = None
    company_size: Optional[str] = Field(None, alias="companySize")

    model_config = ConfigDict(populate_by_name=True)


class SalaryEstimateRequest(BaseModel):
    job_title: str = Field(..., alias="jobTitle")
    location: str


class JobSearchResult(BaseModel):
    job_id: str = Field(alias="jobId")
    employer_name: str = Field(alias="employerName")
    job_title: str = Field(alias="jobTitle")
    job_description: str = Field(alias="jobDescription")
    job_city: Optional[str] = Field(None, alias="jobCity")
    job_state: Optional[str] = Field(None, alias="jobState")
    job_country: Optional[str] = Field(None, alias="jobCountry")
    job_apply_link: Optional[str] = Field(None, alias="jobApplyLink")
    job_min_salary: Optional[float] = Field(None, alias="jobMinSalary")
    job_max_salary: Optional[float] = Field(None, alias="jobMaxSalary")
    job_salary_currency: Optional[str] = Field(None, alias="jobSalaryCurrency")
    job_posted_at_datetime_utc: Optional[str] = Field(None, alias="jobPostedAtDatetimeUTC")
    employer_logo: Optional[str] = Field(None, alias="employerLogo")
    job_employment_type: Optional[str] = Field(None, alias="jobEmploymentType")
    job_is_remote: Optional[bool] = Field(None, alias="jobIsRemote")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class JSearchResponse(BaseModel):
    results: list[dict[str, Any]]
    total_count: int = Field(alias="totalCount")
    page_number: int = Field(alias="pageNumber")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Analytics Schemas
# ============================================================

class FunnelData(BaseModel):
    label: str
    count: int


class PlatformStat(BaseModel):
    platform: str
    count: int
    avg_score: float


class SalaryTrend(BaseModel):
    range_label: str
    count: int
    avg_min: Optional[float] = None
    avg_max: Optional[float] = None


class AnalyticsResponse(BaseModel):
    funnel: list[FunnelData]
    total_applications: int
    total_personas: int
    overall_match_rate: float
    platform_breakdown: list[PlatformStat]
    salary_trends: list[SalaryTrend]
    leak_alerts: int
    response_rate: float


# ============================================================
# Recommendations Schemas
# ============================================================

class SkillGapItem(BaseModel):
    skill: str
    category: str
    priority: str
    market_demand: int
    learning_path: str
    estimated_weeks: int


class SkillGapResponse(BaseModel):
    persona_id: str = Field(alias="personaId")
    persona_name: str = Field(alias="personaName")
    current_skills: list[str] = Field(alias="currentSkills")
    skill_count: int = Field(alias="skillCount")
    gaps: list[SkillGapItem]


class TradeRecommendation(BaseModel):
    target_role: str = Field(alias="targetRole")
    alignment_score: int = Field(alias="alignmentScore")
    missing_skills: list[str] = Field(alias="missingSkills")
    salary_range: dict[str, int] = Field(alias="salaryRange")
    action_steps: list[str] = Field(alias="actionSteps")


class TradesResponse(BaseModel):
    recommendations: list[TradeRecommendation]


class PipelineTelemetry(BaseModel):
    total_applications: int = Field(alias="totalApplications")
    average_match_score: float = Field(alias="averageMatchScore")
    high_match_count: int = Field(alias="highMatchCount")
    status_breakdown: dict[str, int] = Field(alias="statusBreakdown")
    top_target_roles: list[dict[str, Any]] = Field(alias="topTargetRoles")


class FollowUpTemplate(BaseModel):
    template: str
    urgency: str
    days_since_applied: int = Field(alias="daysSinceApplied")
    follow_up_count: int = Field(alias="followUpCount")


# ============================================================
# FSM / Status Advance
# ============================================================

class StatusAdvanceRequest(BaseModel):
    target_status: str = Field(..., alias="targetStatus")

    model_config = ConfigDict(populate_by_name=True)


class StatusAdvanceResponse(BaseModel):
    application_id: str = Field(alias="applicationId")
    previous_status: str = Field(alias="previousStatus")
    new_status: str = Field(alias="newStatus")
    label: str
    is_terminal: bool = Field(alias="isTerminal")


# ============================================================
# Email Parse Schemas
# ============================================================

class EmailParseRequest(BaseModel):
    email_body: str = Field(..., alias="emailBody")
    persona_id: Optional[str] = Field(None, alias="personaId")

    model_config = ConfigDict(populate_by_name=True)


class EmailParseResponse(BaseModel):
    success: bool
    application_id: Optional[str] = Field(None, alias="applicationId")
    extracted_fields: dict[str, Any]


# ============================================================
# Auth Schemas
# ============================================================

class UserRegister(BaseModel):
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


class UserLogin(BaseModel):
    email: str
    password: str


class UserChangePassword(BaseModel):
    current_password: str = Field(..., alias="currentPassword")
    new_password: str = Field(..., min_length=8, max_length=128, alias="newPassword")

    model_config = ConfigDict(populate_by_name=True)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = Field(None, alias="displayName")
    role: str
    is_active: bool = Field(alias="isActive")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserAdminResponse(UserResponse):
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserUpdateByAdmin(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100, alias="displayName")
    role: Optional[str] = Field(None, pattern=r"^(user|admin)$")
    is_active: Optional[bool] = Field(None, alias="isActive")

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Settings Schemas (BYOK)
# ============================================================

class SettingsUpdate(BaseModel):
    """API keys are sent here for server-side encrypted storage."""
    openrouter_key: Optional[str] = Field(None, alias="openRouterKey")
    tavily_key: Optional[str] = Field(None, alias="tavilyKey")
    firecrawl_key: Optional[str] = Field(None, alias="firecrawlKey")

    model_config = ConfigDict(populate_by_name=True)


class SettingsResponse(BaseModel):
    """Response never includes actual key values — only masked indicators."""
    has_openrouter_key: bool = Field(alias="hasOpenRouterKey")
    has_tavily_key: bool = Field(alias="hasTavilyKey")
    has_firecrawl_key: bool = Field(alias="hasFirecrawlKey")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# Quota Schemas
# ============================================================

class QuotaCheckResponse(BaseModel):
    action: str
    remaining: int
    limit: int
    allowed: bool
