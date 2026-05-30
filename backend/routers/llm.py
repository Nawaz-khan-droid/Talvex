"""
FastAPI router for LLM-powered features.
Endpoints:
  POST /api/llm/classify-email           - Classify an email body
  POST /api/llm/cover-letter             - Generate cover letter
  POST /api/llm/analyze-jd               - Analyze job description
  POST /api/llm/follow-up                - Generate follow-up template
  POST /api/llm/interview-prep           - Generate interview prep
  POST /api/llm/resume-tips              - Suggest resume improvements
  POST /api/llm/optimize-resume          - LLM-powered resume optimization
  POST /api/llm/optimized-cover-letter   - Cover letter informed by resume analysis
"""

import logging
import traceback
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from services.llm_service import llm_service
from services.resume_optimizer import resume_optimizer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm", tags=["llm"])


# ============================================================
# Request / Response Schemas
# ============================================================

class ClassifyEmailRequest(BaseModel):
    email_body: str = Field(..., alias="emailBody", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class ClassifyEmailResponse(BaseModel):
    classification: str
    confidence: float
    reasoning: str


class CoverLetterRequest(BaseModel):
    resume_text: str = Field(default="", alias="resumeText")
    job_description: str = Field(..., alias="jobDescription", min_length=1)
    persona_skills: list[str] = Field(default_factory=list, alias="personaSkills")
    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class CoverLetterResponse(BaseModel):
    cover_letter: str = Field(alias="coverLetter")

    model_config = ConfigDict(populate_by_name=True)


class AnalyzeJdRequest(BaseModel):
    job_description: str = Field(..., alias="jobDescription", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class AnalyzeJdResponse(BaseModel):
    required_skills: list[str] = Field(alias="requiredSkills")
    experience_level: str = Field(alias="experienceLevel")
    work_mode: str = Field(alias="workMode")
    perks: list[str]

    model_config = ConfigDict(populate_by_name=True)


class FollowUpRequest(BaseModel):
    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    days_applied: int = Field(..., alias="daysApplied", ge=0)
    followup_count: int = Field(..., alias="followupCount", ge=1)

    model_config = ConfigDict(populate_by_name=True)


class FollowUpResponse(BaseModel):
    follow_up_email: str = Field(alias="followUpEmail")

    model_config = ConfigDict(populate_by_name=True)


class InterviewPrepRequest(BaseModel):
    job_description: str = Field(..., alias="jobDescription", min_length=1)
    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class InterviewPrepQuestion(BaseModel):
    question: str
    category: str
    tip: str


class InterviewPrepResponse(BaseModel):
    questions: list[InterviewPrepQuestion]
    general_tips: list[str] = Field(alias="generalTips")

    model_config = ConfigDict(populate_by_name=True)


class ResumeTipsRequest(BaseModel):
    resume_text: str = Field(..., alias="resumeText", min_length=1)
    job_description: str = Field(..., alias="jobDescription", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class ResumeTipsResponse(BaseModel):
    keyword_gaps: list[str] = Field(alias="keywordGaps")
    suggestions: list[str]

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Resume Optimization Schemas
# ============================================================

class OptimizeResumeRequest(BaseModel):
    resume_text: str = Field(..., alias="resumeText", min_length=1)
    job_description: str = Field(..., alias="jobDescription", min_length=1)
    career_stage: str = Field(
        default="mid_level",
        alias="careerStage",
        pattern=r"^(entry_level|mid_level|senior|executive)$",
    )

    model_config = ConfigDict(populate_by_name=True)


class OptimizeResumeResponse(BaseModel):
    optimized_text: str = Field(alias="optimizedText")
    added_keywords: list[str] = Field(alias="addedKeywords", default_factory=list)
    removed_generic_phrases: list[str] = Field(alias="removedGenericPhrases", default_factory=list)
    before_ats_score: int = Field(alias="beforeAtsScore")
    after_ats_score: int = Field(alias="afterAtsScore")
    optimization_method: str = Field(alias="optimizationMethod")
    changes_summary: str = Field(alias="changesSummary", default="")

    model_config = ConfigDict(populate_by_name=True)


class OptimizedCoverLetterRequest(BaseModel):
    resume_text: str = Field(..., alias="resumeText", min_length=1)
    job_description: str = Field(..., alias="jobDescription", min_length=1)
    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class OptimizedCoverLetterResponse(BaseModel):
    cover_letter: str = Field(alias="coverLetter")
    tone: str = Field(default="professional")
    highlights_count: int = Field(alias="highlightsCount", default=0)

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Endpoints
# ============================================================

@router.post("/classify-email", response_model=ClassifyEmailResponse)
async def classify_email(request: ClassifyEmailRequest, current_user: dict = Depends(get_current_user)):
    """Classify an email as: Rejection, Interview, Assessment, General, or Uncertain."""
    try:
        result = await llm_service.analyze_email(request.email_body)
        return ClassifyEmailResponse(
            classification=result["classification"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
        )
    except Exception as e:
        logger.error("[LLM Router] Email classification failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Email classification failed: {str(e)}")


@router.post("/cover-letter", response_model=CoverLetterResponse)
async def generate_cover_letter(request: CoverLetterRequest, current_user: dict = Depends(get_current_user)):
    """Generate a tailored cover letter — delegates to the optimized resume_optimizer.

    This endpoint now routes to resume_optimizer.generate_optimized_cover_letter()
    which performs skill gap analysis for a more targeted letter.
    """
    try:
        # Use resume_text if provided, otherwise fall back to persona_skills string
        resume_input = request.resume_text or " ".join(request.persona_skills)
        result = await resume_optimizer.generate_optimized_cover_letter(
            resume_text=resume_input,
            job_description=request.job_description,
            company=request.company,
            role=request.role,
        )
        return CoverLetterResponse(cover_letter=result.get("cover_letter", ""))
    except Exception as e:
        logger.error("[LLM Router] Cover letter generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {str(e)}")


@router.post("/analyze-jd", response_model=AnalyzeJdResponse)
async def analyze_jd(request: AnalyzeJdRequest, current_user: dict = Depends(get_current_user)):
    """Extract structured data from job description: skills, experience level, work mode, perks."""
    try:
        result = await llm_service.analyze_job_description(request.job_description)
        return AnalyzeJdResponse(
            required_skills=result.get("required_skills", []),
            experience_level=result.get("experience_level", "Not Specified"),
            work_mode=result.get("work_mode", "Not Specified"),
            perks=result.get("perks", []),
        )
    except Exception as e:
        logger.error("[LLM Router] JD analysis failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Job description analysis failed: {str(e)}")


@router.post("/follow-up", response_model=FollowUpResponse)
async def generate_follow_up(request: FollowUpRequest, current_user: dict = Depends(get_current_user)):
    """Generate a professional follow-up email template."""
    try:
        email = await llm_service.generate_follow_up(
            company=request.company,
            role=request.role,
            days_applied=request.days_applied,
            followup_count=request.followup_count,
        )
        return FollowUpResponse(follow_up_email=email)
    except Exception as e:
        logger.error("[LLM Router] Follow-up generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Follow-up email generation failed: {str(e)}")


@router.post("/interview-prep", response_model=InterviewPrepResponse)
async def generate_interview_prep(request: InterviewPrepRequest, current_user: dict = Depends(get_current_user)):
    """Generate interview preparation questions and tips."""
    try:
        result = await llm_service.generate_interview_prep(
            job_description=request.job_description,
            company=request.company,
            role=request.role,
        )
        questions = [
            InterviewPrepQuestion(
                question=q["question"],
                category=q["category"],
                tip=q["tip"],
            )
            for q in result.get("questions", [])
        ]
        return InterviewPrepResponse(
            questions=questions,
            general_tips=result.get("general_tips", []),
        )
    except Exception as e:
        logger.error("[LLM Router] Interview prep generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Interview prep generation failed: {str(e)}")


@router.post("/resume-tips", response_model=ResumeTipsResponse)
async def improve_resume_suggestions(request: ResumeTipsRequest, current_user: dict = Depends(get_current_user)):
    """Suggest resume improvements based on job description alignment."""
    try:
        result = await llm_service.improve_resume_suggestions(
            resume_text=request.resume_text,
            job_description=request.job_description,
        )
        return ResumeTipsResponse(
            keyword_gaps=result.get("keyword_gaps", []),
            suggestions=result.get("suggestions", []),
        )
    except Exception as e:
        logger.error("[LLM Router] Resume tips generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Resume tips generation failed: {str(e)}")


@router.post("/optimize-resume", response_model=OptimizeResumeResponse)
async def optimize_resume(request: OptimizeResumeRequest, current_user: dict = Depends(get_current_user)):
    """Optimize resume text for a specific job description using LLM or heuristic fallback.

    Rewrites bullet points with measurable achievements, incorporates missing JD keywords,
    cuts generic/vague content, and returns before/after ATS scores.
    """
    try:
        result = await resume_optimizer.optimize_resume(
            resume_text=request.resume_text,
            job_description=request.job_description,
            career_stage=request.career_stage,
        )
        return OptimizeResumeResponse(
            optimized_text=result.get("optimized_text", ""),
            added_keywords=result.get("added_keywords", []),
            removed_generic_phrases=result.get("removed_generic_phrases", []),
            before_ats_score=result.get("before_ats_score", 0),
            after_ats_score=result.get("after_ats_score", 0),
            optimization_method=result.get("optimization_method", "none"),
            changes_summary=result.get("changes_summary", ""),
        )
    except Exception as e:
        logger.error("[LLM Router] Resume optimization failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Resume optimization failed: {str(e)}")


@router.post("/optimized-cover-letter", response_model=OptimizedCoverLetterResponse)
async def generate_optimized_cover_letter(request: OptimizedCoverLetterRequest, current_user: dict = Depends(get_current_user)):
    """Generate a tailored cover letter informed by resume analysis against the JD.

    Unlike the basic cover-letter endpoint, this analyzes the resume for skill gaps
    and generates a more targeted letter that bridges the candidate's experience
    with the job requirements.
    """
    try:
        result = await resume_optimizer.generate_optimized_cover_letter(
            resume_text=request.resume_text,
            job_description=request.job_description,
            company=request.company,
            role=request.role,
        )
        return OptimizedCoverLetterResponse(
            cover_letter=result.get("cover_letter", ""),
            tone=result.get("tone", "professional"),
            highlights_count=result.get("highlights_count", 0),
        )
    except Exception as e:
        logger.error("[LLM Router] Optimized cover letter generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Optimized cover letter generation failed: {str(e)}",
        )
