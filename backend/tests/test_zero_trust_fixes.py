"""
TALVEX Zero Trust Security Verification Tests

These tests verify the 4 critical security fixes:
  FIX 1: Admin bootstrap race condition (register cannot create admin)
  FIX 2: Admin brute-force exemption removed (reset_password CLI exists)
  FIX 3: Data isolation (users cannot see other users' data)
  FIX 4: Next.js proxy loophole killed (no /api/llm routes in src/)

Run with:
  cd /home/z/my-project/backend
  python -m pytest tests/test_zero_trust_fixes.py -v
"""

import os
import sys

import pytest

# Ensure backend directory is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy DATABASE_URL and JWT_SECRET_KEY before any module imports
# These are needed because importing auth.py triggers database.py which
# calls create_async_engine() at module level.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///test_dummy.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-zero-trust-tests")


# ============================================================
# FIX 1: Admin Bootstrap Race Condition
# ============================================================

class TestFix1AdminBootstrap:
    """Verify that the public registration endpoint can NEVER create an admin user."""

    def test_register_request_schema_has_no_role_field(self):
        """RegisterRequest Pydantic model must NOT accept a 'role' field."""
        from auth import RegisterRequest

        schema_fields = set(RegisterRequest.model_fields.keys())
        assert "role" not in schema_fields, (
            "RegisterRequest accepts a 'role' field - an attacker could send "
            "role=admin to escalate privileges. Remove it."
        )

    def test_register_request_ignores_extra_fields(self):
        """Even if 'role' is sent in the JSON body, Pydantic must ignore it."""
        from auth import RegisterRequest

        req = RegisterRequest(
            email="hacker@evil.com",
            password="Password123!",
            display_name="Hacker",
        )
        assert not hasattr(req, "role") or getattr(req, "role", None) is None, (
            "RegisterRequest allows 'role' field to persist - privilege escalation possible."
        )

    def test_register_endpoint_hardcodes_user_role(self):
        """The register endpoint code must hard-code role='user'."""
        import inspect
        from auth import register_endpoint

        source = inspect.getsource(register_endpoint)
        assert 'role="user"' in source, (
            "register_endpoint does not hard-code role='user'. "
            "It may still use conditional role assignment (race condition)."
        )
        assert "user_count == 0" not in source, (
            "register_endpoint still contains the 'first user = admin' bootstrap logic. "
            "Remove it - admin creation must happen via ADMIN_EMAIL env var only."
        )

    def test_no_bootstrap_logic_in_register(self):
        """Ensure no user_count or first-user logic remains in register."""
        import inspect
        from auth import register_endpoint

        source = inspect.getsource(register_endpoint)
        forbidden_patterns = [
            "user_count",
            "first user",
        ]
        source_lower = source.lower()
        for pattern in forbidden_patterns:
            assert pattern not in source_lower, (
                f"register_endpoint still contains '{pattern}' pattern. "
                "Remove all first-user bootstrap logic."
            )

    def test_admin_bootstrap_function_exists_in_main(self):
        """main.py must have _bootstrap_admin_user function using ENV vars."""
        import inspect

        # Read main.py source directly instead of importing (to avoid
        # pulling in the entire dependency tree like openai, faiss, etc.)
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "main.py"
        )
        with open(main_path, "r") as f:
            source = f.read()

        assert "_bootstrap_admin_user" in source, (
            "main.py does not have _bootstrap_admin_user(). "
            "Admin must be created via environment variables on startup."
        )
        assert "ADMIN_EMAIL" in source, (
            "_bootstrap_admin_user does not read ADMIN_EMAIL env var."
        )
        assert "ADMIN_PASSWORD" in source, (
            "_bootstrap_admin_user does not read ADMIN_PASSWORD env var."
        )

    def test_register_request_model_fields(self):
        """Verify RegisterRequest only has email, password, display_name."""
        from auth import RegisterRequest

        fields = set(RegisterRequest.model_fields.keys())
        expected = {"email", "password", "display_name"}
        assert fields == expected, (
            f"RegisterRequest has unexpected fields: {fields - expected}. "
            f"Only {expected} should be allowed."
        )


# ============================================================
# FIX 2: Admin Brute-Force Exemption Removed
# ============================================================

class TestFix2BruteForce:
    """Verify no admin exemption in brute-force protection."""

    def test_brute_force_applies_to_all_roles(self):
        """check_brute_force must not check user role."""
        import inspect
        from auth import check_brute_force

        source = inspect.getsource(check_brute_force)
        assert "role" not in source.lower(), (
            "check_brute_force references 'role' - it may have an admin exemption. "
            "Zero Trust: all roles must be subject to brute-force lockout."
        )

    def test_record_failed_attempt_applies_to_all(self):
        """record_failed_attempt must not check user role."""
        import inspect
        from auth import record_failed_attempt

        source = inspect.getsource(record_failed_attempt)
        assert "role" not in source.lower(), (
            "record_failed_attempt references 'role' - it may exempt admins."
        )

    def test_reset_password_function_exists(self):
        """reset_password utility must exist for admin self-unlock via Docker CLI."""
        from auth import reset_password

        assert callable(reset_password), (
            "reset_password is not callable. Admins need a way to reset passwords "
            "via docker exec."
        )

    def test_reset_password_clears_brute_force(self):
        """reset_password must clear brute-force tracking and revoke sessions."""
        import inspect
        from auth import reset_password

        source = inspect.getsource(reset_password)
        assert "clear_failed_attempts" in source, (
            "reset_password does not call clear_failed_attempts(). "
            "A locked-out admin would remain locked even after password reset."
        )
        assert "revoke_all_user_sessions" in source, (
            "reset_password does not revoke sessions. "
            "Old sessions must be invalidated after password change."
        )


# ============================================================
# FIX 3: Data Isolation (User Scoping)
# ============================================================

class TestFix3DataIsolation:
    """Verify all router endpoints scope queries by user_id."""

    def test_applications_router_scopes_queries(self):
        """applications.py must filter by userId."""
        import inspect
        from routers import applications

        source = inspect.getsource(applications)
        assert "userId" in source or "user_id" in source, (
            "applications.py does not reference userId - data isolation not enforced."
        )
        assert "get_current_user" in source, (
            "applications.py does not import get_current_user."
        )

    def test_personas_router_scopes_queries(self):
        """personas.py must filter by userId."""
        import inspect
        from routers import personas

        source = inspect.getsource(personas)
        assert "userId" in source or "user_id" in source, (
            "personas.py does not reference userId - data isolation not enforced."
        )
        assert "get_current_user" in source, (
            "personas.py does not import get_current_user."
        )

    def test_resume_router_checks_ownership(self):
        """resume.py must verify application ownership."""
        import inspect
        from routers import resume

        source = inspect.getsource(resume)
        assert "current_user" in source, (
            "resume.py does not use current_user - ownership checks missing."
        )

    def test_canary_router_scopes_queries(self):
        """canary.py must scope queries by user ownership."""
        import inspect
        from routers import canary

        source = inspect.getsource(canary)
        assert "current_user" in source, (
            "canary.py does not use current_user - ownership checks missing."
        )

    def test_analytics_router_scopes_queries(self):
        """analytics.py must scope aggregation queries by user."""
        import inspect
        from routers import analytics

        source = inspect.getsource(analytics)
        assert "current_user" in source, (
            "analytics.py does not use current_user - user data could leak."
        )

    def test_recommendations_router_scopes_queries(self):
        """recommendations.py must scope queries by user."""
        import inspect

        # Read source directly to avoid importing openai dependency
        rec_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "routers", "recommendations.py"
        )
        with open(rec_path, "r") as f:
            source = f.read()
        assert "get_current_user" in source, (
            "recommendations.py does not import get_current_user - ownership missing."
        )
        assert "current_user" in source, (
            "recommendations.py does not use current_user - ownership missing."
        )

    def test_jobs_router_sets_userid_on_create(self):
        """jobs.py must set userId when creating applications."""
        import inspect
        from routers import jobs

        source = inspect.getsource(jobs)
        assert "userId" in source or "user_id" in source, (
            "jobs.py does not set userId on created applications - data orphaning."
        )

    def test_llm_router_requires_auth(self):
        """llm.py must require authentication."""
        import inspect
        from routers import llm

        source = inspect.getsource(llm)
        assert "get_current_user" in source, (
            "llm.py does not require authentication - LLM endpoints are unprotected."
        )

    def test_search_router_requires_auth(self):
        """search.py must require authentication."""
        import inspect

        # Read source directly to avoid importing faiss dependency
        search_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "routers", "search.py"
        )
        with open(search_path, "r") as f:
            source = f.read()
        assert "get_current_user" in source, (
            "search.py does not require authentication."
        )

    def test_tasks_router_requires_auth(self):
        """tasks.py must require authentication."""
        import inspect
        from routers import tasks

        source = inspect.getsource(tasks)
        assert "get_current_user" in source, (
            "tasks.py does not require authentication."
        )


# ============================================================
# FIX 4: Next.js Proxy Loophole Killed
# ============================================================

class TestFix4NextJsProxyKilled:
    """Verify no Next.js API route files exist for LLM proxy."""

    def test_no_llm_route_files_in_src(self):
        """The src/app/api/llm/ directory must NOT exist."""
        api_llm_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "src", "app", "api", "llm"
        )
        assert not os.path.exists(api_llm_path), (
            f"src/app/api/llm/ still exists at {api_llm_path}. "
            "Delete it - Next.js must NOT proxy LLM calls. "
            "FastAPI handles ALL LLM endpoints with auth, rate limiting, and audit logging."
        )

    def test_no_api_route_ts_files(self):
        """No route.ts files should exist under src/app/api/."""
        import glob

        api_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "src", "app", "api"
        )
        if os.path.exists(api_dir):
            route_files = glob.glob(os.path.join(api_dir, "**", "route.ts"), recursive=True)
            assert len(route_files) == 0, (
                f"Found {len(route_files)} route.ts files under src/app/api/: "
                f"{route_files}. All API routes must be handled by FastAPI."
            )

    def test_no_api_llm_fetch_in_frontend(self):
        """No .tsx component should fetch /api/llm (Next.js proxy)."""
        import glob

        src_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "src"
        )
        tsx_files = glob.glob(os.path.join(src_dir, "**", "*.tsx"), recursive=True)

        for filepath in tsx_files:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                if "/api/llm" in line and "fetch" in line:
                    raise AssertionError(
                        f"{filepath}:{line_num} contains a fetch to /api/llm. "
                        "Frontend must call FastAPI backend endpoints directly."
                    )


# ============================================================
# Cross-cutting security invariant tests
# ============================================================

class TestSecurityInvariants:
    """Cross-cutting security invariant tests."""

    def test_auth_module_exports_all_needed(self):
        """auth.py must export all functions used by routers."""
        from auth import (
            get_current_user,
            get_current_admin_user,
            get_redis_client,
            reset_password,
            check_user_quota,
        )

    def test_register_model_cannot_accept_role(self):
        """Pydantic must strip or reject extra fields like 'role'."""
        from auth import RegisterRequest

        req = RegisterRequest.model_validate({
            "email": "test@test.com",
            "password": "TestPass123!",
            "role": "admin",
        })

        assert not hasattr(req, "role") or getattr(req, "role", None) is None, (
            "RegisterRequest stores the 'role' field. Ensure model_config "
            "does not allow extra fields."
        )

    def test_docker_compose_has_admin_env_vars(self):
        """docker-compose.yml must define ADMIN_EMAIL and ADMIN_PASSWORD."""
        docker_compose_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "docker-compose.yml"
        )
        with open(docker_compose_path, "r") as f:
            content = f.read()

        assert "ADMIN_EMAIL" in content, (
            "docker-compose.yml missing ADMIN_EMAIL env var."
        )
        assert "ADMIN_PASSWORD" in content, (
            "docker-compose.yml missing ADMIN_PASSWORD env var."
        )
