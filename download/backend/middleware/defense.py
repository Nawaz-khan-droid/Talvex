"""
TALVEX - Reactive Defense Middleware

Five defense layers for the TALVEX backend:

1. **IPBlocklistMiddleware** (ASGI) — checks a Redis-backed blocklist on every
   request.  Malicious IPs receive an immediate 403 response.  Gracefully
   degrades when Redis is unavailable (allows the request, logs a warning).

2. **SecurityHeadersMiddleware** (ASGI) — injects a comprehensive set of
   Zero Trust security headers (CSP, HSTS, X-Frame-Options, etc.) into
   every HTTP response.

3. **CSRFMiddleware** (ASGI) — double-submit cookie pattern.  State-changing
   requests (POST/PUT/PATCH/DELETE) must include an ``X-CSRF-Token`` header
   that matches the ``talvex_csrf`` cookie value.  Safe methods (GET/HEAD/OPTIONS)
   and auth endpoints are exempt.

4. **Automated IP Ban Logic** (standalone functions) — ``record_suspicious_activity``
   tracks violations per IP in Redis and auto-bans after 3 strikes in 1 hour.
   ``is_ip_blocked`` and ``unblock_ip`` complete the admin toolkit.

5. **Prompt Injection Detection** (standalone functions) — regex-based scanner
   that catches common LLM prompt injection patterns before text reaches the
   model.  ``sanitize_llm_input`` normalises whitespace for cleaner prompts.

Redis key namespace: ``talvex:blocked_ips`` (SET), ``talvex:suspicious:{ip}`` (STRING/JSON).
"""

import json
import logging
import os
import re
import time
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("talvex.defense")

# ============================================================
# Redis connection helper (lazy singleton, graceful degradation)
# ============================================================

_redis_singleton = None


def _get_defense_redis():
    """Return a Redis connection as a lazy singleton.

    Follows the same pattern as ``PIIVault`` in ``pii_sanitizer.py``:
    connects once, reuses the connection for the lifetime of the process.
    Returns ``None`` (instead of raising) if Redis is unavailable.
    """
    global _redis_singleton
    if _redis_singleton is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            _redis_singleton = redis.from_url(redis_url, decode_responses=True)
            _redis_singleton.ping()
            logger.info("Defense module connected to Redis at %s", redis_url)
        except Exception as exc:
            logger.warning(
                "Defense module: Redis connection failed (%s) — "
                "IP blocklist and suspicious-activity tracking will be disabled. "
                "Requests will be allowed through.",
                exc,
            )
            _redis_singleton = None
    return _redis_singleton


# ============================================================
# 1. IP Blocklist Middleware (ASGI)
# ============================================================


class IPBlocklistMiddleware:
    """Checks Redis ``talvex:blocked_ips`` set on every request.

    Blocked IPs receive an immediate ``403 Forbidden`` with a structured
    JSON body (``{"detail": "Access denied", "code": "IP_BLOCKED"}``).

    Graceful degradation: if Redis is unavailable the request is allowed
    through and a warning is logged.  This prevents a Redis outage from
    taking down the entire application.
    """

    def __init__(self, app: ASGIApp, redis_url: str | None = None) -> None:
        self.app = app
        # redis_url is accepted for configurability but _get_defense_redis()
        # always reads from the environment / singleton.
        self._redis = _get_defense_redis()

        if self._redis is not None:
            logger.info("IPBlocklistMiddleware initialised — Redis blocklist active.")
        else:
            logger.warning("IPBlocklistMiddleware initialised WITHOUT Redis — blocklist checks disabled.")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client_ip = self._extract_ip(scope)

        # Check if IP is in Redis set "talvex:blocked_ips"
        if self._redis is not None:
            try:
                if self._redis.sismember("talvex:blocked_ips", client_ip):
                    logger.warning("Blocked request from IP=%s", client_ip)
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "Access denied", "code": "IP_BLOCKED"},
                    )
                    await response(scope, receive, send)
                    return
            except Exception as exc:
                logger.error("IPBlocklistMiddleware: Redis check failed — allowing request: %s", exc)

        await self.app(scope, receive, send)

    # ------------------------------------------------------------------
    # IP extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ip(scope: Scope) -> str:
        """Extract the client IP from ASGI scope.

        Priority:
        1. ``X-Forwarded-For`` header (first IP in the chain)
        2. ``X-Real-IP`` header
        3. ``scope["client"][0]`` (direct connection, falls back to ``127.0.0.1``)
        """
        headers = dict(scope.get("headers", []))

        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = headers.get(b"x-real-ip", b"").decode()
        if real_ip:
            return real_ip.strip()

        return scope.get("client", ("127.0.0.1",))[0]


# ============================================================
# 2. Security Headers Middleware (ASGI)
# ============================================================


class SecurityHeadersMiddleware:
    """Injects Zero Trust security headers into every HTTP response.

    Headers are injected by intercepting the ``send`` callable and
    modifying the ``response_headers`` before they are flushed to the
    client.  Non-HTTP scopes (websockets, lifespan) pass through
    untouched.
    """

    SECURITY_HEADERS: dict[str, str] = {
        # CSP — strict, only allow scripts/styles from self + unsafe-inline for Tailwind
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
        ),
        # HSTS — force HTTPS for 2 years, include subdomains, preload eligible
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        # Prevent MIME type sniffing
        "X-Content-Type-Options": "nosniff",
        # Prevent clickjacking
        "X-Frame-Options": "DENY",
        # XSS protection (legacy browser support, CSP is primary)
        "X-XSS-Protection": "0",  # Disabled in favor of CSP
        # Referrer policy
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # Permissions policy — deny all browser permissions by default
        "Permissions-Policy": (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        ),
    }

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, self._build_send(scope, send))

    def _build_send(self, scope: Scope, send: Send) -> Send:
        """Wrap the original ``send`` callable to inject security headers.

        Starlette/ASGI sends two message types:
        - ``http.response.start`` — contains status code and headers
        - ``http.response.body`` — contains the body bytes

        We intercept ``http.response.start`` and merge in our security
        headers.  ``http.response.body`` passes through unchanged.
        """

        headers_injected = False

        async def send_with_headers(message: dict[str, Any]) -> None:
            nonlocal headers_injected

            if message["type"] == "http.response.start" and not headers_injected:
                # Merge security headers into the existing response headers.
                # ASGI headers are a list of [name_bytes, value_bytes] tuples.
                original_headers: list[tuple[bytes, bytes]] = list(
                    message.get("headers", [])
                )

                # Build a set of already-present header names (lowercased)
                # so we don't duplicate headers that the app may have set.
                existing_names = {name.lower() for name, _ in original_headers}

                for name, value in self.SECURITY_HEADERS.items():
                    if name.lower() not in existing_names:
                        original_headers.append(
                            (name.encode("utf-8"), value.encode("utf-8"))
                        )

                message["headers"] = original_headers
                headers_injected = True

            await send(message)

        return send_with_headers


# ============================================================
# 3. CSRF Middleware (ASGI) — Double-Submit Cookie Pattern
# ============================================================


class CSRFMiddleware:
    """Double-submit cookie pattern for CSRF protection.

    Every state-changing request (POST, PUT, PATCH, DELETE) must include
    an ``X-CSRF-Token`` HTTP header whose value matches the ``talvex_csrf``
    cookie that was set by the auth module on login/register.

    Exemptions:
    - Safe methods: GET, HEAD, OPTIONS
    - Auth endpoints: ``/api/auth/login``, ``/api/auth/register``, ``/api/auth/logout``

    If validation fails, returns ``403 Forbidden`` with
    ``{"detail": "CSRF validation failed", "code": "CSRF_INVALID"}``.
    """

    EXEMPT_PATHS: set[str] = {"/api/auth/login", "/api/auth/register", "/api/auth/logout"}
    SAFE_METHODS: set[str] = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"].upper()
        path: str = scope["path"]

        # Exempt safe methods and auth endpoints
        if method in self.SAFE_METHODS or path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # For state-changing requests: verify X-CSRF-Token header matches CSRF cookie
        headers = dict(scope.get("headers", []))
        csrf_header = headers.get(b"x-csrf-token", b"").decode()
        csrf_cookie = self._extract_cookie(headers, "talvex_csrf")

        if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
            logger.warning(
                "CSRF validation failed for %s %s (header=%s, cookie=%s)",
                method, path,
                "present" if csrf_header else "missing",
                "present" if csrf_cookie else "missing",
            )
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed", "code": "CSRF_INVALID"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_cookie(headers: dict[bytes, bytes], cookie_name: str) -> str:
        """Extract a named cookie from the ``Cookie`` header bytes.

        Returns the cookie value as a string, or an empty string if not found.
        """
        cookie_header = headers.get(b"cookie", b"").decode()
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{cookie_name}="):
                return part[len(cookie_name) + 1:]
        return ""


# ============================================================
# 4. Automated IP Ban Logic (Standalone Functions)
# ============================================================

_SUSPICIOUS_TTL = 3600  # 1 hour in seconds
_AUTO_BAN_THRESHOLD = 3  # Auto-ban after this many violations


def record_suspicious_activity(
    ip: str,
    redis_client: Any,
    reason: str = "auth_failure",
) -> int:
    """Track suspicious activity per IP.  Auto-ban after 3 violations in 1 hour.

    Redis key: ``talvex:suspicious:{ip}``
    - Value: JSON list of ``{"ts": <epoch>, "reason": <string>}`` objects
    - TTL: 3600 seconds (1 hour)
    - If count reaches ``_AUTO_BAN_THRESHOLD`` (3): ``SADD talvex:blocked_ips {ip}``

    Args:
        ip: The client IP address.
        redis_client: An active ``redis.Redis`` connection instance.
        reason: A short label describing why this event was recorded
                (e.g. ``"auth_failure"``, ``"rate_limit"``, ``"injection_attempt"``).

    Returns:
        The current violation count (after this recording).
    """
    key = f"talvex:suspicious:{ip}"

    # Fetch existing violations (may be None if key expired or doesn't exist)
    raw = redis_client.get(key)
    if raw is not None:
        try:
            violations: list[dict[str, Any]] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Corrupt suspicious-activity data for IP=%s — resetting", ip)
            violations = []
    else:
        violations = []

    # Append new violation
    violations.append({
        "ts": time.time(),
        "reason": reason,
    })

    # Persist with TTL
    try:
        redis_client.setex(key, _SUSPICIOUS_TTL, json.dumps(violations))
    except Exception as exc:
        logger.error("Failed to record suspicious activity for IP=%s: %s", ip, exc)
        return len(violations)

    count = len(violations)

    # Auto-ban if threshold reached
    if count >= _AUTO_BAN_THRESHOLD:
        try:
            added = redis_client.sadd("talvex:blocked_ips", ip)
            if added:
                logger.warning(
                    "AUTO-BAN: IP=%s has been blocked after %d violations "
                    "(reason=%s).  Added to talvex:blocked_ips.",
                    ip, count, reason,
                )
        except Exception as exc:
            logger.error("Failed to auto-ban IP=%s: %s", ip, exc)

    return count


def is_ip_blocked(ip: str, redis_client: Any) -> bool:
    """Check whether an IP address is in the blocklist.

    Args:
        ip: The client IP address to check.
        redis_client: An active ``redis.Redis`` connection instance.

    Returns:
        ``True`` if the IP is blocked, ``False`` otherwise.
    """
    try:
        return bool(redis_client.sismember("talvex:blocked_ips", ip))
    except Exception as exc:
        logger.error("Failed to check blocklist for IP=%s: %s", ip, exc)
        return False


def unblock_ip(ip: str, redis_client: Any) -> bool:
    """Remove an IP address from the blocklist.

    Also clears the associated ``talvex:suspicious:{ip}`` key so that
    the violation counter resets.

    Args:
        ip: The client IP address to unblock.
        redis_client: An active ``redis.Redis`` connection instance.

    Returns:
        ``True`` if the IP was in the blocklist and has been removed,
        ``False`` if it was not blocked (no-op).
    """
    try:
        was_blocked = bool(redis_client.sismember("talvex:blocked_ips", ip))
    except Exception as exc:
        logger.error("Failed to check blocklist before unblock for IP=%s: %s", ip, exc)
        return False

    if was_blocked:
        try:
            redis_client.srem("talvex:blocked_ips", ip)
            redis_client.delete(f"talvex:suspicious:{ip}")
            logger.info("IP=%s has been unblocked and violation history cleared.", ip)
        except Exception as exc:
            logger.error("Failed to unblock IP=%s: %s", ip, exc)
            return False

    return was_blocked


# ============================================================
# 5. Prompt Injection Detection (Standalone Functions)
# ============================================================

# Patterns that indicate prompt injection attempts against LLM endpoints.
# Each entry is a compiled regex; the pattern string is stored as the
# ``pattern`` attribute for use in user-facing error messages.
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"you\s+are\s+now", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"roleplay\s+as", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"dAN\s*,?\s*your\s+(task|mission|objective)", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"</s>", re.IGNORECASE),
    re.compile(r"<\/instruction>", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"output\s+the\s+(above|following)", re.IGNORECASE),
]


def check_prompt_injection(text: str) -> tuple[bool, list[str]]:
    """Check text for prompt injection patterns.

    Scans the input against all patterns in ``INJECTION_PATTERNS`` and
    returns which patterns matched.

    Args:
        text: The user-supplied text to scan (e.g. a job description,
              cover letter draft, or chat message).

    Returns:
        A 2-tuple ``(is_malicious, matched_patterns)`` where:
        - ``is_malicious`` is ``True`` if any pattern matched.
        - ``matched_patterns`` is a list of the regex pattern strings
          that triggered (human-readable for error messages / logging).

    Usage in LLM endpoints::

        is_malicious, patterns = check_prompt_injection(job_description)
        if is_malicious:
            raise HTTPException(
                400,
                detail=f"Input contains suspicious patterns: {', '.join(patterns)}"
            )
    """
    if not text:
        return False, []

    matched: list[str] = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            matched.append(pattern.pattern)

    is_malicious = len(matched) > 0

    if is_malicious:
        logger.warning(
            "Prompt injection detected — %d pattern(s) matched: %s",
            len(matched),
            ", ".join(matched),
        )

    return is_malicious, matched


def sanitize_llm_input(text: str) -> str:
    """Sanitize input before sending to an LLM.

    Performs:
    - Strip leading/trailing whitespace
    - Collapse consecutive whitespace characters into a single space
    - Strip leading/trailing whitespace again (after collapsing)

    This produces clean, normalised input for the model without
    altering the semantic content.

    Args:
        text: Raw user input.

    Returns:
        The sanitised string.
    """
    if not text:
        return ""
    # Collapse all whitespace runs (spaces, tabs, newlines) into single spaces
    normalized = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    return normalized.strip()
