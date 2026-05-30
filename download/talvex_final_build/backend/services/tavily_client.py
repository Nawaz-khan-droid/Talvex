"""
Tavily AI search client for job aggregation.

Uses the Tavily Search API (https://api.tavily.com/search) to discover job
listings from across the web (LinkedIn, Indeed, Naukri, etc.) via advanced
web search. Falls back gracefully when TAVILY_API_KEY is not configured.

All methods are async and use httpx.AsyncClient for non-blocking I/O.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_load_dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _load_dotenv_path.exists():
    load_dotenv(_load_dotenv_path)

TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
TAVILY_BASE_URL: str = "https://api.tavily.com/search"

if not TAVILY_API_KEY:
    logger.warning(
        "TAVILY_API_KEY not set in environment. "
        "TavilyClient will return empty results."
    )

# Target job-board domains used in search queries
_JOB_SITE_FILTERS = [
    "site:linkedin.com",
    "site:indeed.com",
    "site:naukri.com",
    "site:glassdoor.com",
    "site:wellfound.com",
]


class TavilyClient:
    """Async client for the Tavily Search API, specialized for job discovery."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialize the Tavily client.

        Args:
            api_key: Tavily API key. Falls back to the ``TAVILY_API_KEY``
                     environment variable when *None*.
        """
        self._api_key = api_key or TAVILY_API_KEY
        self._client = httpx.AsyncClient(
            base_url=TAVILY_BASE_URL,
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_jobs(
        self,
        job_title: str,
        location: str = "",
        employment_type: str = "",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for jobs using the Tavily web-search API.

        Args:
            job_title: Role to search for (e.g. "Python Developer").
            location: Geographic filter (e.g. "New Jersey").
            employment_type: "full-time", "part-time", "contract", "intern",
                             or empty string for no filter.
            max_results: Maximum number of results to return (1-20).

        Returns:
            A list of normalized job dicts. Returns an empty list when the
            API key is not configured or on error.
        """
        if not self._api_key:
            logger.warning(
                "TavilyClient.search_jobs called but no API key is configured; "
                "returning empty results."
            )
            return []

        max_results = max(1, min(max_results, 20))

        query = self._build_query(job_title, location, employment_type)
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_raw_content": False,
            "search_depth": "advanced",
        }

        try:
            response = await self._client.post(url=TAVILY_BASE_URL, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Tavily API error %s: %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return []
        except httpx.RequestError as exc:
            logger.error("Tavily request failed: %s", exc)
            return []

        data = response.json()
        return self._parse_results(data)

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Query building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_query(
        job_title: str,
        location: str = "",
        employment_type: str = "",
    ) -> str:
        """
        Construct a Tavily search query targeting job-board sites.

        The resulting query looks like::

            '"Python Developer" jobs "New Jersey" full-time
             site:linkedin.com OR site:indeed.com OR site:naukri.com'

        Args:
            job_title: The role title.
            location: Optional location string.
            employment_type: Optional employment type filter.

        Returns:
            A search-engine-ready query string.
        """
        parts: list[str] = [f'"{job_title}"', "jobs"]

        if location:
            parts.append(f'"{location}"')

        if employment_type:
            parts.append(employment_type)

        site_clause = " OR ".join(_JOB_SITE_FILTERS)
        parts.append(site_clause)

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Parse the Tavily JSON response into a deduplicated, normalized list.

        Args:
            data: Raw JSON dict returned by the Tavily API.

        Returns:
            A list of normalized job dicts with no duplicate URLs.
        """
        raw_results: list[dict[str, Any]] = data.get("results", [])
        seen_urls: set[str] = set()
        normalized: list[dict[str, Any]] = []

        for result in raw_results:
            job = TavilyClient._normalize_job(result)
            url = job.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                normalized.append(job)

        return normalized

    @staticmethod
    def _normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
        """
        Transform a single Tavily search result into a job-shaped dict.

        Tavily returns generic web-search results, so the title usually
        follows the pattern ``"Job Title - Company"`` or
        ``"Job Title | Company"``.  This method attempts to split those
        components apart.

        Args:
            raw: One entry from the ``results`` list in the Tavily response.

        Returns:
            A dict with keys: title, company, location, url, description,
            source_platform, posted_date.
        """
        title_raw: str = raw.get("title", "").strip()
        url: str = raw.get("url", "").strip()
        content: str = raw.get("content", "").strip()

        # Extract company / title from the raw search-result title
        title, company = _split_title_company(title_raw)

        # Derive source platform from the URL domain
        source_platform = _extract_platform(url)

        # Attempt to pull a posted date from Tavily's score/relevance metadata
        posted_date = raw.get("published_date", "")

        # Tavily sometimes returns location hints in the content snippet
        location = raw.get("location", "")

        return {
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": content,
            "source_platform": source_platform,
            "posted_date": posted_date,
        }


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------

def _split_title_company(title_raw: str) -> tuple[str, str]:
    """
    Split a search-result title into ``(job_title, company)``.

    Handles separators like ``" | "``, ``" - "``, ``" — "``, ``" – "``.

    Returns:
        A (title, company) tuple.  Missing parts default to empty strings.
    """
    separators = [" | ", " - ", " — ", " – "]
    for sep in separators:
        if sep in title_raw:
            left, right = title_raw.split(sep, 1)
            return left.strip(), right.strip()

    # No separator found — entire string is the title
    return title_raw, ""


def _extract_platform(url: str) -> str:
    """
    Derive a human-readable platform name from a URL.

    Examples::

        "https://www.linkedin.com/jobs/..."  → "linkedin"
        "https://www.indeed.com/viewjob..."  → "indeed"

    Returns:
        Lowercased domain label, or "unknown" if parsing fails.
    """
    if not url:
        return "unknown"
    try:
        netloc = urlparse(url).netloc.lower()
        # Strip "www." prefix
        domain = netloc.removeprefix("www.")
        # Take only the first label (e.g. "linkedin.com" → "linkedin")
        return domain.split(".")[0]
    except Exception:
        return "unknown"


# Convenience singleton — can be imported and used directly:
#   from services.tavily_client import tavily
#   results = await tavily.search_jobs("Python Developer", "New Jersey")
tavily = TavilyClient()
