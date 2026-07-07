"""
RapidAPI JSearch HTTPS client for job search, details, and salary estimation.
Uses httpx.AsyncClient for async HTTP requests.
All URLs use HTTPS (https://jsearch.p.rapidapi.com).
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from services.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError

logger = logging.getLogger(__name__)

# Load .env from project root
_load_dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _load_dotenv_path.exists():
    load_dotenv(_load_dotenv_path)

JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com"
JSEARCH_API_KEY = os.getenv("RAPIDAPI_KEY", "")
JSEARCH_HOST = "jsearch.p.rapidapi.com"

if not JSEARCH_API_KEY:
    logger.warning("RAPIDAPI_KEY not set in environment. Job search will fail.")

HEADERS = {
    "x-rapidapi-key": JSEARCH_API_KEY,
    "x-rapidapi-host": JSEARCH_HOST,
}

_circuit_breaker = AsyncCircuitBreaker(
    name="jsearch",
    config=CircuitBreakerConfig(failure_threshold=4, recovery_timeout_seconds=45.0),
)


async def _get_with_circuit_breaker(url: str, params: dict[str, Any]) -> dict[str, Any]:
    async def _do_request() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            return response.json()

    try:
        return await _circuit_breaker.call(_do_request)
    except CircuitBreakerOpenError as exc:
        logger.error("JSearch circuit breaker is OPEN for url=%s: %s", url, exc)
        raise Exception("JSearch temporarily unavailable due to repeated upstream failures.") from exc


async def search_jobs(
    query: str,
    country: str = "us",
    num_pages: int = 1,
    date_posted: Optional[str] = None,
) -> dict[str, Any]:
    """
    Search jobs via RapidAPI JSearch v2 endpoint.

    Args:
        query: Search query (e.g., "Python developer")
        country: Country code (e.g., "us", "in")
        num_pages: Number of pages to fetch (1-10)
        date_posted: Date filter - "today", "3days", "week", "month"

    Returns:
        dict with 'results' (list of job dicts), 'total_count', 'page_number'
    """
    params: dict[str, Any] = {
        "query": query,
        "page": "1",
        "num_pages": str(min(num_pages, 10)),
    }

    if country:
        params["country"] = country

    if date_posted:
        params["date_posted"] = date_posted

    logger.info(
        "JSearch search_jobs request query=%s country=%s num_pages=%s date_posted=%s",
        query,
        country,
        num_pages,
        date_posted or "",
    )
    try:
        data = await _get_with_circuit_breaker(f"{JSEARCH_BASE_URL}/search-v2", params)
    except httpx.HTTPStatusError as e:
        logger.error(f"JSearch API error {e.response.status_code}: {e.response.text}")
        raise Exception(f"JSearch API returned status {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"JSearch request failed: {e}")
        raise Exception(f"Failed to reach JSearch API: {e}") from e

    # Normalize response
    raw_results = data.get("data", [])
    results = [_normalize_job(result) for result in raw_results]
    logger.info("JSearch search_jobs success total_results=%d", len(results))

    return {
        "results": results,
        "totalCount": len(results),
        "pageNumber": 1,
    }


async def get_job_details(
    job_id: str,
    country: str = "us",
) -> dict[str, Any]:
    """
    Get detailed information about a specific job.

    Args:
        job_id: The JSearch job ID
        country: Country code

    Returns:
        dict with normalized job details
    """
    params: dict[str, Any] = {
        "job_id": job_id,
        "extended_publisher_details": "false",
    }

    if country:
        params["country"] = country

    logger.info("JSearch get_job_details request job_id=%s country=%s", job_id, country)
    try:
        data = await _get_with_circuit_breaker(f"{JSEARCH_BASE_URL}/job-details", params)
    except httpx.HTTPStatusError as e:
        logger.error(f"JSearch API error {e.response.status_code}: {e.response.text}")
        raise Exception(f"JSearch API returned status {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"JSearch request failed: {e}")
        raise Exception(f"Failed to reach JSearch API: {e}") from e

    raw_jobs = data.get("data", [])
    if raw_jobs:
        return _normalize_job(raw_jobs[0])
    return {}


async def get_estimated_salary(
    job_title: str,
    location: str = "",
) -> list[dict[str, Any]]:
    """
    Get estimated salary for a job title at a given location.

    Args:
        job_title: The job title (e.g., "Software Engineer")
        location: Location string (e.g., "San Francisco, CA" or "India")

    Returns:
        list of salary estimate dicts
    """
    params: dict[str, Any] = {
        "job_title": job_title,
    }

    if location:
        params["location"] = location

    logger.info("JSearch get_estimated_salary request job_title=%s location=%s", job_title, location)
    try:
        data = await _get_with_circuit_breaker(f"{JSEARCH_BASE_URL}/estimated-salary", params)
    except httpx.HTTPStatusError as e:
        logger.error(f"JSearch API error {e.response.status_code}: {e.response.text}")
        raise Exception(f"JSearch API returned status {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"JSearch request failed: {e}")
        raise Exception(f"Failed to reach JSearch API: {e}") from e

    raw_data = data.get("data", [])
    results = []
    for item in raw_data:
        results.append({
            "jobTitle": item.get("job_title", ""),
            "location": item.get("location", ""),
            "salaryMin": item.get("salary_min"),
            "salaryMax": item.get("salary_max"),
            "salaryCurrency": item.get("salary_currency", "USD"),
            "medianSalary": item.get("median_salary"),
        })

    logger.info("JSearch get_estimated_salary success entries=%d", len(results))
    return results


def _normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw JSearch job result into a clean dict."""
    return {
        "jobId": raw.get("job_id", ""),
        "employerName": raw.get("employer_name", ""),
        "employerLogo": raw.get("employer_logo", ""),
        "jobTitle": raw.get("job_title", ""),
        "jobDescription": raw.get("job_description", ""),
        "jobCity": raw.get("job_city", ""),
        "jobState": raw.get("job_state", ""),
        "jobCountry": raw.get("job_country", ""),
        "jobApplyLink": raw.get("job_apply_link", ""),
        "jobMinSalary": raw.get("job_min_salary"),
        "jobMaxSalary": raw.get("job_max_salary"),
        "jobSalaryCurrency": raw.get("job_salary_currency", "USD"),
        "jobSalaryPeriod": raw.get("job_salary_period", ""),
        "jobPostedAtDatetimeUTC": raw.get("job_posted_at_datetime_utc", ""),
        "jobEmploymentType": raw.get("job_employment_type", ""),
        "jobIsRemote": raw.get("job_is_remote", False),
        "jobQualifications": raw.get("job_qualifications", ""),
        "jobHighlights": raw.get("job_highlights", {}),
    }
