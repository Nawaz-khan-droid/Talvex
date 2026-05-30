# TALVEX — Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [1.0.0-rc.5] — 2026-05-30

### Fixed (Build 5 — Critical Auth & UX Fixes)

| # | File | Issue | Fix |
|---|------|-------|-----|
| A1 | `backend/routers/{applications,personas,analytics,canary}.py` | All GET endpoints require JWT auth — frontend has no login page — every API call returns 401 — app shows nothing | Changed GET endpoints to `get_optional_user`; returns empty data when unauthenticated |
| A2 | `src/components/auth/auth-dialog.tsx` | No login/register UI existed — users cannot authenticate at all | Created login/register dialog with email+password, tabs, M3 styling |
| A3 | `src/components/layout/header.tsx` | No way to access login from the UI | Added Login button in header, shows email + Logout after auth |
| A4 | `src/components/onboarding/onboarding-wizard.tsx` | Backdrop click and Escape key permanently close wizard — users lose onboarding forever | Added `onInteractOutside` and `onEscapeKeyDown` prevention |
| A5 | `src/app/page.tsx` | API errors silently swallowed — user sees blank page with no explanation | Added error state with dismissible alert, "Please log in" message for 401s |

### Added
| # | Item | Description |
|---|------|-------------|
| L1 | `backend/services/langfuse_client.py` | Optional Langfuse LLM observability integration (no-op when unconfigured) |
| L2 | `backend/requirements.txt` | Added `langfuse>=2.0.0` (optional dependency) |

---

## [1.0.0-rc.4] — 2026-05-29

### Fixed (Build 4 — UI Polish & Correctness)

| # | File | Issue | Fix |
|---|------|-------|-----|
| U1 | `src/components/analytics/analytics-components.tsx` | Recharts Tooltip/Bar used `hsl(var(--popover))` but CSS tokens are hex values — tooltips rendered with invisible/transparent backgrounds | Changed to `var(--popover)`, `var(--border)`, `var(--primary)` direct references |
| U2 | `src/components/analytics/analytics-components.tsx` | CartesianGrid `className="stroke-muted"` and XAxis/YAxis `className="fill-muted-foreground"` are not valid recharts SVG props — colors silently fail | Changed to `stroke="var(--border)"` and `tick={{ fill: 'var(--muted-foreground)' }}` |
| U3 | `src/components/ingest/ingest-components.tsx` | Label said "AI-Powered Parsing (z.ai GLM)" — misleading branding, TALVEX uses OpenRouter not z-ai-web-dev-sdk | Changed to "AI-Powered Parsing (OpenRouter)" |
| U4 | `src/lib/types.ts` | `PlatformInfo.priority` type missing `"low"` — TypeScript error on manual entry platform | Added `"low"` to union type |
| U5 | `src/components/onboarding/onboarding-wizard.tsx` | `showCloseButton` prop on DialogContent is not a standard shadcn/ui prop — ignored at runtime but generates TS warning | Removed invalid prop |

---

## [1.0.0-rc.3] — 2026-05-29

### Fixed (Build 3 — Final QA Sweep)

#### CRITICAL — App crash fixes
| # | File | Issue | Fix |
|---|------|-------|-----|
| C1 | `backend/requirements.txt` | `python-docx` missing — resume generator crashes on `from docx import Document` | Added `python-docx>=1.0.0` |
| C2 | `backend/requirements.txt` | `jinja2` missing — resume generator crashes on `from jinja2 import Environment` | Added `jinja2>=3.0.0` |
| C3 | `package.json` scripts | `\| tee dev.log` — Linux-only pipe, causes silent failure on Windows | Removed `2>&1 \| tee dev.log` from `dev` |
| C4 | `package.json` scripts | `\| tee server.log` — same Linux-only issue | Removed from `start` |
| C5 | `package.json` scripts | `cp -r` — Linux-only copy, breaks `npm run build` on Windows | Removed from `build` |
| C6 | `run_local.ps1` line 172 | Worker launched with `.\venv\Scripts\arq` (not a real exe) — `ModuleNotFoundError` | Changed to `.\venv\Scripts\python.exe -m arq` |
| C7 | `next.config.ts` | Missing `turbopack.root` — Next.js 16 picks wrong workspace root when stray lockfiles exist in parent dirs | Added `turbopack: { root: __dirname }` |
| C8 | `.env` / `.env.example` | Missing entirely — no DATABASE_URL, no JWT keys, no config template | Created both files with pre-generated secrets |

#### HIGH — UI/UX fixes
| # | File | Issue | Fix |
|---|------|-------|-----|
| H1 | `src/components/layout/header.tsx` | No theme toggle — users cannot switch dark/light mode despite full M3 theme system | Added Sun/Moon toggle button using `next-themes` |
| H2 | `src/app/page.tsx` | Tab navigation doesn't update browser URL — back/forward buttons don't work, deep links break | Added `router.push(\`?tab=${tab}\`)` in `handleNavigate` |
| H3 | `src/components/pipeline/pipeline-components.tsx` | Kanban `onRefresh` only closed detail dialog — didn't reload data after status advance | Fixed to call `onRefresh()` (fetchAll) after closing dialog |

### Known Limitations (Deferred)
| # | Area | Description | Priority |
|---|------|-------------|----------|
| K1 | Auth | Frontend has no login page — backend JWT auth exists but frontend doesn't send tokens | HIGH |
| K2 | i18n | `next-intl` installed but not wired up | LOW |
| K3 | Dependencies | ~18 unused npm packages in package.json (backend-only packages) | LOW |
| K4 | ESLint | Most rules disabled in eslint.config.mjs | LOW |

---

## [1.0.0-rc.2] — 2026-05-28

### Fixed (Build 2 — Core Stability)
| # | File | Issue | Fix |
|---|------|-------|-----|
| B1 | `package.json` | `bun` in start script — fails on Windows without bun | Changed to `node` |
| B2 | `backend/database.py` | SQLite silent fallback — masks missing DATABASE_URL in production | Removed fallback; throws `RuntimeError` if no `DATABASE_URL` |
| B3 | `backend/auth.py` | `user.id` in except block crashes when user is `None` — `AttributeError` | Changed to `email` (already validated) |
| B4 | `backend/auth.py` | No CLI entry point for password reset | Added `if __name__ == "__main__":` block |
| B5 | `run_local.ps1` | PostgreSQL port check used 5432 but .env uses 5439 | Aligned to 5439 |

### Added
| # | Item | Description |
|---|------|-------------|
| A1 | `run_local.ps1` | 6-step local launcher (prereq check → env → PostgreSQL → Redis → deps → launch) |
| A2 | `.env.example` | Template with all required variables documented |
| A3 | `.env` | Pre-generated JWT + Fernet keys, PostgreSQL on port 5439 |

---

## [1.0.0-rc.1] — 2026-05-25

### Initial Release
- FastAPI backend with 11 routers (auth, jobs, applications, personas, resume, canary, analytics, recommendations, LLM, search, tasks, admin, settings)
- Next.js 16 frontend with Material 3 theming, 8-tab SPA layout
- PostgreSQL + Redis + ARQ worker architecture
- PII zero-trust pipeline (regex + spaCy NER → Fernet AES-256 → Redis TTL)
- ATS scoring, skill gap analysis, interview prep
- Tracking canary leak detection system
- 7-step premium job search pipeline
