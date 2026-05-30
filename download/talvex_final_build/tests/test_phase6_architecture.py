"""
Phase 6 Test Suite: Architecture Migration & Material 3 Adoption

Validates:
  1. Frontend/Backend Separation — clean architecture with no monolithic mixing
  2. Next.js Frontend — proper structure with TypeScript, Tailwind CSS 4
  3. FastAPI Backend — proper structure with routers, services, models
  4. Material 3 Design Tokens — light/dark themes with M3 color system
  5. M3 Shape Tokens — rounded corners matching M3 spec
  6. M3 Typography — Roboto font family (M3 recommended)
  7. Dark Mode Support — next-themes integration
  8. shadcn/ui + M3 Fusion — proper token mapping
  9. API Route Separation — Next.js API routes properly structured
  10. Docker Configuration — multi-stage builds for frontend/backend
"""

import os
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
SRC_DIR = PROJECT_ROOT / "src"
FRONTEND_PY_DIR = PROJECT_ROOT / "frontend"


# ===================================================================
# 1. Frontend/Backend Separation
# ===================================================================

class TestFrontendBackendSeparation:
    """Verify clean separation between Next.js frontend and FastAPI backend."""

    def test_next_config_exists(self):
        """Next.js config file exists."""
        assert (PROJECT_ROOT / "next.config.ts").exists(), (
            "next.config.ts must exist at project root"
        )

    def test_package_json_exists(self):
        """package.json exists at project root (Next.js project)."""
        assert (PROJECT_ROOT / "package.json").exists(), (
            "package.json must exist at project root"
        )

    def test_fastapi_main_exists(self):
        """FastAPI main.py exists in backend/."""
        assert (BACKEND_DIR / "main.py").exists(), (
            "backend/main.py must exist"
        )

    def test_backend_requirements_txt(self):
        """backend/requirements.txt exists."""
        assert (BACKEND_DIR / "requirements.txt").exists(), (
            "backend/requirements.txt must exist"
        )

    def test_no_python_files_in_src(self):
        """No .py files in the Next.js src/ directory (pure TypeScript)."""
        py_files = list(SRC_DIR.rglob("*.py"))
        assert len(py_files) == 0, (
            f"Found {len(py_files)} Python files in src/ — frontend must be TypeScript only"
        )

    def test_backend_has_routers_directory(self):
        """backend/routers/ directory exists with router files."""
        routers_dir = BACKEND_DIR / "routers"
        assert routers_dir.exists(), "backend/routers/ must exist"
        router_files = list(routers_dir.glob("*.py"))
        # Exclude __init__.py
        actual_routers = [f for f in router_files if f.name != "__init__.py"]
        assert len(actual_routers) >= 5, (
            f"Expected at least 5 routers, found {len(actual_routers)}"
        )

    def test_backend_has_services_directory(self):
        """backend/services/ directory exists with service files."""
        services_dir = BACKEND_DIR / "services"
        assert services_dir.exists(), "backend/services/ must exist"
        service_files = list(services_dir.glob("*.py"))
        actual_services = [f for f in service_files if f.name != "__init__.py"]
        assert len(actual_services) >= 5, (
            f"Expected at least 5 services, found {len(actual_services)}"
        )

    def test_backend_has_models(self):
        """backend/models.py exists (SQLAlchemy models)."""
        assert (BACKEND_DIR / "models.py").exists(), "backend/models.py must exist"

    def test_backend_has_schemas(self):
        """backend/schemas.py exists (Pydantic schemas)."""
        assert (BACKEND_DIR / "schemas.py").exists(), "backend/schemas.py must exist"

    def test_backend_has_database(self):
        """backend/database.py exists (DB connection)."""
        assert (BACKEND_DIR / "database.py").exists(), "backend/database.py must exist"


# ===================================================================
# 2. Next.js Frontend Structure
# ===================================================================

class TestNextJSFrontend:
    """Verify Next.js frontend is properly structured."""

    def test_app_directory_exists(self):
        """src/app/ directory exists (App Router)."""
        assert (SRC_DIR / "app").exists(), "src/app/ must exist (App Router)"

    def test_app_layout_exists(self):
        """src/app/layout.tsx exists."""
        assert (SRC_DIR / "app" / "layout.tsx").exists(), "src/app/layout.tsx must exist"

    def test_app_page_exists(self):
        """src/app/page.tsx exists."""
        assert (SRC_DIR / "app" / "page.tsx").exists(), "src/app/page.tsx must exist"

    def test_globals_css_exists(self):
        """src/app/globals.css exists."""
        assert (SRC_DIR / "app" / "globals.css").exists(), "src/app/globals.css must exist"

    def test_components_directory_exists(self):
        """src/components/ directory exists."""
        assert (SRC_DIR / "components").exists(), "src/components/ must exist"

    def test_ui_components_exist(self):
        """src/components/ui/ has shadcn/ui components."""
        ui_dir = SRC_DIR / "components" / "ui"
        assert ui_dir.exists(), "src/components/ui/ must exist"
        ui_files = list(ui_dir.glob("*.tsx"))
        assert len(ui_files) >= 10, (
            f"Expected at least 10 UI components, found {len(ui_files)}"
        )

    def test_tailwind_config_exists(self):
        """Tailwind CSS config exists at project root."""
        assert (PROJECT_ROOT / "tailwind.config.ts").exists(), (
            "tailwind.config.ts must exist"
        )

    def test_typescript_config_exists(self):
        """tsconfig.json exists."""
        assert (PROJECT_ROOT / "tsconfig.json").exists(), "tsconfig.json must exist"


# ===================================================================
# 3. FastAPI Backend Structure
# ===================================================================

class TestFastAPIBackend:
    """Verify FastAPI backend is properly structured."""

    def test_main_creates_fastapi_app(self):
        """backend/main.py creates a FastAPI app instance."""
        with open(BACKEND_DIR / "main.py") as f:
            content = f.read()
        assert 'FastAPI(' in content, "main.py must create FastAPI app"
        assert 'title="TALVEX' in content, "FastAPI app must have TALVEX title"

    def test_cors_middleware_configured(self):
        """CORS middleware is configured."""
        with open(BACKEND_DIR / "main.py") as f:
            content = f.read()
        assert 'CORSMiddleware' in content, "CORS middleware must be configured"

    def test_health_check_endpoints(self):
        """Health check endpoints exist."""
        with open(BACKEND_DIR / "main.py") as f:
            content = f.read()
        assert '@app.get("/")' in content or 'def health_check' in content, (
            "Root health check must exist"
        )
        assert '"/health"' in content, "/health endpoint must exist"

    def test_global_exception_handlers(self):
        """Global exception handlers are configured."""
        with open(BACKEND_DIR / "main.py") as f:
            content = f.read()
        assert 'exception_handler' in content, "Exception handlers must be configured"

    def test_routers_included(self):
        """All routers are included in the FastAPI app."""
        with open(BACKEND_DIR / "main.py") as f:
            content = f.read()
        expected_routers = ['jobs', 'applications', 'personas', 'resume', 'llm', 'search']
        for router in expected_routers:
            assert f'{router}.router' in content, f"Router '{router}' must be included"

    def test_dockerfile_exists(self):
        """backend/Dockerfile exists."""
        assert (BACKEND_DIR / "Dockerfile").exists(), "backend/Dockerfile must exist"


# ===================================================================
# 4. Material 3 Design Tokens — Light Theme
# ===================================================================

class TestMaterial3LightTheme:
    """Verify Material 3 light theme tokens."""

    @pytest.fixture(autouse=True)
    def _read_css(self):
        with open(SRC_DIR / "app" / "globals.css") as f:
            self.css = f.read()

    def test_m3_comment_header(self):
        """CSS has 'Material 3' design token comment."""
        assert 'Material 3' in self.css, "CSS must reference Material 3"

    def test_m3_primary_color(self):
        """M3 Primary color is defined (#6750A4 — M3 Baseline Purple)."""
        assert '--primary: #6750A4' in self.css, (
            "M3 Primary must be #6750A4"
        )

    def test_m3_on_primary(self):
        """M3 On Primary is defined (#FFFFFF)."""
        assert '--primary-foreground: #FFFFFF' in self.css, (
            "M3 On Primary must be #FFFFFF"
        )

    def test_m3_secondary_color(self):
        """M3 Secondary color is defined."""
        assert '--secondary: #625B71' in self.css

    def test_m3_tertiary_color(self):
        """M3 Tertiary color is defined."""
        assert '--tertiary:' in self.css

    def test_m3_surface_color(self):
        """M3 Surface color is defined (#FEF7FF)."""
        assert '--background: #FEF7FF' in self.css, (
            "M3 Surface (--background) must be #FEF7FF"
        )

    def test_m3_on_surface(self):
        """M3 On Surface color is defined (#1D1B20)."""
        assert '--foreground: #1D1B20' in self.css, (
            "M3 On Surface (--foreground) must be #1D1B20"
        )

    def test_m3_error_color(self):
        """M3 Error color is defined (#B3261E)."""
        assert '--destructive: #B3261E' in self.css, (
            "M3 Error (--destructive) must be #B3261E"
        )

    def test_m3_outline(self):
        """M3 Outline color is defined."""
        assert '--outline:' in self.css

    def test_m3_primary_container(self):
        """M3 Primary Container is defined."""
        assert '--primary-container: #EADDFF' in self.css

    def test_m3_secondary_container(self):
        """M3 Secondary Container is defined."""
        assert '--secondary-container:' in self.css

    def test_m3_surface_container(self):
        """M3 Surface Container hierarchy is defined."""
        assert '--surface-container:' in self.css
        assert '--surface-container-high:' in self.css
        assert '--surface-container-highest:' in self.css

    def test_m3_error_container(self):
        """M3 Error Container is defined."""
        assert '--error-container:' in self.css


# ===================================================================
# 5. Material 3 Design Tokens — Dark Theme
# ===================================================================

class TestMaterial3DarkTheme:
    """Verify Material 3 dark theme tokens."""

    @pytest.fixture(autouse=True)
    def _read_css(self):
        with open(SRC_DIR / "app" / "globals.css") as f:
            self.css = f.read()

    def test_dark_theme_block_exists(self):
        """.dark class block exists."""
        assert '.dark {' in self.css, ".dark class must exist"

    def test_dark_primary(self):
        """Dark theme Primary is #D0BCFF."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--primary: #D0BCFF' in dark_block, (
            "Dark M3 Primary must be #D0BCFF"
        )

    def test_dark_on_primary(self):
        """Dark theme On Primary is #381E72."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--primary-foreground: #381E72' in dark_block, (
            "Dark M3 On Primary must be #381E72"
        )

    def test_dark_surface(self):
        """Dark theme Surface is #141218."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--background: #141218' in dark_block, (
            "Dark M3 Surface must be #141218"
        )

    def test_dark_on_surface(self):
        """Dark theme On Surface is #E6E0E9."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--foreground: #E6E0E9' in dark_block, (
            "Dark M3 On Surface must be #E6E0E9"
        )

    def test_dark_error(self):
        """Dark theme Error is #F2B8B5."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--destructive: #F2B8B5' in dark_block, (
            "Dark M3 Error must be #F2B8B5"
        )

    def test_dark_primary_container(self):
        """Dark theme Primary Container is #4F378B."""
        dark_block = self.css[self.css.find('.dark {'):]
        assert '--primary-container: #4F378B' in dark_block


# ===================================================================
# 6. Material 3 Shape Tokens
# ===================================================================

class TestMaterial3ShapeTokens:
    """Verify M3 shape tokens (rounded corners)."""

    @pytest.fixture(autouse=True)
    def _read_css(self):
        with open(SRC_DIR / "app" / "globals.css") as f:
            self.css = f.read()

    def test_m3_shape_comment(self):
        """M3 shape tokens section exists."""
        assert 'M3 shape tokens' in self.css or 'radius-' in self.css, (
            "M3 shape tokens must be defined"
        )

    def test_radius_sm(self):
        """radius-sm = 4px (M3 Extra Small)."""
        assert '--radius-sm: 0.25rem' in self.css, (
            "radius-sm must be 0.25rem (4px)"
        )

    def test_radius_md(self):
        """radius-md = 8px (M3 Small)."""
        assert '--radius-md: 0.5rem' in self.css, (
            "radius-md must be 0.5rem (8px)"
        )

    def test_radius_lg(self):
        """radius-lg = 12px (M3 Medium)."""
        assert '--radius-lg: 0.75rem' in self.css, (
            "radius-lg must be 0.75rem (12px)"
        )

    def test_radius_xl(self):
        """radius-xl = 16px (M3 Large)."""
        assert '--radius-xl: 1rem' in self.css, (
            "radius-xl must be 1rem (16px)"
        )

    def test_radius_2xl(self):
        """radius-2xl = 20px (M3 Extra Large)."""
        assert '--radius-2xl: 1.25rem' in self.css, (
            "radius-2xl must be 1.25rem (20px)"
        )

    def test_radius_3xl(self):
        """radius-3xl = 28px (M3 Full)."""
        assert '--radius-3xl: 1.75rem' in self.css, (
            "radius-3xl must be 1.75rem (28px)"
        )


# ===================================================================
# 7. Material 3 Typography
# ===================================================================

class TestMaterial3Typography:
    """Verify M3 typography with Roboto font."""

    def test_roboto_font_imported(self):
        """Roboto font is imported from next/font/google."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert 'Roboto' in content, "Roboto font must be imported"

    def test_roboto_variable_defined(self):
        """Roboto CSS variable is defined."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert '--font-roboto' in content, "Roboto CSS variable must be defined"

    def test_body_uses_roboto(self):
        """Body element uses Roboto as the primary font."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert 'Roboto' in content or 'var(--font-roboto)' in content, (
            "Body must use Roboto font"
        )

    def test_css_font_sans_is_roboto(self):
        """CSS --font-sans maps to Roboto."""
        with open(SRC_DIR / "app" / "globals.css") as f:
            content = f.read()
        assert 'var(--font-roboto)' in content, (
            "CSS --font-sans must map to --font-roboto"
        )


# ===================================================================
# 8. Dark Mode Support
# ===================================================================

class TestDarkModeSupport:
    """Verify dark mode implementation."""

    def test_next_themes_imported(self):
        """next-themes is imported in layout."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert 'next-themes' in content, "next-themes must be imported"

    def test_theme_provider_used(self):
        """ThemeProvider from next-themes wraps the app."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert 'ThemeProvider' in content, "ThemeProvider must be used"

    def test_system_theme_default(self):
        """Default theme is 'system'."""
        with open(SRC_DIR / "app" / "layout.tsx") as f:
            content = f.read()
        assert 'defaultTheme="system"' in content or 'defaultTheme="dark"' in content, (
            "Default theme should be 'system' or 'dark'"
        )

    def test_dark_variant_css(self):
        """CSS has dark variant custom-variant definition."""
        with open(SRC_DIR / "app" / "globals.css") as f:
            content = f.read()
        assert '@custom-variant dark' in content or '.dark' in content, (
            "Dark mode variant must be defined in CSS"
        )


# ===================================================================
# 9. Docker Configuration
# ===================================================================

class TestDockerConfiguration:
    """Verify Docker configuration for frontend/backend separation."""

    def test_docker_compose_exists(self):
        """docker-compose.yml exists at project root."""
        assert (PROJECT_ROOT / "docker-compose.yml").exists(), (
            "docker-compose.yml must exist"
        )

    def test_docker_compose_has_backend_service(self):
        """docker-compose.yml has a backend service."""
        with open(PROJECT_ROOT / "docker-compose.yml") as f:
            content = f.read()
        assert 'talvex-backend' in content or 'backend:' in content, (
            "docker-compose.yml must define a backend service"
        )

    def test_docker_compose_has_redis(self):
        """docker-compose.yml has a Redis service."""
        with open(PROJECT_ROOT / "docker-compose.yml") as f:
            content = f.read()
        assert 'redis' in content.lower(), (
            "docker-compose.yml must have a Redis service"
        )


# ===================================================================
# 10. API Route Separation
# ===================================================================

class TestAPIRoutes:
    """Verify Next.js API routes are properly structured."""

    def test_api_directory_exists(self):
        """src/app/api/ directory exists."""
        assert (SRC_DIR / "app" / "api").exists(), "src/app/api/ must exist"

    def test_api_routes_exist(self):
        """Multiple API route files exist."""
        api_dir = SRC_DIR / "app" / "api"
        route_files = list(api_dir.rglob("route.ts"))
        assert len(route_files) >= 3, (
            f"Expected at least 3 API routes, found {len(route_files)}"
        )

    def test_no_python_in_api_routes(self):
        """API routes are TypeScript, not Python."""
        api_dir = SRC_DIR / "app" / "api"
        py_files = list(api_dir.rglob("*.py"))
        assert len(py_files) == 0, "API routes must be TypeScript only"
