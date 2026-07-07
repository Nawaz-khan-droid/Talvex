# TALVEX — Job Application Command Center

Enterprise-grade AI-powered job application pipeline with ATS resume scoring,
intelligent job search, resume optimization, and comprehensive admin analytics.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Next.js    │────▶│  FastAPI     │────▶│  PostgreSQL │
│  Frontend   │     │  Backend     │     │  Database   │
│  (React)    │     │  (Python)    │     │             │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────┴───────┐
                    │              │
               ┌────▼───┐   ┌────▼──────┐
               │ Redis  │   │ ARQ Worker│
               │        │   │ (Background│
               └────────┘   └───────────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼───┐ ┌───▼────┐ ┌──▼──────┐
    │OpenRouter│ │JSearch │ │ Tavily  │
    │(LLM)    │ │(Jobs)  │ │(Search) │
    └─────────┘ └────────┘ └─────────┘
```

## Features

### AI-Powered Career Tools
- **ATS Resume Scoring** — Match score analysis with keyword gap detection
- **Resume Builder** — Template-based resume generation with ATS optimization
- **Resume Optimizer** — JD-aware resume rewriting with skill gap analysis
- **Interview Prep** — Role-specific interview questions with answer tips
- **Follow-Up Emails** — Professional follow-up generation with urgency scoring
- **Email Classification** — Auto-classify recruiter emails (rejection/interview/assessment)
- **Job Description Analysis** — Structured extraction of requirements, skills, perks

### Intelligent Job Search (Dual Engine)
- **JSearch Premium** — Structured job database with salary ranges, experience levels,
  employment types, remote status, and qualifications
- **Tavily Web Search** — Google-powered platform-specific dorking
  (site:linkedin.com, site:indeed.com, site:naukri.com, etc.)
- **Priority Routing**:
  - Platform-specific query ("Search LinkedIn") → Tavily with site: prefix
  - Generic search ("Find AI jobs") → JSearch first (rich metadata), Tavily fallback
  - URL paste → Jina Reader for direct content extraction
- **Smart Match Scoring** — Each listing scored against user's skill profile

### Zero Trust Security
- **Stateful JWT** — Redis-backed sessions with instant revocation
- **Brute-Force Protection** — 5 attempts → 15 min lockout
- **IP Blocklist** — Automated blocking on repeated violations
- **CSRF Protection** — Double-submit cookie pattern
- **CSP Headers** — Content Security Policy, HSTS, X-Content-Type-Options
- **PII Vault** — Fernet encryption for BYOK API keys
- **RBAC** — Role-based access control (admin/user)
- **Per-User Quotas** — Daily rate limits per action type

### Admin Monitoring Dashboard
6 comprehensive analytics endpoints:
1. `GET /api/admin/stats/overview` — System-wide totals, active users, error rates
2. `GET /api/admin/stats/api-usage` — Per-service call counts with token/credit tracking
3. `GET /api/admin/stats/credits` — Top spenders, credit consumption trends
4. `GET /api/admin/stats/users/active` — Most active users ranked by request volume
5. `GET /api/admin/stats/errors` — Recent errors with per-service frequency
6. `GET /api/admin/stats/rate-limits` — Rate limit hit monitoring (24h/7d)

### Prompt Management System
- 16 centralized `.md` prompt templates
- Zero-trust: No inline fallbacks — missing templates fail loudly
- `load_prompt()` with `PromptNotFoundException`
- `[TOKEN EFFICIENCY]` directives on all prompts
- `json_mode=True` enforced on structured outputs

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js, React, Tailwind CSS, shadcn/ui |
| Backend | FastAPI (Python 3.11+), async/await |
| Database | PostgreSQL (production), SQLite (local dev) |
| Cache | Redis (sessions, quotas, rate limits, task queue) |
| Worker | ARQ (async task queue, Redis-backed) |
| LLM | OpenRouter (multi-model: gpt-oss-120b, deepseek-v4-flash, gemma-4-26b) |
| Job Search | JSearch (RapidAPI), Tavily (web search) |
| Auth | JWT (stateful), bcrypt, CSRF double-submit |
| Migrations | Alembic |
| Security | CSP, HSTS, PII Vault (Fernet), IP Blocklist |

## LLM Model Configuration (Free Tier)

| Role | Primary Model | Fallback Model | Purpose |
|------|--------------|----------------|---------|
| SEARCHER | openai/gpt-oss-120b:free | google/gemma-4-26b-a4b-it:free | Conversation, intent routing |
| PARSER | deepseek/deepseek-v4-flash:free | qwen/qwen3-coder:free | JD parsing, content extraction |
| ARCHITECT | openai/gpt-oss-120b:free | google/gemma-4-26b-a4b-it:free | Deep analysis, ATS scoring |
| BUILDER | deepseek/deepseek-v4-flash:free | qwen/qwen3-coder:free | Resume generation |

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis
- PostgreSQL (or SQLite for dev)

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/talvex

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET_KEY=<your-secret-key>
ADMIN_EMAIL=admin@talvex.app
ADMIN_PASSWORD=<admin-password>

# API Keys
OPENROUTER_API_KEY=<your-openrouter-key>
RAPIDAPI_KEY=<your-rapidapi-key>
TAVILY_API_KEY=<your-tavily-key>

# Model Configuration
OPENROUTER_MODEL_SEARCHER=openai/gpt-oss-120b:free
OPENROUTER_MODEL_SEARCHER_FALLBACK=google/gemma-4-26b-a4b-it:free
OPENROUTER_MODEL_ARCHITECT=openai/gpt-oss-120b:free
OPENROUTER_MODEL_ARCHITECT_FALLBACK=google/gemma-4-26b-a4b-it:free
OPENROUTER_MODEL_PARSER=deepseek/deepseek-v4-flash:free
OPENROUTER_MODEL_PARSER_FALLBACK=qwen/qwen3-coder:free
OPENROUTER_MODEL_BUILDER=deepseek/deepseek-v4-flash:free
OPENROUTER_MODEL_BUILDER_FALLBACK=qwen/qwen3-coder:free
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Frontend
cd ..
npm install
npm run dev

# ARQ Worker (separate terminal)
cd backend
arq worker.WorkerSettings
```

### Docker Deployment

```bash
docker compose up -d
```

## Project Structure

```
talvex/
├── backend/
│   ├── main.py                    # FastAPI application entry point
│   ├── auth.py                    # Zero Trust auth (JWT, CSRF, brute-force)
│   ├── models.py                  # SQLAlchemy ORM models
│   ├── schemas.py                 # Pydantic request/response schemas
│   ├── database.py                # Async SQLAlchemy engine + session
│   ├── logging_config.py          # Structured logging with rotation
│   ├── worker.py                  # ARQ background worker
│   ├── alembic/                   # Database migrations
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       ├── 002_chat_history.py
│   │       └── 003_usage_logging.py
│   ├── middleware/
│   │   └── defense.py             # IP Blocklist, Security Headers, CSRF
│   ├── routers/
│   │   ├── admin.py               # Admin dashboard (6 analytics endpoints)
│   │   ├── llm.py                 # LLM-powered endpoints
│   │   ├── resume.py              # Resume management
│   │   ├── jobs.py                # Job search (JSearch + Tavily)
│   │   ├── search.py              # Search proxy endpoints
│   │   ├── analytics.py           # Pipeline analytics
│   │   ├── applications.py        # Application CRUD
│   │   ├── personas.py            # Job persona management
│   │   ├── canary.py              # Email tracking canaries
│   │   ├── recommendations.py     # Skill gap & trade recommendations
│   │   ├── settings.py            # BYOK API key storage
│   │   └── tasks.py               # Background task management
│   ├── services/
│   │   ├── agent.py                # Central orchestrator (intent → handler)
│   │   ├── llm_service.py          # Unified LLM service
│   │   ├── openrouter_client.py    # Multi-model LLM client (2-tier fallback)
│   │   ├── jsearch_client.py       # RapidAPI JSearch client
│   │   ├── tavily_client.py        # Tavily web search client
│   │   ├── usage_logger.py         # Fire-and-forget API usage logging
│   │   ├── rate_limiter.py         # In-memory token bucket rate limiter
│   │   ├── task_queue.py           # ARQ-backed async task queue
│   │   ├── prompt_manager.py       # Centralized prompt template system
│   │   ├── pii_sanitizer.py        # PII detection + Fernet encryption
│   │   ├── resume_optimizer.py     # JD-aware resume optimization
│   │   ├── resume_generator.py     # HTML resume generation
│   │   ├── resume_customizer.py    # Template-based customization
│   │   ├── matcher.py              # ATS match scoring + skill gap analysis
│   │   ├── web_scraper.py          # Job listing scraper
│   │   ├── vector_search.py        # FAISS semantic search
│   │   └── chat_history.py         # Conversation persistence
│   ├── prompts/                    # 16 .md prompt templates
│   ├── templates/                  # HTML resume templates
│   └── tests/                      # Test suite (135+ tests)
├── frontend/                       # Legacy Streamlit UI
├── src/                            # Next.js frontend
│   ├── app/                        # Next.js App Router
│   ├── components/                 # React components (shadcn/ui)
│   ├── hooks/                      # Custom React hooks
│   └── lib/                        # Utilities and types
├── tests/                          # Root test suite
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
└── package.json
```

## API Endpoints

### Auth (Public)
- `POST /api/auth/register` — Create account
- `POST /api/auth/login` — Login (brute-force protected)
- `POST /api/auth/logout` — Revoke session
- `GET /api/auth/me` — Current user profile
- `POST /api/auth/change-password` — Change password (revokes all sessions)

### LLM-Powered (Auth Required)
- `POST /api/llm/chat` — Conversational agent
- `POST /api/llm/ats-score` — ATS resume scoring
- `POST /api/llm/resume-optimize` — Resume optimization
- `POST /api/llm/cover-letter` — Cover letter generation
- `POST /api/llm/interview-prep` — Interview preparation
- `POST /api/llm/follow-up` — Follow-up email generation
- `POST /api/llm/email-classify` — Recruiter email classification
- `POST /api/llm/jd-analyze` — Job description analysis

### Job Search
- `POST /api/jobs/search` — Search jobs (JSearch + Tavily priority routing)
- `GET /api/jobs/{job_id}` — Get job details
- `POST /api/jobs/salary` — Salary estimation
- `POST /api/jobs/ingest` — Ingest job into pipeline

### Admin (Admin Only)
- `GET /api/admin/users` — List users (paginated, searchable)
- `GET /api/admin/stats/overview` — System-wide analytics
- `GET /api/admin/stats/api-usage` — Per-service usage metrics
- `GET /api/admin/stats/credits` — Credit consumption analytics
- `GET /api/admin/stats/users/active` — Most active users
- `GET /api/admin/stats/errors` — Error monitoring
- `GET /api/admin/stats/rate-limits` — Rate limit monitoring
- `GET /api/admin/system/health` — System health (DB + Redis + uptime)
- `GET /api/admin/audit-log` — Paginated audit trail

## Credit System

| Service | Cost per Call |
|---------|--------------|
| OpenRouter (LLM) | 1.0 credit |
| JSearch (Job DB) | 0.5 credits |
| Tavily (Web Search) | 0.3 credits |
| Resume Generation | 2.0 credits |
| ATS Score Analysis | 1.0 credit |

New users start with **100 credits**.

## Security Model

- **Authentication**: Stateful JWT in HTTP-only cookies + Redis session store
- **Authorization**: RBAC with admin/user roles (admin via env vars only)
- **CSRF**: Double-submit cookie pattern
- **Rate Limiting**: Per-service token bucket (openrouter: 40/day, tavily: 33/day, jsearch: 10/day)
- **PII Protection**: Fernet-encrypted BYOK storage, PII scrubbing before LLM calls
- **Input Validation**: Prompt injection detection on LLM inputs
- **Infrastructure**: IP blocklist, security headers (CSP, HSTS), brute-force lockout

## License

Private — All rights reserved.
