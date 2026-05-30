# Task 6, 7, 8 — Agent Work Record

## Agent: Main
## Task: Phase 4 — Docker Compose setup, PostgreSQL migration, Telegram bot

### Files Created (5)
1. `/home/z/my-project/docker-compose.yml` — 4-service Docker Compose stack
2. `/home/z/my-project/Dockerfile` — Multi-stage Next.js 16 build
3. `/home/z/my-project/backend/Dockerfile` — Python FastAPI + Typst
4. `/home/z/my-project/.dockerignore` — Build exclusions
5. `/home/z/my-project/backend/telegram_bot.py` — Telegram bot (6 commands)

### Files Modified (5)
1. `prisma/schema.prisma` — provider "sqlite" → "postgresql"
2. `backend/database.py` — env-based DATABASE_URL with SQLite fallback
3. `backend/routers/jobs.py` — Added POST /api/jobs/tavily-search endpoint
4. `backend/requirements.txt` — Added python-telegram-bot, psycopg2-binary
5. `.env.example` — Updated DATABASE_URL to PostgreSQL, added POSTGRES_PASSWORD

### Key Decisions
- `.env` kept with SQLite URL for local dev (env-based switching)
- Backend database.py conditionally applies SQLite connect_args
- Telegram bot uses httpx (not raw requests) to call FastAPI endpoints
- Added Tavily search endpoint to jobs router (bot reuses tavily_client.py)
- Docker backend volume mounts source for dev hot-reload
