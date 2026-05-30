"""
TALVEX Web Scraper — Multi-Source Fallback Chain

Provides a unified ``scrape_url()`` interface that tries multiple scraping
backends in order of cost efficiency:

  1. **Tavily Extract** (primary) — get content directly from Tavily's
     ``include_raw_content`` or ``extract_depth``.  Uses 1 Tavily credit.
  2. **Jina Reader** (free) — ``https://r.jina.ai/{url}`` via HTTP GET.
     No API key needed.  Handles ~80 % of static sites.
  3. **Firecrawl** (credits) — headless browser scrape for JS-heavy sites
     (LinkedIn, Workday, Greenhouse).  Uses 1 Firecrawl credit.
  4. **Manual paste** — caller should prompt the user to paste content.

All scraped content is cleaned before return:
  - Strip "Loading..." / "Please enable JavaScript" remnants
  - Remove navigation menus, sidebars, and filter boilerplate
  - Return structured JSON: ``{url, title, content_markdown, source, cleaned}``

Environment:
  TAVILY_API_KEY      — for primary extraction (required for tier 1)
  FIRECRAWL_API_KEY   — for JS-heavy sites (optional, tier 3)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE_URL: str = "https://api.firecrawl.dev/v1"
JINA_READER_PREFIX: str = "https://r.jina.ai"

# Request timeouts
_SCRRAPE_TIMEOUT: float = 30.0  # seconds


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ScrapeSource(str, Enum):
    """Which backend successfully scraped the URL."""
    TAVILY = "tavily"
    JINA = "jina_reader"
    FIRECRAWL = "firecrawl"
    MANUAL = "manual"
    FAILED = "failed"


@dataclass
class ScrapeResult:
    """
    Structured result from the scraping pipeline.

    Attributes:
        url: The URL that was scraped.
        title: Page title (if extractable).
        content_markdown: Cleaned main content in Markdown format.
        source: Which backend produced this result.
        success: Whether scraping succeeded.
        error: Error message if scraping failed.
        word_count: Number of words in the cleaned content.
        metadata: Additional metadata from the scraping backend.
    """
    url: str
    title: str = ""
    content_markdown: str = ""
    source: ScrapeSource = ScrapeSource.FAILED
    success: bool = False
    error: str | None = None
    word_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Content cleaning pipeline
# ---------------------------------------------------------------------------

# Patterns to remove from scraped content
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(Loading,?\s*please\s*wait\.\.\.)", re.IGNORECASE),
    re.compile(r"(Please\s+enable\s+JavaScript\s+to\s+view)", re.IGNORECASE),
    re.compile(r"(Please\s+enable\s+JavaScript)", re.IGNORECASE),
    re.compile(r"(JavaScript\s+is\s+required)", re.IGNORECASE),
]

# Lines containing these keywords are dropped entirely
_SKIP_LINE_KEYWORDS: list[str] = [
    "Filters",
    "As per my preferences",
    "Save this search as alert",
    "All Filters",
    "Cookie Preferences",
    "Privacy Policy",
    "Terms of Service",
    "Sign In",
    "Sign Up",
    "Create Account",
    "Forgot Password",
]


def _is_packed_filter_line(line: str) -> bool:
    """
    Detect lines that are packed filter/category lists.

    These lines look like:
      ".NET Development3D PrintingAI AgentDevelopmentAccountsActing..."
      "AdilabadAgaraharaAgartalaAgondaAgraAhmadnagarAhmedabad"

    Heuristics:
      - Long line (>40 chars)
      - Many lowercase→uppercase transitions (TitleCase concatenation)
      - High ratio of words to spaces (concatenated, not spaced out)
      - Not a proper sentence (no terminal punctuation)
    """
    if len(line) < 30:
        return False

    # Skip if it looks like a proper sentence
    if line.endswith((".", "!", "?")):
        return False

    # Count lowercase→uppercase transitions (camelCase concatenation)
    # e.g., "PrintingAI" has 'g'→'A', "DevelopmentAccounts" has 't'→'A'
    transitions = len(re.findall(r"[a-z][A-Z]", line))

    # Strong signal: 4+ transitions in a line = almost certainly packed
    if transitions >= 4:
        return True

    # Weaker signal: check word-to-space ratio
    words = re.findall(r"[a-zA-Z0-9+#.]+", line)
    if len(words) < 5:
        return False

    space_count = line.count(" ")
    # Normal text: ~1 space per word.  Packed text: <<1 space per word.
    if space_count < len(words) * 0.4 and transitions >= 2:
        return True

    return False


def clean_scraped_text(raw_text: str) -> str:
    """
    Clean raw scraped text by removing noise, boilerplate, and artifacts.

    Steps:
      1. Remove "Loading..." and "Enable JavaScript" remnants.
      2. Split into lines and filter out noise lines.
      3. Drop lines that look like packed filter/category lists.
      4. Remove lines containing boilerplate navigation keywords.
      5. Skip bare URLs and file paths.
      6. Reconstruct clean text with collapsed blank lines.

    Args:
        raw_text: The raw text extracted from a web page.

    Returns:
        Cleaned text with noise removed.
    """
    # Step 1: Remove noise patterns
    cleaned = raw_text
    for pattern in _NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Steps 2-5: Line-by-line filtering
    lines = cleaned.split("\n")
    filtered_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip empty lines (preserve paragraph breaks)
        if not stripped:
            if filtered_lines and filtered_lines[-1] != "":
                filtered_lines.append("")
            continue

        # Skip packed filter/category lists
        if _is_packed_filter_line(stripped):
            continue

        # Skip boilerplate navigation keywords
        if any(kw.lower() in stripped.lower() for kw in _SKIP_LINE_KEYWORDS):
            continue

        # Skip lines that are just URLs or file paths
        if re.match(r"^(https?://|www\.|/)", stripped) and len(stripped) < 100:
            continue

        filtered_lines.append(stripped)

    # Step 6: Reconstruct and collapse excessive blank lines
    result = "\n".join(filtered_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)  # Collapse 3+ newlines to 2
    return result.strip()


# ---------------------------------------------------------------------------
# Tier 1: Tavily Extract
# ---------------------------------------------------------------------------

async def _scrape_with_tavily(url: str) -> ScrapeResult:
    """
    Attempt to extract content using Tavily's extract endpoint.

    Tavily can return content directly from search results, avoiding a
    separate scrape step.  This uses 1 Tavily credit per URL.

    Falls back gracefully if TAVILY_API_KEY is not set.
    """
    if not TAVILY_API_KEY:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.TAVILY,
            error="TAVILY_API_KEY not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=_SCRRAPE_TIMEOUT) as client:
            # Use Tavily's extract endpoint if available (v1)
            # Fallback: use the search API with include_raw_content
            payload: dict[str, Any] = {
                "api_key": TAVILY_API_KEY,
                "query": url,
                "max_results": 1,
                "include_raw_content": True,
                "search_depth": "advanced",
            }

            response = await client.post(
                "https://api.tavily.com/search",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.TAVILY,
                    error="Tavily returned no results for URL",
                )

            first = results[0]
            raw_content = first.get("raw_content", "") or first.get("content", "")
            title = first.get("title", "")

            if not raw_content or len(raw_content) < 50:
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.TAVILY,
                    error=f"Tavily content too short ({len(raw_content)} chars)",
                )

            cleaned = clean_scraped_text(raw_content)
            word_count = len(cleaned.split())

            return ScrapeResult(
                url=url,
                title=title,
                content_markdown=cleaned,
                source=ScrapeSource.TAVILY,
                success=True,
                word_count=word_count,
                metadata={
                    "tavily_score": first.get("score", 0),
                },
            )

    except httpx.HTTPStatusError as exc:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.TAVILY,
            error=f"Tavily HTTP {exc.response.status_code}: "
                  f"{exc.response.text[:200]}",
        )
    except httpx.RequestError as exc:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.TAVILY,
            error=f"Tavily request failed: {exc}",
        )
    except Exception as exc:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.TAVILY,
            error=f"Tavily unexpected error: {exc}",
        )


# ---------------------------------------------------------------------------
# Tier 2: Jina Reader (free, no API key)
# ---------------------------------------------------------------------------

async def _scrape_with_jina(url: str) -> ScrapeResult:
    """
    Extract content using Jina Reader (https://r.jina.ai/{url}).

    Free service, no API key required.  Rate limited to ~20 requests/min.
    Does NOT execute JavaScript — fails on SPAs (LinkedIn, Workday).

    Returns cleaned Markdown if successful.
    """
    jina_url = f"{JINA_READER_PREFIX}/{url}"

    try:
        async with httpx.AsyncClient(timeout=_SCRRAPE_TIMEOUT) as client:
            # Jina Reader accepts optional headers for format control
            headers = {
                "Accept": "text/markdown",
                "X-Return-Format": "markdown",
            }
            response = await client.get(jina_url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            raw_content = response.text

            # Check for common failure indicators
            if not raw_content or len(raw_content) < 50:
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.JINA,
                    error="Jina returned empty or too-short content",
                )

            # Detect JavaScript-required pages
            js_indicators = ["enable javascript", "javascript is required",
                             "loading...", "please wait"]
            if any(ind in raw_content[:500].lower() for ind in js_indicators):
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.JINA,
                    error="Page requires JavaScript — Jina cannot render it",
                )

            # Try to extract title from content (Jina usually puts it as H1)
            title = ""
            title_match = re.search(r"^#\s+(.+)$", raw_content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

            cleaned = clean_scraped_text(raw_content)
            word_count = len(cleaned.split())

            return ScrapeResult(
                url=url,
                title=title,
                content_markdown=cleaned,
                source=ScrapeSource.JINA,
                success=True,
                word_count=word_count,
            )

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        error_msg = f"Jina HTTP {status}"
        if status == 429:
            error_msg += " (rate limited — too many requests)"
        elif status == 403:
            error_msg += " (forbidden — site blocked Jina)"
        return ScrapeResult(
            url=url, source=ScrapeSource.JINA, error=error_msg,
        )
    except httpx.RequestError as exc:
        return ScrapeResult(
            url=url, source=ScrapeSource.JINA,
            error=f"Jina request failed: {exc}",
        )
    except Exception as exc:
        return ScrapeResult(
            url=url, source=ScrapeSource.JINA,
            error=f"Jina unexpected error: {exc}",
        )


# ---------------------------------------------------------------------------
# Tier 3: Firecrawl (headless browser — uses credits)
# ---------------------------------------------------------------------------

async def _scrape_with_firecrawl(url: str) -> ScrapeResult:
    """
    Extract content using Firecrawl's Cloud API.

    Spins up a headless browser, waits for JS rendering, and returns
    clean Markdown.  Best for JS-heavy sites (LinkedIn, Workday, Greenhouse).

    Uses 1 Firecrawl credit per scrape.  Free tier: 1,000 credits/month.
    Only called when Tavily and Jina both fail.
    """
    if not FIRECRAWL_API_KEY:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.FIRECRAWL,
            error="FIRECRAWL_API_KEY not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:  # Longer timeout for browser
            headers = {
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "url": url,
                "formats": ["markdown"],
                "actions": [
                    # Wait for dynamic content to load
                    {"type": "wait", "milliseconds": 3000},
                ],
            }

            response = await client.post(
                f"{FIRECRAWL_BASE_URL}/scrape",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            # Check if scrape succeeded
            if data.get("success") is False:
                error_detail = data.get("error", "Unknown Firecrawl error")
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.FIRECRAWL,
                    error=f"Firecrawl scrape failed: {error_detail}",
                )

            # Extract markdown content
            markdown = data.get("markdown", "") or ""
            metadata = data.get("metadata", {}) or {}
            title = metadata.get("title", "") or ""

            if not markdown or len(markdown) < 50:
                return ScrapeResult(
                    url=url,
                    source=ScrapeSource.FIRECRAWL,
                    error=f"Firecrawl content too short ({len(markdown)} chars)",
                )

            cleaned = clean_scraped_text(markdown)
            word_count = len(cleaned.split())

            return ScrapeResult(
                url=url,
                title=title,
                content_markdown=cleaned,
                source=ScrapeSource.FIRECRAWL,
                success=True,
                word_count=word_count,
                metadata={
                    "description": metadata.get("description", ""),
                    "language": metadata.get("language", ""),
                    "firecrawl_credits_used": 1,
                },
            )

    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        error_msg = f"Firecrawl HTTP {status}"
        if status == 402:
            error_msg += " (credits exhausted — upgrade or wait for reset)"
        elif status == 429:
            error_msg += " (rate limited)"
        else:
            error_msg += f": {exc.response.text[:200]}"
        return ScrapeResult(
            url=url, source=ScrapeSource.FIRECRAWL, error=error_msg,
        )
    except httpx.RequestError as exc:
        return ScrapeResult(
            url=url, source=ScrapeSource.FIRECRAWL,
            error=f"Firecrawl request failed: {exc}",
        )
    except Exception as exc:
        return ScrapeResult(
            url=url, source=ScrapeSource.FIRECRAWL,
            error=f"Firecrawl unexpected error: {exc}",
        )


# ---------------------------------------------------------------------------
# Public API: Unified scraping pipeline
# ---------------------------------------------------------------------------

async def scrape_url(url: str) -> ScrapeResult:
    """
    Scrape a URL using the multi-tier fallback chain.

    Fallback order:
      1. Tavily Extract (1 credit) — best for most sites
      2. Jina Reader (free) — handles static pages well
      3. Firecrawl (1 credit) — headless browser for JS-heavy sites
      4. Return failure with guidance for manual paste

    Args:
        url: The URL to scrape.

    Returns:
        A ``ScrapeResult`` with cleaned Markdown content if successful,
        or error details if all tiers failed.
    """
    if not url:
        return ScrapeResult(
            url="",
            source=ScrapeSource.FAILED,
            error="Empty URL provided",
        )

    # Validate URL format
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ScrapeResult(
            url=url,
            source=ScrapeSource.FAILED,
            error=f"Invalid URL format: {url}",
        )

    logger.info("Starting scrape pipeline for URL: %s", url)

    # --- Tier 1: Tavily Extract ---
    logger.info("Tier 1: Trying Tavily Extract for %s", url)
    result = await _scrape_with_tavily(url)
    if result.success:
        logger.info(
            "Tavily succeeded for %s (%d words)", url, result.word_count,
        )
        return result
    logger.warning("Tavily failed for %s: %s", url, result.error)

    # --- Tier 2: Jina Reader (free) ---
    logger.info("Tier 2: Trying Jina Reader for %s", url)
    result = await _scrape_with_jina(url)
    if result.success:
        logger.info(
            "Jina Reader succeeded for %s (%d words)", url, result.word_count,
        )
        return result
    logger.warning("Jina Reader failed for %s: %s", url, result.error)

    # --- Tier 3: Firecrawl (credits) ---
    logger.info("Tier 3: Trying Firecrawl for %s", url)
    result = await _scrape_with_firecrawl(url)
    if result.success:
        logger.info(
            "Firecrawl succeeded for %s (%d words)", url, result.word_count,
        )
        return result
    logger.warning("Firecrawl failed for %s: %s", url, result.error)

    # --- All tiers failed ---
    logger.error(
        "All scraping tiers failed for URL: %s. "
        "User should paste content manually.",
        url,
    )
    return ScrapeResult(
        url=url,
        source=ScrapeSource.FAILED,
        error=(
            "All scraping methods failed. "
            "Please copy the page content and paste it directly."
        ),
    )


async def scrape_multiple(
    urls: list[str],
    max_concurrent: int = 3,
) -> list[ScrapeResult]:
    """
    Scrape multiple URLs with concurrency control.

    Args:
        urls: List of URLs to scrape.
        max_concurrent: Maximum concurrent scrape operations.

    Returns:
        List of ``ScrapeResult`` objects in the same order as input URLs.
    """
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _limited_scrape(url: str) -> ScrapeResult:
        async with semaphore:
            return await scrape_url(url)

    tasks = [_limited_scrape(url) for url in urls]
    return await asyncio.gather(*tasks)


def format_scrape_result_for_llm(result: ScrapeResult) -> str:
    """
    Format a scrape result for LLM consumption.

    Returns a clean string with the page title and content,
    suitable for injecting into an LLM prompt.
    """
    if not result.success:
        return f"[Scrape failed for {result.url}: {result.error}]"

    parts = []
    if result.title:
        parts.append(f"# {result.title}")
    parts.append(f"Source: {result.url}")
    parts.append(f"Scraped via: {result.source.value}")
    parts.append("")
    parts.append(result.content_markdown)

    return "\n".join(parts)
