"""
TALVEX OpenRouter Multi-Agent LLM Client with Fallback Architecture

Routes chat-completion requests to distinct OpenRouter models based on
agent role (searcher, parser, architect, builder).  Implements a two-tier
fallback strategy:

  1. Primary model — up to MAX_RETRIES (2) attempts with exponential back-off.
  2. Fallback model — 1 attempt if the primary exhausts all retries.

Model tier assignment (all free-tier on OpenRouter):

  Conversation / Router Layer:
    searcher  — PRIMARY: openai/gpt-oss-120b:free
                FALLBACK: google/gemma-4-26b-a4b-it:free

  Parsing / Generation Layer:
    parser    — PRIMARY: deepseek/deepseek-v4-flash:free
                FALLBACK: qwen/qwen3-coder:free
    builder   — PRIMARY: deepseek/deepseek-v4-flash:free
                FALLBACK: qwen/qwen3-coder:free

  Deep Analysis Layer:
    architect — PRIMARY: openai/gpt-oss-120b:free
                FALLBACK: z-ai/glm-4.5-air:free

Requires ``OPENROUTER_API_KEY`` to be set in the environment or ``.env`` file.
Uses the official OpenAI Python SDK pointed at OpenRouter's
OpenAI-compatible endpoint (``https://openrouter.ai/api/v1``).

This is the SOLE LLM pathway for the TALVEX backend.  There is NO
local proxy, NO Node.js middleware, NO ``httpx.post`` to localhost:3001.
All LLM calls in the system MUST route through this module.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env early so that env-vars are available at import time
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Retry / timeout defaults
# MAX_RETRIES = 2 before escalating to fallback (as specified by user)
_MAX_RETRIES: int = 2
_RETRY_BASE_DELAY: float = 3.0  # 3 s → 6 s (slower backoff to respect RPM limits)
_REQUEST_TIMEOUT: float = 180.0  # 3 minutes (matches TIMEOUT_LLM_GENERATION)

# Extra headers required by OpenRouter
_OPENROUTER_EXTRA_HEADERS: dict[str, str] = {
    "HTTP-Referer": "https://talvex.app",
    "X-Title": "TALVEX",
}


# ---------------------------------------------------------------------------
# Agent role enum
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    """
    Each role maps to a dedicated OpenRouter model via env-vars.

    Model tiers (free-tier on OpenRouter):
      - SEARCHER:  gpt-oss-120b    — conversation, intent routing, job hunting
      - PARSER:    deepseek-v4-flash — fast JD parsing, content extraction
      - ARCHITECT: gpt-oss-120b    — deep analysis, ATS scoring, review, research
      - BUILDER:   deepseek-v4-flash — resume content generation, template filling
    """

    SEARCHER = "searcher"
    PARSER = "parser"
    ARCHITECT = "architect"
    BUILDER = "builder"


# Mapping: AgentRole → (primary_env_var, fallback_env_var)
_ROLE_ENV_MAP: dict[AgentRole, tuple[str, str]] = {
    AgentRole.SEARCHER: (
        "OPENROUTER_MODEL_SEARCHER",
        "OPENROUTER_MODEL_SEARCHER_FALLBACK",
    ),
    AgentRole.PARSER: (
        "OPENROUTER_MODEL_PARSER",
        "OPENROUTER_MODEL_PARSER_FALLBACK",
    ),
    AgentRole.ARCHITECT: (
        "OPENROUTER_MODEL_ARCHITECT",
        "OPENROUTER_MODEL_ARCHITECT_FALLBACK",
    ),
    AgentRole.BUILDER: (
        "OPENROUTER_MODEL_BUILDER",
        "OPENROUTER_MODEL_BUILDER_FALLBACK",
    ),
}

# Human-readable tier names for logging
_TIER_NAMES: dict[AgentRole, str] = {
    AgentRole.SEARCHER: "Conversation/Router",
    AgentRole.PARSER: "Parsing/Generation",
    AgentRole.ARCHITECT: "Deep Analysis",
    AgentRole.BUILDER: "Parsing/Generation",
}


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class OpenRouterError(Exception):
    """Base exception for OpenRouter client errors."""


class OpenRouterAuthError(OpenRouterError):
    """Invalid or missing API key."""


class OpenRouterRateLimitError(OpenRouterError):
    """Rate-limit exceeded (HTTP 429)."""


class OpenRouterModelError(OpenRouterError):
    """Requested model not found or unavailable."""


class OpenRouterTimeoutError(OpenRouterError):
    """Request exceeded the timeout deadline."""


class OpenRouterAllModelsFailedError(OpenRouterError):
    """Both primary and fallback models failed."""


# ---------------------------------------------------------------------------
# Token usage tracking (per-role counters)
# ---------------------------------------------------------------------------

class TokenUsageTracker:
    """
    Lightweight in-process tracker for LLM token consumption.

    Tracks per-role: prompt_tokens, completion_tokens, total_tokens, call_count.
    Not persisted to disk — resets on process restart (acceptable for a
    single-user Telegram bot).
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, int]] = {}

    def record(
        self,
        role: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record token usage for a call."""
        key = role
        if key not in self._data:
            self._data[key] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
        self._data[key]["prompt_tokens"] += prompt_tokens
        self._data[key]["completion_tokens"] += completion_tokens
        self._data[key]["total_tokens"] += prompt_tokens + completion_tokens
        self._data[key]["call_count"] += 1

        # Also track per-model usage
        model_key = f"model:{model}"
        if model_key not in self._data:
            self._data[model_key] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
            }
        self._data[model_key]["prompt_tokens"] += prompt_tokens
        self._data[model_key]["completion_tokens"] += completion_tokens
        self._data[model_key]["total_tokens"] += prompt_tokens + completion_tokens
        self._data[model_key]["call_count"] += 1

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Return a snapshot of all token usage data."""
        return dict(self._data)

    def get_role_summary(self, role: str) -> dict[str, int]:
        """Return token usage for a specific role."""
        return dict(self._data.get(role, {}))

    def reset(self) -> None:
        """Clear all tracking data."""
        self._data.clear()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class OpenRouterClient:
    """
    Multi-model LLM client powered by OpenRouter via the OpenAI SDK.

    Two-tier fallback architecture:
      - Primary model: up to MAX_RETRIES (2) attempts with exponential back-off.
      - Fallback model: 1 attempt if primary exhausts all retries.

    Usage::

        client = OpenRouterClient()
        reply  = await client.call(
            model_role="searcher",
            messages=[{"role": "user", "content": "Find jobs for ..."}],
        )

    Requires ``OPENROUTER_API_KEY`` to be set in the environment / .env.
    Raises ``OpenRouterAuthError`` if the key is missing.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_overrides: dict[str, str] | None = None,
        timeout: float = _REQUEST_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        retry_base_delay: float = _RETRY_BASE_DELAY,
    ) -> None:
        """
        Args:
            api_key: OpenRouter API key.  Defaults to the
                ``OPENROUTER_API_KEY`` env-var.
            model_overrides: Optional ``{role: model_id}`` dict to override
                the env-var-based model selection for one or more roles.
            timeout: Per-request HTTP timeout in seconds.
            max_retries: How many times to retry the PRIMARY model before
                escalating to the fallback.  Default: 2.
            retry_base_delay: Base delay in seconds for exponential backoff
                (actual delays: *base*, *base*×2, …).
        """
        self._api_key: str | None = api_key or os.getenv("OPENROUTER_API_KEY")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._token_tracker = TokenUsageTracker()

        # Resolve primary + fallback model IDs --------------------------------
        overrides = model_overrides or {}
        self._models: dict[AgentRole, str] = {}       # primary
        self._fallbacks: dict[AgentRole, str] = {}    # fallback

        for role, (primary_env, fallback_env) in _ROLE_ENV_MAP.items():
            primary_id = overrides.get(role.value) or os.getenv(primary_env, "")
            fallback_id = os.getenv(fallback_env, "")

            if not primary_id:
                logger.warning(
                    "No primary model configured for role=%s (env-var %s is empty).",
                    role.value, primary_env,
                )

            self._models[role] = primary_id
            self._fallbacks[role] = fallback_id

            if fallback_id:
                logger.info(
                    "Role %s: primary=%s, fallback=%s",
                    role.value, primary_id or "(none)", fallback_id,
                )
            else:
                logger.info(
                    "Role %s: primary=%s, fallback=(none)",
                    role.value, primary_id or "(none)",
                )

        # Build the AsyncOpenAI client ----------------------------------------
        self._openai_client: AsyncOpenAI | None = None

        if self._api_key:
            self._openai_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=self._timeout,
                default_headers=_OPENROUTER_EXTRA_HEADERS,
            )
            logger.info(
                "OpenRouter client initialised — key found, routing to "
                "OpenRouter API via OpenAI SDK. "
                "Fallback architecture: 2 retries on primary, then 1 fallback attempt."
            )
        else:
            logger.warning(
                "OpenRouter API key not set — calls will raise OpenRouterAuthError."
            )

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    @property
    def is_openrouter_active(self) -> bool:
        """``True`` when the client will use OpenRouter (key is present)."""
        return self._api_key is not None

    @property
    def models(self) -> dict[str, str]:
        """Return a read-only snapshot of ``{role: primary_model_id}``."""
        return {role.value: mid for role, mid in self._models.items()}

    @property
    def fallback_models(self) -> dict[str, str]:
        """Return a read-only snapshot of ``{role: fallback_model_id}``."""
        return {role.value: mid for role, mid in self._fallbacks.items()}

    @property
    def token_usage(self) -> TokenUsageTracker:
        """Access the token usage tracker."""
        return self._token_tracker

    async def call(
        self,
        model_role: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat-completion request with two-tier fallback.

        Flow:
          1. Try primary model — up to MAX_RETRIES (2) attempts.
          2. If all primary retries fail, try fallback model — 1 attempt.
          3. If fallback also fails, raise OpenRouterAllModelsFailedError.

        Args:
            model_role: One of ``"searcher"``, ``"parser"``, ``"architect"``,
                or ``"builder"``.
            messages: OpenAI-style message list.
            temperature: Sampling temperature (0–2).
            max_tokens: Maximum tokens in the response.
            json_mode: If ``True``, pass ``response_format={{"type": "json_object"}}``
                to the API. This forces the LLM provider to reject non-JSON
                responses at the API level, catching malformed output BEFORE
                it reaches Python's JSON parser.  Use this for ALL call sites
                that expect structured JSON responses.

        Returns:
            The assistant's reply text.

        Raises:
            ValueError: If *model_role* is invalid or no model is configured.
            OpenRouterAuthError: If no API key is configured.
            OpenRouterAllModelsFailedError: If both primary and fallback fail.
            OpenRouterError / subclass: On non-retryable API failures.
        """
        if not self._api_key:
            raise OpenRouterAuthError(
                "OpenRouter API key not configured. "
                "Please set the OPENROUTER_API_KEY environment variable."
            )

        # Validate role -------------------------------------------------------
        try:
            role = AgentRole(model_role)
        except ValueError:
            raise ValueError(
                f"Unknown model_role '{model_role}'. "
                f"Valid roles: {[r.value for r in AgentRole]}"
            )

        primary_id = self._models.get(role, "")
        fallback_id = self._fallbacks.get(role, "")

        if not primary_id:
            raise ValueError(
                f"No primary model configured for role '{role.value}'. "
                f"Set the {_ROLE_ENV_MAP[role][0]} environment variable."
            )

        tier_name = _TIER_NAMES.get(role, role.value)

        # --- Step 1: Try primary model with retries -------------------------
        logger.info(
            "[%s] Calling primary model: %s (max_retries=%d)",
            tier_name, primary_id, self._max_retries,
        )
        try:
            result = await self._call_with_retries(
                model_id=primary_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            logger.info("[%s] Primary model succeeded: %s", tier_name, primary_id)
            return result
        except (OpenRouterAuthError, OpenRouterModelError):
            # Non-retryable errors — don't bother with fallback
            raise
        except OpenRouterError as primary_exc:
            logger.warning(
                "[%s] Primary model %s failed after %d retries: %s",
                tier_name, primary_id, self._max_retries, primary_exc,
            )

        # --- Step 2: Escalate to fallback model -----------------------------
        if not fallback_id:
            logger.error(
                "[%s] No fallback model configured for role '%s'. "
                "Primary exhausted all retries. Failing.",
                tier_name, role.value,
            )
            raise OpenRouterAllModelsFailedError(
                f"[{tier_name}] Primary model '{primary_id}' failed after "
                f"{self._max_retries} retries, and no fallback model is "
                f"configured for role '{role.value}'. "
                f"Last error: {primary_exc}"
            ) from primary_exc

        logger.info(
            "[%s] Escalating to fallback model: %s (1 attempt)",
            tier_name, fallback_id,
        )
        try:
            result = await self._call_with_retries(
                model_id=fallback_id,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                max_attempts=1,  # Only 1 attempt on fallback
                json_mode=json_mode,
            )
            logger.info(
                "[%s] Fallback model succeeded: %s", tier_name, fallback_id,
            )
            return result
        except OpenRouterError as fallback_exc:
            logger.error(
                "[%s] Fallback model %s also failed: %s",
                tier_name, fallback_id, fallback_exc,
            )
            raise OpenRouterAllModelsFailedError(
                f"[{tier_name}] Both models failed. "
                f"Primary '{primary_id}' failed: {primary_exc}. "
                f"Fallback '{fallback_id}' failed: {fallback_exc}."
            ) from fallback_exc

    # -------------------------------------------------------------------
    # Internal: retry loop
    # -------------------------------------------------------------------

    async def _call_with_retries(
        self,
        model_id: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        max_attempts: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """
        Call a specific model with retry + exponential back-off.

        Args:
            model_id: The OpenRouter model identifier.
            messages: OpenAI-style message list.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            max_attempts: Override for max retries (default: self._max_retries).
            json_mode: If True, enforce JSON output at the API level via
                ``response_format={{"type": "json_object"}}``.

        Returns:
            The assistant's reply text.

        Raises:
            OpenRouterError: On failure after all attempts.
        """
        assert self._openai_client is not None

        attempts = max_attempts if max_attempts is not None else self._max_retries
        last_exception: OpenRouterError | None = None

        for attempt in range(1, attempts + 1):
            delay = self._retry_base_delay * (2 ** (attempt - 1))

            try:
                start_time = time.time()
                # Build API kwargs — conditionally enforce JSON mode
                api_kwargs: dict[str, Any] = {
                    "model": model_id,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,  # NEVER stream — Telegram needs complete responses
                }
                if json_mode:
                    api_kwargs["response_format"] = {"type": "json_object"}
                    logger.debug(
                        "Enforcing JSON mode for model=%s (response_format=json_object).",
                        model_id,
                    )

                response = await self._openai_client.chat.completions.create(**api_kwargs)
                elapsed = time.time() - start_time

                # Extract content from the SDK response object
                content = self._extract_sdk_content(response)

                # Track token usage
                self._track_usage(model_id, response, elapsed)

                return content

            except AuthenticationError as exc:
                # Non-retryable — fail fast
                raise OpenRouterAuthError(
                    "OpenRouter authentication failed — check your API key."
                ) from exc

            except NotFoundError as exc:
                # Non-retryable — model not found on this provider
                detail = ""
                if hasattr(exc, "response") and exc.response is not None:
                    try:
                        body = exc.response.json()
                        detail = body.get("error", {}).get("message", "")
                    except Exception:
                        pass
                raise OpenRouterModelError(
                    f"Model '{model_id}' not found on OpenRouter. {detail}"
                ) from exc

            except RateLimitError as exc:
                last_exception = OpenRouterRateLimitError(
                    f"Rate limit hit on '{model_id}' "
                    f"(attempt {attempt}/{attempts})."
                )
                logger.warning(
                    "Rate limited (429) on %s attempt %d/%d — retrying in %.1fs.",
                    model_id, attempt, attempts, delay,
                )
                await asyncio.sleep(delay)
                continue

            except APITimeoutError as exc:
                last_exception = OpenRouterTimeoutError(
                    f"'{model_id}' timed out after {self._timeout}s "
                    f"(attempt {attempt}/{attempts})."
                )
                logger.warning(
                    "Timeout on %s attempt %d/%d — retrying in %.1fs.",
                    model_id, attempt, attempts, delay,
                )
                await asyncio.sleep(delay)
                continue

            except APIStatusError as exc:
                status_code = exc.status_code
                if status_code >= 500:
                    last_exception = OpenRouterError(
                        f"Server error {status_code} on '{model_id}' "
                        f"(attempt {attempt}/{attempts})."
                    )
                    logger.warning(
                        "Server error %d on %s attempt %d/%d — retrying in %.1fs.",
                        status_code, model_id, attempt, attempts, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                        # Non-5xx unexpected error — fail fast
                if status_code == 402:
                    last_exception = OpenRouterError(
                        f"Payment required (402) on '{model_id}'. "
                        "Check OpenRouter account balance."
                    )
                    logger.error("Payment required (402) on %s: %s", model_id, last_exception)
                    break

                last_exception = OpenRouterError(
                    f"Unexpected status {status_code} on '{model_id}': "
                    f"{str(exc)[:300]}"
                )
                logger.error("Unexpected status on %s: %s", model_id, last_exception)
                break

            except APIConnectionError as exc:
                last_exception = OpenRouterError(
                    f"Connection failed to '{model_id}' "
                    f"(attempt {attempt}/{attempts}): {exc}"
                )
                logger.warning(
                    "Connection error on %s attempt %d/%d — retrying in %.1fs.",
                    model_id, attempt, attempts, delay,
                )
                await asyncio.sleep(delay)
                continue

            except OpenRouterError:
                raise

            except Exception as exc:
                last_exception = OpenRouterError(
                    f"Unexpected error on '{model_id}' "
                    f"(attempt {attempt}/{attempts}): {exc}"
                )
                logger.exception("Unexpected error on %s attempt %d.", model_id, attempt)
                await asyncio.sleep(delay)
                continue

        # All attempts exhausted
        raise last_exception or OpenRouterError(
            f"Call to '{model_id}' failed after {attempts} attempts."
        )

    def _track_usage(
        self,
        model_id: str,
        response: Any,
        elapsed: float,
    ) -> None:
        """Extract and record token usage from the API response."""
        try:
            usage = response.usage
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0

                self._token_tracker.record(
                    role=model_id,
                    model=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                logger.info(
                    "Token usage — model=%s: prompt=%d, completion=%d, "
                    "total=%d (%.1fs)",
                    model_id, prompt_tokens, completion_tokens,
                    prompt_tokens + completion_tokens, elapsed,
                )
        except Exception as exc:
            logger.debug("Could not extract token usage: %s", exc)

    @staticmethod
    def _extract_sdk_content(response: Any) -> str:
        """Pull the text content out of an OpenAI SDK ChatCompletion object."""
        try:
            return response.choices[0].message.content.strip()
        except (AttributeError, IndexError, TypeError) as exc:
            raise OpenRouterError(
                f"Unexpected OpenRouter response structure: {exc!s}"
            ) from exc


# ---------------------------------------------------------------------------
# Module-level singleton (follows existing codebase convention)
# ---------------------------------------------------------------------------

openrouter_client = OpenRouterClient()
