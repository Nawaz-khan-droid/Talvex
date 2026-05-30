# TALVEX Architecture Overview

**Author**: Comprehensive Codebase Analysis  
**Date**: 2026-05-30  
**Status**: Production-Grade System (with identified technical debt)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Technology Stack](#technology-stack)
4. [Core User Flows](#core-user-flows)
5. [Security Model](#security-model)
6. [Technical Debt & Risks](#technical-debt--risks)
7. [Refactoring Roadmap](#refactoring-roadmap)
8. [Operations & Deployment](#operations--deployment)

---

## Executive Summary

**TALVEX** is an enterprise-grade, AI-powered job application management platform combining:
- **Intelligent job discovery** (JSearch + Tavily dual-engine routing)
- **Resume optimization** (JD-aware customization + ATS scoring)
- **Career coaching** (interview prep, follow-up generation, email classification)
- **Admin analytics** (6 comprehensive endpoints with real-time metrics)

**Tech Stack**: FastAPI (Python 3.11) + Next.js (React 19) + PostgreSQL + Redis + OpenRouter  
**Scale**: Multi-user SaaS with per-user quotas, RBAC, and zero-trust security  
**Maturity**: Production-ready core with 3-4 identified high-priority improvements

---

## System Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT LAYER                             │
│  Next.js Frontend (React 19 + Tailwind CSS + shadcn/ui)    │
│  Streamlit UI (Legacy, deprecated)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS/JSON
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI GATEWAY                           │
│  ├─ Route Registration (routers/ directory)                 │
│  ├─ JWT Auth + CSRF Protection (auth.py)                   │
│  ├─ Rate Limiting (in-memory token bucket)                 │
│  └─ Middleware Defense (IP blocklist, CSP headers)         │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    ┌────────┐  ┌──────────┐  ┌─────────────┐
    │ Agent  │  │LLM       │  │ Job Search  │
    │Service │  │Service   │  │ Services    │
    │        │  │(Routing) │  │(JSearch+    │
    │(Intent)│  │          │  │ Tavily)     │
    └────────┘  └──────────┘  └─────────────┘
        │              │              │
        ▼              ▼              ▼
   ┌─────────────────────────────────────────┐
   │       External APIs (Over HTTPS)        │
   │  ├─ OpenRouter (Multi-Model LLM)        │
   │  ├─ JSearch (RapidAPI)                  │
   │  ├─ Tavily (Web Search)                 │
   │  └─ Jina (Content Extraction)           │
   └─────────────────────────────────────────┘
        
        │              │
        ▼              ▼
┌─────────────────────────────────────────┐
│       Persistent Storage Layer          │
│  ├─ PostgreSQL (ORM: SQLAlchemy)       │
│  ├─ Redis (Sessions, Cache, Queue)     │
│  └─ FAISS (Vector Embeddings)          │
└─────────────────────────────────────────┘

        │
        ▼
┌─────────────────────────────────────────┐
│    Background Task Worker               │
│  ARQ (Async Task Queue, Redis-backed)  │
└─────────────────────────────────────────┘
```

### Data Flow: End-to-End Job Application

```
USER INPUT (Resume + Job Link)
    │
    ▼
AUTHENTICATION & AUTHORIZATION
    ├─ JWT token validated
    ├─ Session checked in Redis
    └─ User quota verified
    │
    ▼
INTENT ROUTING (Agent Service)
    ├─ Detect user request type
    ├─ Route to appropriate handler
    └─ Log operation
    │
    ▼
BUSINESS LOGIC EXECUTION
    ├─ Job Discovery (JSearch/Tavily)
    ├─ ATS Matching (OpenRouter ARCHITECT model)
    ├─ Resume Optimization (OpenRouter PARSER model)
    ├─ Interview Prep (OpenRouter SEARCHER model)
    └─ Email Classification (OpenRouter PARSER)
    │
    ▼
DATABASE PERSISTENCE
    ├─ SQLAlchemy ORM saves to PostgreSQL
    ├─ Chat history stored (Conversation model)
    ├─ Credits deducted from user quota
    └─ Audit trail logged
    │
    ▼
CACHE UPDATE & NOTIFICATIONS
    ├─ Redis session refreshed
    ├─ FAISS vectors updated (if resume changed)
    └─ Background task queued (if async)
    │
    ▼
CLIENT RESPONSE (JSON)
    └─ Next.js frontend renders results
```

---

## Technology Stack

### Backend (68.7% Python)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | FastAPI | Latest | Async HTTP server |
| **ORM** | SQLAlchemy | 2.x | Database abstraction |
| **Database** | PostgreSQL | 13+ | Production DB |
| **Cache/Sessions** | Redis | 6+ | Stateful JWT, rate limits |
| **Background Jobs** | ARQ | Latest | Async task queue |
| **LLM Client** | OpenAI SDK | 1.x | OpenRouter compatible |
| **Encryption** | cryptography (Fernet) | Latest | PII vault |
| **Validation** | Pydantic v2 | 2.x | Request/response schemas |
| **Migrations** | Alembic | Latest | DB versioning |

### Frontend (27.5% TypeScript/JavaScript)

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Framework** | Next.js | 16.1.1 | React meta-framework |
| **UI Library** | React | 19.0.0 | Component rendering |
| **Styling** | Tailwind CSS | 4.x | Utility CSS |
| **Components** | shadcn/ui | Latest | Headless UI kit |
| **State Mgmt** | Zustand | 5.x | Lightweight state |
| **Forms** | React Hook Form | 7.x | Form state & validation |
| **Data Fetch** | TanStack Query | 5.x | Server state sync |
| **Schema Valid** | Zod | 4.x | Runtime type checking |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Containerization** | Docker | Immutable deployments |
| **Orchestration** | Docker Compose (local) | Multi-service setup |
| **Reverse Proxy** | Caddy | TLS termination, routing |
| **Async Runtime** | Python asyncio | Concurrent requests |

---

## Core User Flows

### Flow 1: Job Search → ATS Scoring → Resume Customization

```
1. User searches: "Python FastAPI jobs remote"
   └─ Intent detected: SEARCH_JOBS (platform-agnostic)
   
2. Query routed in services/agent.py:
   ├─ Check if "LinkedIn" or "Indeed" mentioned → Tavily (site: prefix)
   ├─ Else → JSearch first (structured), fallback Tavily
   └─ Results deduplicated (url-based hash)
   
3. For each result, ATS score computed:
   ├─ Resume + JD → OpenRouter (ARCHITECT model)
   ├─ Keyword extraction (skill gaps)
   ├─ Score 0–100 assigned
   ├─ 1.0 credit deducted
   └─ Results stored in PostgreSQL
   
4. High-scoring jobs (>75) flagged:
   ├─ User sees tailored action items
   └─ Resume customization offered
   
5. User selects job → "Optimize for this JD"
   ├─ POST /api/llm/resume-optimize
   ├─ OpenRouter (PARSER model) analyzes gaps
   ├─ New resume bullets generated
   ├─ 2.0 credits deducted
   └─ HTML resume compiled + stored

6. Optionally: Interview Prep
   ├─ POST /api/llm/interview-prep
   ├─ Technical Q&A generated
   ├─ 1.0 credit deducted
   └─ Stored in chat_history (PostgreSQL)
```

### Flow 2: Email Ingestion & Follow-Up Generation

```
1. Recruiter email arrives → User forwards to system webhook
   
2. Email parsed & classified:
   ├─ OpenRouter detects: [Rejection | Interview Invite | Assessment]
   ├─ 1.0 credit deducted
   └─ Classification stored in chat_history
   
3. If "Interview Invite":
   ├─ POST /api/llm/follow-up triggered
   ├─ Generated follow-up email displayed
   ├─ 0.5 credit deducted
   └─ User sends manually (no auto-send)
   
4. Application status updated:
   ├─ PATCH /api/applications/{job_id}
   ├─ Status → "Interview" (user-confirmed)
   ├─ Timestamp recorded
   └─ Analytics updated
```

### Flow 3: Admin Monitoring

```
1. Admin logs in (credentials from .env only)
   
2. Dashboard opens → GET /api/admin/stats/overview
   ├─ Total users, jobs indexed, applications
   ├─ Success rate (offers / applications)
   ├─ Error rates (last 24h)
   └─ System uptime
   
3. Drill-down analytics:
   ├─ GET /api/admin/stats/api-usage → Per-service call counts
   ├─ GET /api/admin/stats/credits → Top spenders
   ├─ GET /api/admin/stats/users/active → Most active users
   ├─ GET /api/admin/stats/errors → Recent error logs
   └─ GET /api/admin/stats/rate-limits → Rate limit hits (24h/7d)
   
4. System health:
   ├─ GET /api/admin/system/health
   ├─ Database connectivity
   ├─ Redis status
   ├─ Uptime (process start time)
   └─ Error rate (errors / total requests)
```

---

## Security Model

### Authentication

**Method**: Stateful JWT (JSON Web Tokens)

```
1. User → POST /api/auth/login
   ├─ Email + password received
   ├─ Brute-force check:
   │  ├─ Last 5 failed attempts + timestamp in PostgreSQL
   │  └─ If 5 attempts in 15 min → lockout
   ├─ Password verified (bcrypt)
   └─ JWT token generated
   
2. Token storage:
   ├─ HTTP-only cookie (cannot be accessed by JavaScript)
   ├─ SameSite=Strict
   ├─ Secure flag (HTTPS only)
   └─ Session ID also stored in Redis
   
3. On each request:
   ├─ Cookie extracted
   ├─ JWT signature verified (JWT_SECRET_KEY)
   ├─ Session lookup in Redis (instant revocation)
   └─ Request allowed
   
4. Password change:
   ├─ POST /api/auth/change-password
   ├─ All sessions revoked (all Redis entries deleted)
   └─ User forced to re-login
```

**Files Involved**:
- `backend/auth.py` — Password hashing, JWT creation, brute-force tracking
- `backend/middleware/defense.py` — IP blocklist enforcement

### Authorization

**Model**: Role-Based Access Control (RBAC)

```
┌─────────────────────────────────────────┐
│           User Roles                     │
├─────────────────────────────────────────┤
│ ADMIN (defined in .env only)            │
│  └─ Can access all analytics endpoints  │
│  └─ Can view all users                  │
│  └─ Can access audit logs               │
│                                          │
│ USER (default, self-service)            │
│  └─ Own resume, jobs, applications      │
│  └─ Per-user quota limits               │
│  └─ Chat history (private)              │
└─────────────────────────────────────────┘
```

**Implementation**:
```python
# backend/routers/admin.py
@router.get("/api/admin/stats/overview")
async def get_overview(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    # ... fetch stats
```

### CSRF Protection

**Pattern**: Double-Submit Cookie

```
1. Client receives X-CSRF-Token in response header
2. For mutations (POST, PATCH, DELETE):
   ├─ Client sends X-CSRF-Token header
   └─ Server compares token value with session token in Redis
3. Token mismatch → 403 Forbidden
```

**File**: `backend/middleware/defense.py`

### PII Protection

**Encryption**: Fernet (AES-128-CBC)

```
Sensitive Data:
├─ BYOK API keys (user enters OpenAI key, etc.)
│  └─ Encrypted at rest in PostgreSQL (UserSecret table)
│  └─ Decrypted only on API call
│
├─ Resume text (contains name, phone, address)
│  └─ Scrubbed before LLM exposure (regex + hashing)
│  └─ Stored plain in PostgreSQL (user-controlled)
│  └─ Can be encrypted per-user preference
│
└─ Chat history (may contain PII)
   └─ Stored per-user in PostgreSQL
   └─ Accessible only to owner
```

**Implementation**:
```python
# backend/services/pii_sanitizer.py
def scrub_resume(resume_text: str) -> str:
    # Remove emails: user@domain.com → [EMAIL_REDACTED]
    # Remove phones: +1-555-1234 → [PHONE_REDACTED]
    # Before sending to OpenRouter
    return sanitized_text

# Encrypt BYOK keys
from cryptography.fernet import Fernet
cipher = Fernet(encryption_key)  # Key from .env
encrypted = cipher.encrypt(user_openai_key.encode())
db.UserSecret.encrypted_value = encrypted
```

**Files Involved**:
- `backend/services/pii_sanitizer.py` — PII detection & scrubbing
- `backend/routers/settings.py` — BYOK key storage (encrypted)

---

## Technical Debt & Risks

### Critical Issues (Implement Immediately)

#### 1. **Missing Template Validation on Startup**
- **Location**: `backend/services/prompt_manager.py`
- **Risk**: Missing `.md` template → `PromptNotFoundException` → production outage
- **Fix**: Add startup validation loop
- **Effort**: 30 minutes

```python
# backend/services/prompt_manager.py
REQUIRED_TEMPLATES = [
    'ats_score.md', 'resume_optimize.md', 
    'interview_prep.md', 'cover_letter.md', ...
]

def validate_templates():
    missing = [t for t in REQUIRED_TEMPLATES if not os.path.exists(f"backend/prompts/{t}")]
    if missing:
        raise RuntimeError(f"Missing templates: {missing}")

# Add to main.py startup
@app.on_event("startup")
async def startup():
    validate_templates()
    # ... other startup logic
```

---

#### 2. **No Circuit Breaker on External APIs**
- **Location**: `openrouter_client.py`, `jsearch_client.py`, `tavily_client.py`
- **Risk**: OpenRouter outage cascades to all users; no graceful degradation
- **Fix**: Wrap calls with circuit breaker pattern
- **Effort**: 2–3 hours

```python
# backend/services/circuit_breaker.py (add new file)
from functools import wraps
import time

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.last_failure_time = None
        self.threshold = failure_threshold
        self.timeout = recovery_timeout
        self.state = "CLOSED"  # CLOSED → OPEN → HALF-OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF-OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.threshold:
                self.state = "OPEN"
            raise

# Usage in openrouter_client.py
class OpenRouterClient:
    def __init__(self):
        self.breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    
    async def call_model(self, messages, model):
        return self.breaker.call(self._call_openrouter, messages, model)
```

---

#### 3. **Rate Limiter State Lost on Restart**
- **Location**: `backend/services/rate_limiter.py`
- **Risk**: In-memory token bucket → users can bypass quotas by restarting server
- **Fix**: Persist bucket state to Redis
- **Effort**: 2 hours

```python
# backend/services/rate_limiter.py (refactor)
class RedisTokenBucket:
    def __init__(self, user_id: str, redis_conn, capacity=40, refill_rate=1):
        self.redis = redis_conn
        self.user_id = user_id
        self.key = f"quota:{user_id}:tokens"
        self.capacity = capacity
    
    def consume(self, tokens=1) -> bool:
        current = self.redis.get(self.key)
        if current is None:
            self.redis.set(self.key, self.capacity, ex=86400)  # 24h expiry
            current = self.capacity
        
        if int(current) >= tokens:
            self.redis.decrby(self.key, tokens)
            return True
        return False
```

---

### High-Priority Issues (Implement Within 2 Weeks)

#### 4. **Prompt Injection Vulnerability**
- **Location**: `backend/routers/llm.py`
- **Risk**: User input directly to LLM; susceptible to instruction override attacks
- **Fix**: Input validation with suspicious pattern detection
- **Effort**: 1 hour

```python
# backend/schemas.py
from pydantic import BaseModel, Field, validator

class LLMChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    
    @validator('message')
    def check_injection_patterns(cls, v):
        dangerous = ["ignore all", "system prompt", "execute code", "as an administrator"]
        if any(p in v.lower() for p in dangerous):
            raise ValueError("Suspicious input detected")
        return v
```

---

#### 5. **No Structured Logging in Services**
- **Location**: `backend/services/*` (all service files)
- **Risk**: Difficult to debug production issues; no audit trail for failures
- **Fix**: Add logger to every service method
- **Effort**: 3–4 hours

```python
# backend/services/llm_service.py
import logging
logger = logging.getLogger(__name__)

class LLMService:
    async def chat(self, user_id: str, message: str):
        logger.info("LLM chat started", extra={
            'user_id': user_id,
            'message_length': len(message)
        })
        try:
            result = await self.openrouter.call_model([...])
            logger.info("LLM chat success", extra={'user_id': user_id})
            return result
        except OpenRouterError as e:
            logger.error("LLM chat failed", exc_info=True, extra={'user_id': user_id})
            raise
```

---

### Code Duplication Issues (Refactor Within 1 Month)

#### 6. **Resume Service Fragmentation**
- **Files**: `resume_generator.py`, `resume_customizer.py`, `resume_optimizer.py`
- **Issue**: Duplicate logic for resume text processing, scoring, HTML generation
- **Fix**: Create unified `ResumeService` abstraction
- **Effort**: 4–5 hours

```python
# backend/services/resume_service.py (new file)
class ResumeService:
    def __init__(self, db, llm_service, matcher):
        self.db = db
        self.llm = llm_service
        self.matcher = matcher
    
    async def generate(self, user_id: str, template='default') -> Resume:
        # Centralized logic from resume_generator.py
        pass
    
    async def customize(self, resume_id: str, jd: str) -> Resume:
        # Centralized logic from resume_customizer.py
        pass
    
    async def optimize(self, resume_id: str, jd: str) -> Resume:
        # Centralized logic from resume_optimizer.py
        pass
```

---

#### 7. **Duplicate API Client Boilerplate**
- **Files**: `openrouter_client.py`, `jsearch_client.py`, `tavily_client.py`
- **Issue**: Each implements own HTTP client, retry logic, error handling
- **Fix**: Create base `ExternalAPIClient` class
- **Effort**: 2–3 hours

```python
# backend/services/external_api_client.py (new file)
class ExternalAPIClient:
    async def call(self, method, url, params=None, json=None, timeout=15, max_retries=3):
        # Centralized: retries, timeouts, error handling
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url, json=json, timeout=timeout) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status >= 500:  # Server error, retry
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                                continue
                        else:  # Client error, fail immediately
                            raise ClientError(await resp.text())
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    continue
                raise
```

---

## Refactoring Roadmap

### Phase 1: Stability (Week 1)
- [ ] Add template validation on startup (30 min)
- [ ] Add prompt injection detection (1 hour)
- [ ] Add circuit breaker to OpenRouter calls (2 hours)

### Phase 2: Observability (Week 2)
- [ ] Add structured logging to all services (4 hours)
- [ ] Add metrics/telemetry for API calls (2 hours)
- [ ] Implement distributed tracing (optional, 3 hours)

### Phase 3: Data Durability (Week 3)
- [ ] Migrate rate limiter to Redis (2 hours)
- [ ] Add comprehensive error handling to task queue (1 hour)

### Phase 4: Code Quality (Weeks 4–5)
- [ ] Consolidate resume services (5 hours)
- [ ] Consolidate API clients (3 hours)
- [ ] Add 100+ additional unit tests (8 hours)

---

## Operations & Deployment

### Local Development

**Prerequisites**:
```bash
Python 3.11+
Node.js 18+
Redis (local or Docker)
PostgreSQL (local or Docker)
```

**Setup**:
```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
npm install
npm run dev  # http://localhost:3000

# Background worker (separate terminal)
cd backend
arq worker.WorkerSettings

# Or use Docker Compose
docker-compose up -d
```

### Production Deployment

**Recommended**: Docker Compose + Caddy Reverse Proxy

```yaml
# docker-compose.yml (key services)
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: talvex
      POSTGRES_PASSWORD: ${DB_PASSWORD}
  
  redis:
    image: redis:7-alpine
  
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://user:pass@postgres/talvex
      REDIS_URL: redis://redis:6379
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
    ports:
      - "8000:8000"
  
  frontend:
    build: ./src
    ports:
      - "3000:3000"
  
  caddy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
```

**Environment Variables** (`.env.production`):
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:secure_password@postgres.example.com/talvex

# Redis
REDIS_URL=redis://redis.example.com:6379

# Auth
JWT_SECRET_KEY=<very-long-random-string-min-32-chars>
ADMIN_EMAIL=admin@talvex.app
ADMIN_PASSWORD=<secure-admin-password>

# APIs
OPENROUTER_API_KEY=<your-openrouter-key>
RAPIDAPI_KEY=<your-rapidapi-key>
TAVILY_API_KEY=<your-tavily-key>

# Model Configuration
OPENROUTER_MODEL_SEARCHER=openai/gpt-oss-120b:free
OPENROUTER_MODEL_PARSER=deepseek/deepseek-v4-flash:free
OPENROUTER_MODEL_ARCHITECT=openai/gpt-oss-120b:free
OPENROUTER_MODEL_BUILDER=deepseek/deepseek-v4-flash:free
```

### Monitoring

**Endpoints for Ops**:
```bash
# System health
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.talvex.app/api/admin/system/health

# Recent errors
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.talvex.app/api/admin/stats/errors

# Rate limit hits (last 24h)
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.talvex.app/api/admin/stats/rate-limits
```

---

## Contact & Maintenance

- **Owner**: Nawaz Khan (@Nawaz-khan-droid)
- **Repository**: https://github.com/Nawaz-khan-droid/Talvex
- **Issues**: Tracked via GitHub Issues

---

**Last Updated**: 2026-05-30  
**Next Review**: 2026-06-30
