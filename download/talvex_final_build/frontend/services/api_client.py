"""
TALVEX API Client
Central module for all backend communication.
Robust error handling with proper JSON parsing and user-friendly error messages.
"""

import requests
import json as _json
from typing import Optional, Dict, Any, List


API_BASE = "http://localhost:8000/api"


def _safe_json(resp: requests.Response) -> Any:
    """Safely parse JSON response, raising a clear error on failure."""
    try:
        return resp.json()
    except (_json.JSONDecodeError, ValueError):
        # Response is not JSON — extract what we can
        text = resp.text[:500] if resp.text else "(empty response)"
        raise ValueError(
            f"Server returned non-JSON response (HTTP {resp.status_code}). "
            f"Body: {text}"
        )


def _extract_error(resp: requests.Response) -> str:
    """Extract a human-readable error message from an API error response."""
    ct = (resp.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        try:
            data = resp.json()
            # FastAPI defaults to "detail"; our custom handler uses "error"
            return data.get("detail") or data.get("error") or data.get("message") or resp.text
        except (_json.JSONDecodeError, ValueError):
            pass
    return resp.text[:300] if resp.text else f"HTTP {resp.status_code}"


class TALVEXClient:
    """Central API client for TALVEX backend."""

    @staticmethod
    def get(path: str, params: dict = None) -> dict:
        """Send a GET request."""
        try:
            resp = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
        except requests.ConnectionError:
            raise ConnectionError("Cannot connect to TALVEX backend at localhost:8000. Is the server running?")
        except requests.Timeout:
            raise ConnectionError("Request timed out. The server may be overloaded.")

        if resp.status_code == 404:
            raise ValueError(f"Resource not found: {path}")
        if resp.status_code >= 400:
            raise ConnectionError(f"API error {resp.status_code}: {_extract_error(resp)}")
        return _safe_json(resp)

    @staticmethod
    def post(path: str, json: dict = None, files: dict = None, data: dict = None) -> dict:
        """Send a POST request."""
        try:
            resp = requests.post(f"{API_BASE}{path}", json=json, files=files, data=data, timeout=30)
        except requests.ConnectionError:
            raise ConnectionError("Cannot connect to TALVEX backend at localhost:8000. Is the server running?")
        except requests.Timeout:
            raise ConnectionError("Request timed out. The server may be overloaded.")

        if resp.status_code >= 400:
            raise ConnectionError(f"API error {resp.status_code}: {_extract_error(resp)}")
        return _safe_json(resp)

    @staticmethod
    def patch(path: str, json: dict = None) -> dict:
        """Send a PATCH request."""
        try:
            resp = requests.patch(f"{API_BASE}{path}", json=json, timeout=10)
        except requests.ConnectionError:
            raise ConnectionError("Cannot connect to TALVEX backend at localhost:8000. Is the server running?")
        except requests.Timeout:
            raise ConnectionError("Request timed out.")

        if resp.status_code >= 400:
            raise ConnectionError(f"API error {resp.status_code}: {_extract_error(resp)}")
        return _safe_json(resp)

    @staticmethod
    def delete(path: str) -> dict:
        """Send a DELETE request."""
        try:
            resp = requests.delete(f"{API_BASE}{path}", timeout=10)
        except requests.ConnectionError:
            raise ConnectionError("Cannot connect to TALVEX backend at localhost:8000. Is the server running?")
        except requests.Timeout:
            raise ConnectionError("Request timed out.")

        if resp.status_code >= 400:
            raise ConnectionError(f"API error {resp.status_code}: {_extract_error(resp)}")
        return _safe_json(resp)

    # ============================================================
    # Applications
    # ============================================================

    @staticmethod
    def list_applications(status: str = None, platform: str = None) -> List[dict]:
        params = {}
        if status:
            params["status"] = status
        if platform:
            params["platform"] = platform
        result = TALVEXClient.get("/applications", params=params)
        return result if isinstance(result, list) else result.get("applications", result)

    @staticmethod
    def create_application(data: dict) -> dict:
        return TALVEXClient.post("/applications", json=data)

    @staticmethod
    def get_application(app_id: str) -> dict:
        return TALVEXClient.get(f"/applications/{app_id}")

    @staticmethod
    def update_application(app_id: str, data: dict) -> dict:
        return TALVEXClient.patch(f"/applications/{app_id}", json=data)

    @staticmethod
    def advance_application(app_id: str, target_status: str) -> dict:
        return TALVEXClient.post(f"/applications/{app_id}/advance", json={"targetStatus": target_status})

    @staticmethod
    def delete_application(app_id: str) -> dict:
        return TALVEXClient.delete(f"/applications/{app_id}")

    # ============================================================
    # Personas
    # ============================================================

    @staticmethod
    def list_personas() -> List[dict]:
        result = TALVEXClient.get("/personas")
        return result if isinstance(result, list) else result.get("personas", result)

    @staticmethod
    def create_persona(data: dict) -> dict:
        return TALVEXClient.post("/personas", json=data)

    @staticmethod
    def get_persona(persona_id: str) -> dict:
        return TALVEXClient.get(f"/personas/{persona_id}")

    @staticmethod
    def update_persona(persona_id: str, data: dict) -> dict:
        return TALVEXClient.patch(f"/personas/{persona_id}", json=data)

    @staticmethod
    def delete_persona(persona_id: str) -> dict:
        return TALVEXClient.delete(f"/personas/{persona_id}")

    # ============================================================
    # Canary / Privacy
    # ============================================================

    @staticmethod
    def list_canaries() -> List[dict]:
        result = TALVEXClient.get("/canary")
        return result if isinstance(result, list) else result.get("canaries", result)

    @staticmethod
    def create_canary(data: dict) -> dict:
        return TALVEXClient.post("/canary", json=data)

    @staticmethod
    def flag_canary(canary_id: str, data: dict) -> dict:
        return TALVEXClient.patch(f"/canary/{canary_id}/flag", json=data)

    @staticmethod
    def get_leaks() -> dict:
        return TALVEXClient.get("/canary/leaks")

    # ============================================================
    # Resume
    # ============================================================

    @staticmethod
    def upload_resume(app_id: str, file) -> dict:
        return TALVEXClient.post("/resume/upload", data={"app_id": app_id}, files={"file": file})

    @staticmethod
    def get_resume_versions(app_id: str) -> List[dict]:
        result = TALVEXClient.get(f"/resume/versions/{app_id}")
        return result if isinstance(result, list) else result.get("versions", result)

    @staticmethod
    def customize_resume(data: dict) -> bytes:
        """Customize resume — returns .docx bytes."""
        resp = requests.post(f"{API_BASE}/resume/customize", json=data, timeout=30)
        if resp.status_code >= 400:
            raise ConnectionError(f"API error {resp.status_code}: {_extract_error(resp)}")
        if resp.status_code == 200:
            return resp.content
        raise ConnectionError(f"Unexpected response: HTTP {resp.status_code}")

    @staticmethod
    def list_templates() -> List[dict]:
        result = TALVEXClient.get("/resume/templates")
        return result.get("templates", []) if isinstance(result, dict) else result

    # ============================================================
    # Analytics
    # ============================================================

    @staticmethod
    def get_analytics() -> dict:
        return TALVEXClient.get("/analytics")

    @staticmethod
    def get_funnel() -> List[dict]:
        result = TALVEXClient.get("/analytics/funnel")
        return result if isinstance(result, list) else result.get("funnel", result)

    @staticmethod
    def get_platform_stats() -> List[dict]:
        result = TALVEXClient.get("/analytics/platform")
        return result if isinstance(result, list) else result.get("platformBreakdown", result)

    @staticmethod
    def get_salary_trends() -> List[dict]:
        result = TALVEXClient.get("/analytics/salary")
        return result if isinstance(result, list) else result.get("salaryTrends", result)

    # ============================================================
    # Jobs Search
    # ============================================================

    @staticmethod
    def search_jobs(query: str, country: str = "us", num_pages: int = 1, date_posted: str = None) -> dict:
        data = {"query": query, "country": country, "numPages": num_pages}
        if date_posted:
            data["datePosted"] = date_posted
        return TALVEXClient.post("/jobs/search", json=data)

    @staticmethod
    def ingest_job(data: dict) -> dict:
        return TALVEXClient.post("/jobs/ingest", json=data)

    @staticmethod
    def parse_email(data: dict) -> dict:
        return TALVEXClient.post("/jobs/parse-email", json=data)

    # ============================================================
    # Recommendations
    # ============================================================

    @staticmethod
    def get_skill_gap(persona_id: str) -> dict:
        return TALVEXClient.get(f"/recommendations/skill-gap/{persona_id}")

    @staticmethod
    def get_trade_recommendations() -> dict:
        return TALVEXClient.get("/recommendations/trades")

    @staticmethod
    def get_pipeline_telemetry() -> dict:
        return TALVEXClient.get("/recommendations/pipeline")

    @staticmethod
    def get_follow_up_template(app_id: str) -> dict:
        return TALVEXClient.post(f"/recommendations/follow-up/{app_id}")

    @staticmethod
    def get_follow_up_alerts(days_threshold: int = 7) -> dict:
        """Get applications that need follow-up attention."""
        return TALVEXClient.get("/applications/follow-ups/alerts", params={"days_threshold": days_threshold})

    # ============================================================
    # LLM-Powered Features
    # ============================================================

    @staticmethod
    def analyze_jd(job_description: str) -> dict:
        """Analyze a job description: extract skills, experience level, work mode, perks."""
        return TALVEXClient.post("/llm/analyze-jd", json={"jobDescription": job_description})

    @staticmethod
    def classify_email(email_body: str) -> dict:
        """Classify an email as rejection, interview, assessment, general, or uncertain."""
        return TALVEXClient.post("/llm/classify-email", json={"emailBody": email_body})

    @staticmethod
    def generate_cover_letter(job_description: str, persona_skills: list, company: str, role: str) -> dict:
        """Generate a tailored cover letter."""
        return TALVEXClient.post("/llm/cover-letter", json={
            "jobDescription": job_description,
            "personaSkills": persona_skills,
            "company": company,
            "role": role,
        })

    @staticmethod
    def generate_follow_up_email(company: str, role: str, days_applied: int, followup_count: int) -> dict:
        """Generate a follow-up email template."""
        return TALVEXClient.post("/llm/follow-up", json={
            "company": company,
            "role": role,
            "daysApplied": days_applied,
            "followupCount": followup_count,
        })

    @staticmethod
    def generate_interview_prep(job_description: str, company: str, role: str) -> dict:
        """Generate interview preparation questions and tips."""
        return TALVEXClient.post("/llm/interview-prep", json={
            "jobDescription": job_description,
            "company": company,
            "role": role,
        })

    @staticmethod
    def get_resume_tips(resume_text: str, job_description: str) -> dict:
        """Get resume improvement suggestions based on JD alignment."""
        return TALVEXClient.post("/llm/resume-tips", json={
            "resumeText": resume_text,
            "jobDescription": job_description,
        })

    # ============================================================
    # Vector Search
    # ============================================================

    @staticmethod
    def search_similar(query: str, top_k: int = 5, app_id: str = None) -> dict:
        """Search for similar jobs using FAISS vector search."""
        data = {"query": query, "topK": top_k}
        if app_id:
            data["appId"] = app_id
        return TALVEXClient.post("/search/similar", json=data)

    @staticmethod
    def get_search_stats() -> dict:
        """Get FAISS search index statistics."""
        return TALVEXClient.get("/search/stats")
