# AI PM Autonomous Learning & Intelligence System

> **Production-grade, autonomous daily learning system for AI Product Managers.** Curates, summarizes, and tests AI/ML knowledge from 42 RSS feeds using Google Gemini — running entirely on free infrastructure.

---

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd ai-pm-learning-system
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

**Required env vars:**
- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/app/apikey)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` — Google OAuth2 (Drive + Gmail)
- `API_KEY`, `CRON_SECRET` — Generate strong random secrets
- `DASHBOARD_USER`, `DASHBOARD_PASS`, `CSRF_SECRET` — Dashboard auth
- `SENDER_EMAIL`, `RECIPIENT_EMAIL` — Gmail sender and recipient

### 3. Run Locally

```bash
uvicorn app.main:app --reload --port 8000
```

Visit: `http://localhost:8000/dashboard` (use your `DASHBOARD_USER`/`DASHBOARD_PASS`)

### 4. Deploy to Render

1. Push to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect your repo — Render auto-detects `render.yaml`
4. Add all environment variables from `.env.example` in Render's dashboard
5. Deploy

### 5. Configure cron-job.org (4 jobs)

| Job | URL | Schedule (IST) |
|-----|-----|----------------|
| Morning RSS | `POST /trigger/rss` | `25 2 * * *` (07:55 IST) |
| Midday RSS | `POST /trigger/rss` | `25 6 * * *` (11:55 IST) |
| Evening RSS | `POST /trigger/rss` | `25 11 * * *` (16:55 IST) |
| Email Digest | `POST /trigger/email` | `0 3 * * *` (08:30 IST) |
| Keep-Alive | `GET /api/ping` | `*/14 * * * *` |

All trigger requests must include header `X-Cron-Secret: <your CRON_SECRET>`.

---

## Architecture

```
External Cron (cron-job.org)
    ↓ X-Cron-Secret
FastAPI on Render (stateless)
    ↓
Google Drive JSON files (6 core files)
    ↓
Google Gemini API (AI scoring, summarization, grading)
    ↓
Gmail API (daily email digest)
```

**State files on Google Drive (`AI_PM_SYSTEM/` folder):**
| File | Purpose |
|------|---------|
| `topics.json` | Active learning topics |
| `archived_topics.json` | Completed/inactive topics |
| `metrics.json` | Cost tracking, streak, adaptive mode |
| `cache.json` | URL dedup + summary + grading cache |
| `pipeline_state.json` | Today's slot status + RPD counters |
| `discarded.json` | Rejected articles (capped 500) |
| `errors.json` | System errors (capped 200) |
| `rss_sources.json` | 42 feed configs with failure tracking |

---

## Key Design Decisions & Loophole Fixes

| Fix | Description |
|-----|-------------|
| **L2-02** | Cleanup runs as part of morning RSS trigger (no 5th cron job) |
| **L2-03** | Grading cache = display-only (no state advance on cache hit) |
| **L2-04** | ETag-based optimistic locking on all Drive writes |
| **L2-05** | Zero-grading days are **neutral** — don't affect low/recovery counters |
| **L2-06** | Evening carry-over queue for overflow articles |
| **L2-07** | Single `MODE_CONFIG` source of truth for adaptive mode thresholds |
| **L2-08** | RPD-aware grading model selection with fallback to bulk |
| **L2-09** | `/tmp/` fallback + startup sync for Drive outages |
| **L2-10** | Streak = consecutive email_sent days (not grading days) |
| **L2-11** | Two-phase title dedup (85% definite, 60-85% Gemini confirm) |
| **L2-12** | Single combined Gemini call for 5 dims + credibility + promo |
| **L2-13** | Dual auth on `/api/grade` (API Key OR Basic Auth) |
| **L2-14** | Reteaching auto-revert after 14 days |
| **L2-15** | `mastery_score` = latest grade score |
| **L2-17** | Gemini model deprecation fallback with alert email |
| **L2-18** | Separate `BLOCKED_DOMAINS` + `BLOCKED_URL_PATTERNS` lists |
| **L2-19** | Dual auth on `/api/dashboard-data` |
| **L2-20** | Summary cache key = `SHA256(url + extraction_method)` |

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/trigger/rss` | X-Cron-Secret | Run RSS pipeline for current slot |
| POST | `/trigger/email` | X-Cron-Secret | Send daily email digest |
| POST | `/trigger/weekly` | X-Cron-Secret | Run weekly backup |
| GET | `/api/ping` | None | Keep-alive (cron every 14 min) |
| GET | `/api/health` | None | System health check |
| POST | `/api/grade` | API Key or Basic Auth | Grade an answer |
| GET | `/api/dashboard-data` | API Key or Basic Auth | JSON dashboard data |
| GET | `/dashboard` | Basic Auth | HTML dashboard |
| GET | `/dashboard/topic/{id}` | Basic Auth | Topic detail + grading form |
| GET | `/dashboard/discarded` | Basic Auth | Discarded articles |
| GET | `/dashboard/errors` | Basic Auth | Error log |

---

## Cost Model

All Gemini usage uses free tier (90-150 RPD limits):
- **Bulk model** (`gemini-2.0-flash-lite`): $0.075/M input + $0.30/M output
- **Grade model** (`gemini-2.5-flash`): higher quality, limited to 100 RPD

**Budget guards:**
- Yellow at ₹90/month (~$1.06): disable faithfulness checks
- Red at ₹95/month (~$1.12): disable ALL Gemini + alert email

---

## Testing

```bash
pytest tests/ -v
```

Tests cover: adaptive mode, deduplication, grading cache, RSS pipeline utilities, and scoring logic. All tests are pure unit tests (no Drive/Gemini calls).

---

## Tech Stack

- **Runtime:** Python 3.11, FastAPI, Uvicorn
- **AI:** Google Gemini API (`google-generativeai`)
- **Storage:** Google Drive (JSON files) via `google-api-python-client`
- **Email:** Gmail API
- **Content:** `feedparser`, `trafilatura`, `readability-lxml`, `newspaper3k`
- **Dedup:** `fuzzywuzzy`, SHA-256 hashing
- **Infra:** Render (free tier), cron-job.org
