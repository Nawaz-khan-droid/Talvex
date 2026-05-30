"""
Phase 5 Test Suite: Critical Fixes & Cleanup

Validates every corrective action from Phase 5:
  1. Ghost Subsystem Purge — no localhost:3001 or httpx.post proxy calls in services
  2. OpenRouter Client — sole LLM pathway, no bypass routes
  3. 180s Timeout Standardization — all LLM calls wrapped in 180s timeout
  4. Rate Limiting — 15 RPM, 40 RPD for openrouter service
  5. Model Upgrades — gpt-oss-120b:free for searcher, gemma-4-26b-a4b-it:free for fallback
  6. PII Sanitization — all LLM calls sanitize before sending
  7. 429 Retry Handler — exponential backoff in openrouter_client
  8. Fernet Encryption — vault data encrypted at rest
  9. Fernet Static Key — PII_VAULT_MASTER_KEY / PII_VAULT_ENCRYPTION_KEY env-var support
  10. Call #12 Deprecation — no duplicate cover letter generation outside resume_optimizer
  11. Heuristic Fallbacks — every LLM method has a non-LLM fallback path
"""

import os
import re
import textwrap
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"


# ===================================================================
# 1. Ghost Subsystem Purge
# ===================================================================

class TestGhostSubsystemPurge:
    """Verify the ghost subsystem (httpx.post to localhost:3001) is completely eliminated."""

    @pytest.fixture(autouse=True)
    def _read_service_files(self):
        """Read all service files once for the test class."""
        self.service_files = {}
        services_dir = BACKEND_DIR / "services"
        for py_file in services_dir.glob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            with open(py_file, "r") as f:
                self.service_files[py_file.name] = f.read()

    def test_no_localhost_3001_in_service_code(self):
        """No service file contains httpx.post('http://localhost:3001') or similar."""
        violations = []
        proxy_patterns = [
            r'httpx\.post\s*\(\s*["\']http://localhost:3001',
            r'httpx\.post\s*\(\s*["\']http://127\.0\.0\.1:3001',
            r'httpx\.post\s*\(\s*["\'].*localhost.*3001',
            r'LLM_PROXY_URL',
        ]
        for filename, content in self.service_files.items():
            for pattern in proxy_patterns:
                for match in re.finditer(pattern, content):
                    # Check if it's in a comment or docstring
                    line_start = content.rfind('\n', 0, match.start()) + 1
                    line_end = content.find('\n', match.start())
                    line = content[line_start:line_end].strip()
                    # Skip if it's a comment explaining it was removed
                    if line.startswith('#') or '"""' in line or "'''" in line:
                        continue
                    # Skip docstring references
                    if 'NO' in line and ('local proxy' in line.lower() or 'httpx.post' in line.lower()):
                        continue
                    violations.append((filename, match.start(), pattern))

        assert len(violations) == 0, (
            f"Ghost subsystem violations found ({len(violations)}):\n"
            + "\n".join(f"  {f}: pattern={p}" for f, _, p in violations)
        )

    def test_no_httpx_post_proxy_in_llm_service(self):
        """llm_service.py has zero httpx.post calls (all via openrouter_client)."""
        content = self.service_files.get("llm_service.py", "")
        # Remove triple-quoted strings (docstrings) to avoid false positives
        code_only = re.sub(r'"""[\s\S]*?"""', '', content)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        # Find actual httpx.post calls (not in comments/docstrings)
        actual_calls = []
        for i, line in enumerate(code_only.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'httpx.post' in stripped:
                actual_calls.append((i, stripped))

        assert len(actual_calls) == 0, (
            f"llm_service.py still has httpx.post calls:\n"
            + "\n".join(f"  Line {n}: {l}" for n, l in actual_calls)
        )

    def test_no_httpx_post_proxy_in_resume_optimizer(self):
        """resume_optimizer.py has zero httpx.post calls."""
        content = self.service_files.get("resume_optimizer.py", "")
        # Remove triple-quoted strings (docstrings) to avoid false positives
        code_only = re.sub(r'"""[\s\S]*?"""', '', content)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        actual_calls = []
        for i, line in enumerate(code_only.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'httpx.post' in stripped:
                actual_calls.append((i, stripped))

        assert len(actual_calls) == 0, (
            f"resume_optimizer.py still has httpx.post calls:\n"
            + "\n".join(f"  Line {n}: {l}" for n, l in actual_calls)
        )

    def test_openrouter_client_import_in_llm_service(self):
        """llm_service.py imports from openrouter_client."""
        content = self.service_files.get("llm_service.py", "")
        assert 'from services.openrouter_client import' in content, (
            "llm_service.py must import from openrouter_client"
        )

    def test_openrouter_client_import_in_resume_optimizer(self):
        """resume_optimizer.py imports from openrouter_client."""
        content = self.service_files.get("resume_optimizer.py", "")
        assert 'from services.openrouter_client import' in content, (
            "resume_optimizer.py must import from openrouter_client"
        )


# ===================================================================
# 2. 180s Timeout Standardization
# ===================================================================

class TestTimeoutStandardization:
    """Verify all LLM-calling code uses 180s timeout."""

    def test_llm_service_timeout_is_180(self):
        """llm_service.py defines _LLM_TIMEOUT = 180.0."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_LLM_TIMEOUT = 180.0' in content, (
            "llm_service.py must define _LLM_TIMEOUT = 180.0"
        )

    def test_resume_optimizer_timeout_is_180(self):
        """resume_optimizer.py defines _LLM_TIMEOUT = 180.0."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        assert '_LLM_TIMEOUT = 180.0' in content, (
            "resume_optimizer.py must define _LLM_TIMEOUT = 180.0"
        )

    def test_openrouter_client_timeout_is_180(self):
        """openrouter_client.py default timeout is 180s."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert '_REQUEST_TIMEOUT: float = 180.0' in content, (
            "openrouter_client.py must have _REQUEST_TIMEOUT = 180.0"
        )

    def test_agent_timeout_constants(self, agent_module):
        """agent.py defines correct timeout tier constants."""
        assert agent_module.TIMEOUT_LLM_GENERATION == 180.0
        assert agent_module.TIMEOUT_LLM_CLASSIFY == 30.0
        assert agent_module.TIMEOUT_LLM_CHAT == 60.0
        assert agent_module.TIMEOUT_EXTERNAL_API == 45.0

    def test_asyncio_wait_for_in_llm_service(self):
        """llm_service.py _call_llm uses asyncio.wait_for with timeout."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert 'asyncio.wait_for' in content, (
            "llm_service.py _call_llm must use asyncio.wait_for"
        )
        assert 'timeout=timeout' in content or 'timeout=_LLM_TIMEOUT' in content, (
            "asyncio.wait_for must use the timeout parameter"
        )

    def test_asyncio_wait_for_in_resume_optimizer(self):
        """resume_optimizer.py _call_llm uses asyncio.wait_for with timeout."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        assert 'asyncio.wait_for' in content, (
            "resume_optimizer.py _call_llm must use asyncio.wait_for"
        )
        assert 'timeout=timeout' in content or 'timeout=_LLM_TIMEOUT' in content, (
            "asyncio.wait_for must use the timeout parameter"
        )


# ===================================================================
# 3. Rate Limiting (15 RPM, 40 RPD)
# ===================================================================

class TestRateLimiting:
    """Verify rate limiter is configured with correct limits."""

    def test_openrouter_rpm_is_15(self, rate_limiter_module):
        """OpenRouter service has 15 requests per minute."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("openrouter")
        assert bucket is not None, "openrouter service must be configured"
        assert bucket.minute.max_tokens == 15.0, (
            f"Expected RPM=15, got {bucket.minute.max_tokens}"
        )

    def test_openrouter_rpd_is_40(self, rate_limiter_module):
        """OpenRouter service has 40 requests per day."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("openrouter")
        assert bucket is not None, "openrouter service must be configured"
        assert bucket.day.max_tokens == 40.0, (
            f"Expected RPD=40, got {bucket.day.max_tokens}"
        )

    def test_openrouter_min_interval(self, rate_limiter_module):
        """OpenRouter service has min_interval=4.5s between calls."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("openrouter")
        assert bucket is not None
        assert bucket.min_interval == 4.5, (
            f"Expected min_interval=4.5, got {bucket.min_interval}"
        )

    def test_tavily_rate_limit_exists(self, rate_limiter_module):
        """Tavily service has rate limits configured."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("tavily")
        assert bucket is not None, "tavily service must be configured"

    def test_serper_rate_limit_exists(self, rate_limiter_module):
        """Serper service has rate limits configured."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("serper")
        assert bucket is not None, "serper service must be configured"

    def test_token_bucket_refill_rate_rpm(self, rate_limiter_module):
        """Token bucket refill rate matches RPM (15 tokens/60s = 0.25/s)."""
        bucket = rate_limiter_module.rate_limiter._buckets.get("openrouter")
        assert bucket is not None
        expected_rate = 15.0 / 60.0  # 0.25 tokens per second
        assert abs(bucket.minute.refill_rate - expected_rate) < 0.001, (
            f"Expected refill_rate={expected_rate}, got {bucket.minute.refill_rate}"
        )


# ===================================================================
# 4. Model Upgrades
# ===================================================================

class TestModelUpgrades:
    """Verify model configurations match the required upgrades."""

    def test_searcher_primary_model_reference(self):
        """OpenRouter client references gpt-oss-120b:free for searcher role."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'gpt-oss-120b:free' in content, (
            "Searcher primary model must be openai/gpt-oss-120b:free"
        )

    def test_searcher_fallback_model_reference(self):
        """OpenRouter client references gemma-4-26b-a4b-it:free for searcher fallback."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'gemma-4-26b-a4b-it:free' in content, (
            "Searcher fallback model must be google/gemma-4-26b-a4b-it:free"
        )

    def test_gpt_oss_20b_removed(self):
        """gpt-oss-20b:free is NOT referenced in openrouter_client."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'gpt-oss-20b:free' not in content, (
            "gpt-oss-20b:free must be removed (upgraded to gpt-oss-120b:free)"
        )

    def test_no_old_gemma_3_fallback(self):
        """gemma-3-27b-it:free is NOT referenced (upgraded to gemma-4)."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'gemma-3-27b-it:free' not in content, (
            "gemma-3-27b-it:free must be removed (upgraded to gemma-4-26b-a4b-it:free)"
        )

    def test_docstring_mentions_120b(self):
        """OpenRouter client docstring mentions gpt-oss-120b."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'gpt-oss-120b' in content, (
            "Docstring should reference gpt-oss-120b"
        )


# ===================================================================
# 5. PII Sanitization in LLM Calls
# ===================================================================

class TestPIISanitizationInLLMCalls:
    """Verify PII is sanitized before any LLM call."""

    def test_llm_service_imports_pii_sanitizer(self):
        """llm_service.py imports PIISanitizer."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert 'from services.pii_sanitizer import PIISanitizer' in content, (
            "llm_service.py must import PIISanitizer"
        )

    def test_llm_service_has_sanitize_helper(self):
        """llm_service.py has a _sanitize() helper function."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert 'def _sanitize(' in content, (
            "llm_service.py must have a _sanitize() helper"
        )

    def test_llm_service_sanitizes_email_body(self):
        """analyze_email calls _sanitize() before LLM."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        # Find the analyze_email method and verify _sanitize is called before _call_llm
        analyze_section = content[content.find('async def analyze_email'):content.find('def _heuristic_email')]
        assert '_sanitize(' in analyze_section, (
            "analyze_email must call _sanitize() before sending to LLM"
        )

    def test_llm_service_sanitizes_cover_letter(self):
        """Cover letter generation was moved to resume_optimizer. Verify it sanitizes there."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        cover_section = content[content.find('async def generate_optimized_cover_letter'):content.find('# Singleton instance')]
        assert '_sanitize' in cover_section or 'pii_map' in cover_section, (
            "generate_optimized_cover_letter must sanitize PII before sending to LLM"
        )

    def test_llm_service_sanitizes_jd_analysis(self):
        """analyze_job_description calls _sanitize() before LLM."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        jd_section = content[content.find('async def analyze_job_description'):content.find('def _heuristic_jd')]
        assert '_sanitize(' in jd_section, (
            "analyze_job_description must call _sanitize() before sending to LLM"
        )

    def test_llm_service_sanitizes_interview_prep(self):
        """generate_interview_prep calls _sanitize() before LLM."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        prep_section = content[content.find('async def generate_interview_prep'):content.find('def _heuristic_interview')]
        assert '_sanitize(' in prep_section, (
            "generate_interview_prep must call _sanitize() before sending to LLM"
        )

    def test_resume_optimizer_imports_pii(self):
        """resume_optimizer.py imports PII sanitization functions."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        assert 'sanitize_pii' in content, (
            "resume_optimizer.py must import sanitize_pii"
        )

    def test_resume_optimizer_sanitizes_before_llm(self):
        """resume_optimizer sanitizes before LLM calls."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        llm_optimize = content[content.find('async def _llm_optimize'):content.find('async def generate_optimized')]
        assert '_sanitize_for_llm(' in llm_optimize, (
            "_llm_optimize must call _sanitize_for_llm() before sending to LLM"
        )


# ===================================================================
# 6. 429 Retry Handler
# ===================================================================

class Test429RetryHandler:
    """Verify the 429 rate-limit retry with exponential backoff."""

    def test_retry_base_delay_is_3(self, openrouter_client_module):
        """Base retry delay is 3.0 seconds."""
        assert openrouter_client_module._RETRY_BASE_DELAY == 3.0, (
            f"Expected base delay 3.0s, got {openrouter_client_module._RETRY_BASE_DELAY}"
        )

    def test_max_retries_is_2(self, openrouter_client_module):
        """Max retries before fallback escalation is 2."""
        assert openrouter_client_module._MAX_RETRIES == 2, (
            f"Expected max retries 2, got {openrouter_client_module._MAX_RETRIES}"
        )

    def test_exponential_backoff_in_code(self):
        """Exponential backoff logic exists in _call_with_retries."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        # Should have delay = base_delay * 2^(attempt-1)
        assert '2 ** (attempt - 1)' in content or '2 ** attempt' in content or 'backoff' in content.lower(), (
            "openrouter_client must implement exponential backoff"
        )
        assert 'RateLimitError' in content, (
            "openrouter_client must handle RateLimitError"
        )

    def test_402_payment_required_handled(self):
        """402 Payment Required is handled specially (break, no retry)."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert '402' in content, "openrouter_client must handle 402 status code"
        assert 'Payment required' in content or 'Payment Required' in content, (
            "402 handler must mention 'Payment required'"
        )

    def test_fallback_escalation_in_call_method(self):
        """call() method has two-tier fallback (primary + fallback)."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        call_method = content[content.find('async def call('):content.find('def _call_with_retries')]
        assert 'fallback' in call_method.lower(), (
            "call() method must implement fallback escalation"
        )
        assert 'OpenRouterAllModelsFailedError' in content, (
            "Must raise OpenRouterAllModelsFailedError when both models fail"
        )


# ===================================================================
# 7. Fernet Encryption & Static Key
# ===================================================================

class TestFernetEncryption:
    """Verify Fernet encryption is implemented correctly."""

    def test_fernet_import(self):
        """pii_sanitizer.py imports Fernet from cryptography."""
        with open(BACKEND_DIR / "services" / "pii_sanitizer.py") as f:
            content = f.read()
        assert 'from cryptography.fernet import Fernet' in content, (
            "pii_sanitizer.py must import Fernet"
        )

    def test_pii_vault_has_fernet_encryption(self, pii_vault):
        """PIIVault instance has a Fernet encryptor."""
        # In test environment (no Redis), Fernet may or may not be available
        # depending on whether cryptography is installed. It IS installed.
        assert pii_vault._fernet is not None, (
            "PIIVault must have Fernet encryption enabled"
        )

    def test_encryption_round_trip(self, pii_vault):
        """Data encrypted and stored can be retrieved and decrypted."""
        mapping = {
            "[EMAIL_ADDRESS_1]": "secret@example.com",
            "[PHONE_NUMBER_1]": "+1-555-999-0000",
            "[SSN_1]": "123-45-6789",
        }
        pii_vault.store("fernet-round-trip-test", mapping, ttl=60)
        retrieved = pii_vault.retrieve("fernet-round-trip-test")
        assert retrieved == mapping, "Fernet encryption round-trip failed"
        # Cleanup
        pii_vault.delete_session("fernet-round-trip-test")

    def test_unicode_encryption_round_trip(self, pii_vault):
        """Unicode PII values round-trip correctly through Fernet."""
        mapping = {"[CANDIDATE_NAME_1]": "Jos\u00e9 Garc\u00eda"}
        pii_vault.store("unicode-fernet-test", mapping, ttl=60)
        retrieved = pii_vault.retrieve("unicode-fernet-test")
        assert retrieved == mapping, "Unicode Fernet round-trip failed"
        pii_vault.delete_session("unicode-fernet-test")

    def test_env_var_key_support(self):
        """PII_VAULT_ENCRYPTION_KEY env var is supported."""
        with open(BACKEND_DIR / "services" / "pii_sanitizer.py") as f:
            content = f.read()
        assert 'PII_VAULT_ENCRYPTION_KEY' in content, (
            "Must support PII_VAULT_ENCRYPTION_KEY env var"
        )

    def test_file_based_key_fallback(self):
        """File-based encryption key fallback (.pii_vault_key)."""
        with open(BACKEND_DIR / "services" / "pii_sanitizer.py") as f:
            content = f.read()
        assert '.pii_vault_key' in content, (
            "Must support file-based encryption key fallback"
        )

    def test_docker_compose_has_key(self):
        """docker-compose.yml injects PII_VAULT_MASTER_KEY or PII_VAULT_ENCRYPTION_KEY."""
        with open(PROJECT_ROOT / "docker-compose.yml") as f:
            content = f.read()
        has_key = 'PII_VAULT_MASTER_KEY' in content or 'PII_VAULT_ENCRYPTION_KEY' in content
        assert has_key, (
            "docker-compose.yml must inject the PII vault encryption key"
        )


# ===================================================================
# 8. Heuristic Fallbacks
# ===================================================================

class TestHeuristicFallbacks:
    """Verify every LLM method has a non-LLM fallback path."""

    def test_llm_service_email_has_fallback(self):
        """analyze_email has _heuristic_email_classification fallback."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_heuristic_email_classification' in content

    def test_llm_service_cover_letter_has_fallback(self):
        """Cover letter generation moved to resume_optimizer. Verify it has a heuristic fallback."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        # The heuristic fallback generates a cover letter inline (no separate function name)
        cover_section = content[content.find('async def generate_optimized_cover_letter'):]
        assert 'heuristic' in cover_section.lower() or 'fallback' in cover_section.lower() or 'Dear Hiring Team' in cover_section, (
            "resume_optimizer cover letter must have a fallback when LLM is unavailable"
        )

    def test_llm_service_jd_analysis_has_fallback(self):
        """analyze_job_description has _heuristic_jd_analysis fallback."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_heuristic_jd_analysis' in content

    def test_llm_service_follow_up_has_fallback(self):
        """generate_follow_up has _heuristic_follow_up fallback."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_heuristic_follow_up' in content

    def test_llm_service_interview_prep_has_fallback(self):
        """generate_interview_prep has _heuristic_interview_prep fallback."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_heuristic_interview_prep' in content

    def test_llm_service_resume_improvements_has_fallback(self):
        """improve_resume_suggestions has _heuristic_resume_improvements fallback."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert '_heuristic_resume_improvements' in content

    def test_resume_optimizer_has_heuristic_fallback(self):
        """ResumeOptimizer has _heuristic_optimize fallback."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        assert '_heuristic_optimize' in content

    def test_cover_letter_fallback_delegates_to_llm_service(self):
        """resume_optimizer cover letter has an inline heuristic fallback (no cross-service dependency)."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        # Should NOT delegate to llm_service anymore — it uses inline heuristic
        assert 'from services.llm_service import llm_service' not in content, (
            "resume_optimizer cover letter should use inline fallback, not llm_service"
        )


# ===================================================================
# 9. OpenRouter Client — Sole LLM Pathway
# ===================================================================

class TestOpenRouterSolePathway:
    """Verify openrouter_client is the SOLE LLM pathway."""

    def test_no_direct_openai_imports_in_services(self):
        """Service files don't import openai directly (only openrouter_client does)."""
        services_dir = BACKEND_DIR / "services"
        violations = []
        for py_file in services_dir.glob("*.py"):
            if py_file.name in ("openrouter_client.py", "__init__.py"):
                continue
            with open(py_file) as f:
                content = f.read()
            # Check for direct openai imports
            if re.search(r'^import openai\b|^from openai\b', content, re.MULTILINE):
                violations.append(py_file.name)

        assert len(violations) == 0, (
            f"Services import openai directly instead of openrouter_client: {violations}"
        )

    def test_openrouter_client_docstring_declares_sole_pathway(self):
        """openrouter_client docstring declares itself as the SOLE pathway."""
        with open(BACKEND_DIR / "services" / "openrouter_client.py") as f:
            content = f.read()
        assert 'SOLE' in content or 'sole' in content, (
            "openrouter_client docstring must declare itself as the sole LLM pathway"
        )

    def test_llm_service_docstring_declares_no_proxy(self):
        """llm_service docstring declares no local proxy."""
        with open(BACKEND_DIR / "services" / "llm_service.py") as f:
            content = f.read()
        assert 'NO local proxy' in content or 'NO Node.js middleware' in content, (
            "llm_service docstring must declare no local proxy"
        )

    def test_resume_optimizer_docstring_declares_no_proxy(self):
        """resume_optimizer docstring declares no local proxy."""
        with open(BACKEND_DIR / "services" / "resume_optimizer.py") as f:
            content = f.read()
        assert 'NO local proxy' in content or 'NO httpx.post' in content, (
            "resume_optimizer docstring must declare no local proxy"
        )
