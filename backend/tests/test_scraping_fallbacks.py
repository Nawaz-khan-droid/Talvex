"""
TALVEX Scraping Fallback Chain Tests (Phase 8 — Task 8.3)

Locks in the Tavily -> Jina -> Firecrawl fallback behavior so future
changes don't break the manual deep-link logic.

Tests:
  1. Direct URL Detection: raw LinkedIn URL bypasses Tavily search
  2. Jina Failure -> Firecrawl fallback
  3. All tiers fail -> clean error message
  4. Invalid URL -> immediate rejection
  5. Empty URL -> immediate rejection
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.web_scraper import (
    scrape_url,
    _scrape_with_tavily,
    _scrape_with_jina,
    _scrape_with_firecrawl,
    ScrapeSource,
)


# ============================================================
# Test 1: Direct URL Detection (Tavily receives raw URL, not search)
# ============================================================

class TestDirectURLDetection:
    """Verify that direct URLs (e.g. LinkedIn job pages) are passed
    through to the scraping pipeline correctly.

    The Tavily tier should receive the URL as-is for extraction,
    not perform a web search for it.  If Tavily fails, the pipeline
    should fall through to Jina and then Firecrawl.
    """

    @pytest.mark.asyncio
    async def test_linkedin_url_passes_through_tavily_extract(self):
        """A raw LinkedIn URL should be sent to Tavily Extract API,
        not Tavily Search API.  Verify Tavily receives the exact URL.
        """
        linkedin_url = "https://linkedin.com/jobs/view/1234"

        # Mock Tavily to succeed
        mock_tavily_result = type("ScrapeResult", (), {
            "success": True,
            "source": ScrapeSource.TAVILY,
            "word_count": 150,
            "url": linkedin_url,
            "content_markdown": "Senior Software Engineer at Google...",
            "title": "Job Listing",
            "error": None,
            "metadata": {"tavily_credits_used": 1},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock) as mock_tavily:
            mock_tavily.return_value = mock_tavily_result

            result = await scrape_url(linkedin_url)

            # Assert Tavily was called with the exact URL
            mock_tavily.assert_called_once()
            call_args = mock_tavily.call_args
            assert call_args[0][0] == linkedin_url, (
                "Tavily should receive the raw LinkedIn URL for extraction, "
                "not a search query."
            )
            assert result.success is True
            assert result.source == ScrapeSource.TAVILY

    @pytest.mark.asyncio
    async def test_linkedin_url_falls_through_when_tavily_fails(self):
        """When Tavily fails for a LinkedIn URL, Jina should be tried next."""
        linkedin_url = "https://linkedin.com/jobs/view/5678"

        # Mock Tavily to fail
        mock_tavily_fail = type("ScrapeResult", (), {
            "success": False,
            "source": ScrapeSource.TAVILY,
            "error": "Tavily rate limit exceeded",
            "word_count": 0,
            "url": linkedin_url,
            "content_markdown": "",
            "title": "",
            "metadata": {},
        })()

        # Mock Jina to succeed
        mock_jina_result = type("ScrapeResult", (), {
            "success": True,
            "source": ScrapeSource.JINA,
            "word_count": 200,
            "url": linkedin_url,
            "content_markdown": "Full job description from Jina...",
            "title": "LinkedIn Job",
            "error": None,
            "metadata": {},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock) as mock_tavily, \
             patch("services.web_scraper._scrape_with_jina", new_callable=AsyncMock) as mock_jina:
            mock_tavily.return_value = mock_tavily_fail
            mock_jina.return_value = mock_jina_result

            result = await scrape_url(linkedin_url)

            # Tavily was tried first
            mock_tavily.assert_called_once_with(linkedin_url)
            # Then Jina was tried
            mock_jina.assert_called_once_with(linkedin_url)
            # Result should be from Jina
            assert result.success is True
            assert result.source == ScrapeSource.JINA


# ============================================================
# Test 2: Jina Failure -> Firecrawl Fallback
# ============================================================

class TestJinaFirecrawlFallback:
    """Verify the Jina -> Firecrawl fallback chain works correctly."""

    @pytest.mark.asyncio
    async def test_jina_timeout_falls_back_to_firecrawl(self):
        """When Jina returns a timeout/404, Firecrawl should be tried."""
        test_url = "https://jobs.leetcode.com/company/google/position/42"

        # Mock Tavily to fail
        mock_tavily_fail = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.TAVILY,
            "error": "Tavily error", "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()

        # Mock Jina to fail with timeout
        mock_jina_fail = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.JINA,
            "error": "Jina HTTP 404", "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()

        # Mock Firecrawl to succeed
        mock_firecrawl_result = type("ScrapeResult", (), {
            "success": True, "source": ScrapeSource.FIRECRAWL,
            "word_count": 300,
            "url": test_url,
            "content_markdown": "Full job listing scraped by headless browser...",
            "title": "Google SWE",
            "error": None,
            "metadata": {"firecrawl_credits_used": 1},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock, return_value=mock_tavily_fail), \
             patch("services.web_scraper._scrape_with_jina", new_callable=AsyncMock, return_value=mock_jina_fail), \
             patch("services.web_scraper._scrape_with_firecrawl", new_callable=AsyncMock, return_value=mock_firecrawl_result):
            result = await scrape_url(test_url)

            assert result.success is True
            assert result.source == ScrapeSource.FIRECRAWL
            assert result.metadata.get("firecrawl_credits_used") == 1

    @pytest.mark.asyncio
    async def test_jina_forbidden_falls_back_to_firecrawl(self):
        """When Jina returns 403 (site blocked Jina), Firecrawl is tried."""
        test_url = "https://www.workday.com/jobs/google/123"

        mock_fail_tavily = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.TAVILY,
            "error": "fail", "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()
        mock_fail_jina = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.JINA,
            "error": "Jina HTTP 403 (forbidden — site blocked Jina)",
            "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()
        mock_ok_firecrawl = type("ScrapeResult", (), {
            "success": True, "source": ScrapeSource.FIRECRAWL,
            "word_count": 100, "url": test_url,
            "content_markdown": "Workday listing...", "title": "Job", "error": None,
            "metadata": {},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock, return_value=mock_fail_tavily), \
             patch("services.web_scraper._scrape_with_jina", new_callable=AsyncMock, return_value=mock_fail_jina), \
             patch("services.web_scraper._scrape_with_firecrawl", new_callable=AsyncMock, return_value=mock_ok_firecrawl):
            result = await scrape_url(test_url)
            assert result.success is True
            assert result.source == ScrapeSource.FIRECRAWL

    @pytest.mark.asyncio
    async def test_firecrawl_no_credits_returns_clean_error(self):
        """When Firecrawl has no API key, returns clean error — not a crash."""
        test_url = "https://greenhouse.io/company/job/99"

        mock_fail_all = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.FAILED,
            "error": "Failed", "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()
        mock_firecrawl_no_key = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.FIRECRAWL,
            "error": "FIRECRAWL_API_KEY not configured",
            "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock, return_value=mock_fail_all), \
             patch("services.web_scraper._scrape_with_jina", new_callable=AsyncMock, return_value=mock_fail_all), \
             patch("services.web_scraper._scrape_with_firecrawl", new_callable=AsyncMock, return_value=mock_firecrawl_no_key):
            result = await scrape_url(test_url)

            assert result.success is False
            assert result.source == ScrapeSource.FAILED
            assert "All scraping methods failed" in (result.error or "")
            # Should NOT crash — just return a clean error
            assert result.error is not None


# ============================================================
# Test 3: All tiers fail -> clean error
# ============================================================

class TestAllTiersFail:
    """When all three tiers fail, the pipeline should return a clean
    error message directing the user to paste content manually."""

    @pytest.mark.asyncio
    async def test_all_fail_returns_manual_paste_message(self):
        """If Tavily, Jina, AND Firecrawl all fail, return helpful error."""
        test_url = "https://example.com/job/1"

        mock_fail = type("ScrapeResult", (), {
            "success": False, "source": ScrapeSource.FAILED,
            "error": "Failed", "word_count": 0,
            "url": test_url, "content_markdown": "", "title": "", "metadata": {},
        })()

        with patch("services.web_scraper._scrape_with_tavily", new_callable=AsyncMock, return_value=mock_fail), \
             patch("services.web_scraper._scrape_with_jina", new_callable=AsyncMock, return_value=mock_fail), \
             patch("services.web_scraper._scrape_with_firecrawl", new_callable=AsyncMock, return_value=mock_fail):
            result = await scrape_url(test_url)

            assert result.success is False
            assert result.source == ScrapeSource.FAILED
            assert "paste" in (result.error or "").lower()


# ============================================================
# Test 4: Invalid URL -> immediate rejection
# ============================================================

class TestInvalidURL:
    """The pipeline should reject malformed URLs immediately."""

    @pytest.mark.asyncio
    async def test_missing_scheme_rejected(self):
        result = await scrape_url("linkedin.com/jobs/view/123")
        assert result.success is False
        assert "Invalid URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_empty_url_rejected(self):
        result = await scrape_url("")
        assert result.success is False
        assert "Empty URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_none_url_rejected(self):
        result = await scrape_url(None)
        assert result.success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
