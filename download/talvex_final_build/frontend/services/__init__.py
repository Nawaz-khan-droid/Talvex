"""
TALVEX API Client
Central module for all backend communication.
"""

import requests
from typing import Optional, Dict, Any, List


API_BASE = "http://localhost:8000/api"


class TALVEXClient:
    """Central API client for TALVEX backend."""

    @staticmethod
    def get(path: str, params: dict = None) -> dict:
        """Send a GET request."""
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
        if resp.status_code == 404:
            raise ValueError(f"Resource not found: {path}")
        if resp.status_code >= 400:
            error_detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ConnectionError(f"API error {resp.status_code}: {error_detail}")
        return resp.json()

    @staticmethod
    def post(path: str, json: dict = None, files: dict = None, data: dict = None) -> dict:
        """Send a POST request."""
        resp = requests.post(f"{API_BASE}{path}", json=json, files=files, data=data, timeout=30)
        if resp.status_code >= 400:
            error_detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ConnectionError(f"API error {resp.status_code}: {error_detail}")
        return resp.json()

    @staticmethod
    def patch(path: str, json: dict = None) -> dict:
        """Send a PATCH request."""
        resp = requests.patch(f"{API_BASE}{path}", json=json, timeout=10)
        if resp.status_code >= 400:
            error_detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ConnectionError(f"API error {resp.status_code}: {error_detail}")
        return resp.json()

    @staticmethod
    def delete(path: str) -> dict:
        """Send a DELETE request."""
        resp = requests.delete(f"{API_BASE}{path}", timeout=10)
        if resp.status_code >= 400:
            error_detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ConnectionError(f"API error {resp.status_code}: {error_detail}")
        return resp.json()

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

    # ============================================================
    # Recommendations
    # ============================================================

    @staticmethod
    def get_skill_gap(persona_id: str) -> dict:
        return TALVEXClient.get(f"/recommendations/skill-gap/{persona_id}")

    @staticmethod
    def get_pipeline_telemetry() -> dict:
        return TALVEXClient.get("/recommendations/pipeline")

    @staticmethod
    def get_follow_up_template(app_id: str) -> dict:
        return TALVEXClient.post(f"/recommendations/follow-up/{app_id}")
