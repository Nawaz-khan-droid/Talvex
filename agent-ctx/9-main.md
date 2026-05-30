# Task ID: 9 — Work Record
## Agent: Main
## Task: Replace hardcoded keyword recommendation system with LLM + web search

### Files Modified
1. **`src/app/api/recommendations/route.ts`** — Complete rewrite (~280 lines)
2. **`backend/routers/recommendations.py`** — LLM-powered update (~290 lines)

### What Changed

#### `src/app/api/recommendations/route.ts`
- **Removed** all hardcoded data: `SKILL_TAXONOMY` (6 categories, 50+ skills), `SALARY_BENCHMARKS` (10 roles), `MARKET_DEMAND` (27 skills with scores), and 8 static helper functions
- **Added** `callLLM()` — routes through internal `/api/llm` proxy using the `architect` model (hermes-3-405b)
- **Added** `analyzeWithLLM()` — sends persona skills + job context + pipeline data to LLM with a structured system prompt requesting JSON
- **Added** `extractJSON()` — handles LLM responses wrapped in ```json code fences
- **Added** 3 sanitizer functions that reject garbage entries via regex (`/^\d+$/`, `/^[\/\d\s,.\-]+$/`)
- **Kept** DB-based pipeline telemetry unchanged
- **Kept** same POST signature `{ personaId?, applicationId?, query? }`
- **Kept** same `RecommendationData` response type

#### `backend/routers/recommendations.py`
- **Removed** hardcoded `role_profiles` list (5 static roles)
- **Added** `_llm_skill_gap()` and `_llm_trade_recs()` async functions using `openrouter_client`
- **Added** fallback to `matcher.analyze_skill_gap()` when OpenRouter fails
- **Changed** `get_skill_gap` and `get_trade_recommendations` from `def` to `async def`
- **Kept** pipeline telemetry and follow-up endpoints unchanged

### New Recommendation Flow
```
POST /api/recommendations
  ├── Fetch persona skills from DB
  ├── Fetch application context (job title, JD) from DB
  ├── Build pipeline telemetry from DB (no LLM needed)
  ├── Call /api/llm (architect model) with:
  │   ├── System prompt: structured JSON schema + 7 critical rules
  │   └── User prompt: skills + job context + target roles + query
  ├── Parse LLM JSON response (handle code fences)
  ├── Sanitize: reject garbage entries, clamp values, validate enums
  └── Return RecommendationData matching existing TypeScript type
```
