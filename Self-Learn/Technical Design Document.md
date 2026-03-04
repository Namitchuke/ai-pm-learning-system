# TDD: AI PM Autonomous Learning & Intelligence System

**Version**: 2.0
**Date**: 2026-02-17
**Status**: Draft
**Based on**: PRD v2.0 (2026-02-15), FRD v2.0 (2026-02-16)

---

## System Architecture

### Architecture Overview

The AI PM Autonomous Learning System follows a **stateless, event-triggered architecture** designed for free-tier infrastructure constraints. The system operates without persistent processes, relying entirely on external HTTP triggers to initiate all operations.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL TRIGGERS                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ cron-job.org │  │ cron-job.org │  │ cron-job.org │  │ cron-job.org │         │
│  │  RSS Morning │  │  RSS Midday  │  │ RSS Evening  │  │  Email Send  │         │
│  │   7:55 AM    │  │  11:55 AM    │  │   4:55 PM    │  │   12:25 PM   │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                 │                 │
│         └─────────────────┴────────┬────────┴─────────────────┘                 │
│                                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         RENDER FREE TIER                                 │   │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │   │
│  │  │                    FastAPI Application                             │  │   │
│  │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐  │  │   │
│  │  │  │   Trigger   │ │   Pipeline  │ │   Grading   │ │  Dashboard  │  │  │   │
│  │  │  │  Endpoints  │ │   Engine    │ │   Engine    │ │   Routes    │  │  │   │
│  │  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘  │  │   │
│  │  │         │               │               │               │         │  │   │
│  │  │  ┌──────┴───────────────┴───────────────┴───────────────┴──────┐  │  │   │
│  │  │  │                    Core Services Layer                       │  │  │   │
│  │  │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     │  │  │   │
│  │  │  │  │  RSS   │ │Scoring │ │Summary │ │ Topic  │ │ Email  │     │  │  │   │
│  │  │  │  │Fetcher │ │Service │ │Service │ │Selector│ │Service │     │  │  │   │
│  │  │  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘     │  │  │   │
│  │  │  └──────────────────────────┬──────────────────────────────────┘  │  │   │
│  │  │                             │                                      │  │   │
│  │  │  ┌──────────────────────────┴──────────────────────────────────┐  │  │   │
│  │  │  │                    Infrastructure Layer                      │  │  │   │
│  │  │  │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐ ┌───────┐  │  │  │   │
│  │  │  │  │ Gemini  │ │  Drive   │ │  Gmail  │ │ Cache  │ │ Cost  │  │  │  │   │
│  │  │  │  │ Client  │ │  Client  │ │  Client │ │Manager │ │Tracker│  │  │  │   │
│  │  │  │  └────┬────┘ └────┬─────┘ └────┬────┘ └────────┘ └───────┘  │  │  │   │
│  │  │  └───────┼───────────┼────────────┼────────────────────────────┘  │  │   │
│  │  └──────────┼───────────┼────────────┼────────────────────────────────┘  │   │
│  └─────────────┼───────────┼────────────┼────────────────────────────────────┘   │
│                │           │            │                                        │
└────────────────┼───────────┼────────────┼────────────────────────────────────────┘
                 │           │            │
        ┌────────┴───┐  ┌────┴────┐  ┌────┴────┐
        │   Gemini   │  │ Google  │  │  Gmail  │
        │    API     │  │  Drive  │  │   API   │
        └────────────┘  └─────────┘  └─────────┘
```

### Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Stateless** | No in-memory state between requests. All state persisted to Google Drive JSON |
| **Event-Triggered** | All operations initiated by external HTTP calls (cron-job.org) |
| **Graceful Degradation** | System continues with partial functionality on component failures |
| **Cost-Aware** | Every Gemini call tracked; automatic fallback and kill switches |
| **Idempotent** | Per-slot tracking ensures re-triggers don't duplicate work |

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               APPLICATION LAYER                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │   main.py       │  │   config.py     │  │   models.py     │               │
│  │   FastAPI app   │  │   Settings      │  │   Pydantic      │               │
│  │   Lifespan      │  │   Env vars      │  │   schemas       │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
│                                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                 ROUTERS                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │ triggers.py     │  │ dashboard.py    │  │ api.py          │               │
│  │ /api/trigger/*  │  │ /dashboard      │  │ /api/grade      │               │
│  │ RSS, Email      │  │ /topic/{id}     │  │ /api/dashboard- │               │
│  │                 │  │ /discarded      │  │      data       │               │
│  │                 │  │ /health         │  │                 │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
│                                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                               CORE SERVICES                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │rss_pipeline  │ │scoring       │ │summarizer    │ │topic_selector│         │
│  │.py           │ │.py           │ │.py           │ │.py           │         │
│  │              │ │              │ │              │ │              │         │
│  │- fetch_feeds │ │- score_      │ │- extract_    │ │- select_     │         │
│  │- extract_    │ │  article     │ │  sentences   │ │  daily_mix   │         │
│  │  content     │ │- combined_   │ │- summarize   │ │- evening_    │         │
│  │- filter_     │ │  scoring     │ │- verify_     │ │  carry_over  │         │
│  │  duplicates  │ │              │ │  faithfulness│ │- balance_    │         │
│  └──────────────┘ └──────────────┘ └──────────────┘ │  categories  │         │
│                                                      └──────────────┘         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │grading       │ │email_service │ │adaptive_mode │ │quarterly_    │         │
│  │.py           │ │.py           │ │.py           │ │report.py     │         │
│  │              │ │              │ │              │ │              │         │
│  │- grade_      │ │- generate_   │ │- update_mode │ │- generate_   │         │
│  │  answer      │ │  email       │ │- check_      │ │  report      │         │
│  │- reteaching  │ │- send_via_   │ │  recovery    │ │- calculate_  │         │
│  │- cache_      │ │  gmail       │ │- pause_state │ │  metrics     │         │
│  │  lookup      │ │- streak_     │ │              │ │              │         │
│  │              │ │  tracking    │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                            INFRASTRUCTURE LAYER                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │gemini_client │ │drive_client  │ │gmail_client  │ │cache_manager │         │
│  │.py           │ │.py           │ │.py           │ │.py           │         │
│  │              │ │              │ │              │ │              │         │
│  │- call_gemini │ │- read_file   │ │- send_email  │ │- get/set     │         │
│  │- track_rpd   │ │- write_with_ │ │- refresh_    │ │- evict       │         │
│  │- model_      │ │  etag        │ │  token       │ │- ttl_check   │         │
│  │  fallback    │ │- backup      │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │cost_tracker  │ │auth          │ │rate_limiter  │ │logging       │         │
│  │.py           │ │.py           │ │.py           │ │.py           │         │
│  │              │ │              │ │              │ │              │         │
│  │- log_call    │ │- verify_     │ │- slowapi     │ │- loguru      │         │
│  │- check_      │ │  api_key     │ │  middleware  │ │  setup       │         │
│  │  budget      │ │- verify_     │ │- per_ip      │ │- structured  │         │
│  │- kill_switch │ │  basic_auth  │ │  tracking    │ │  json        │         │
│  │              │ │- csrf_verify │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                               UTILITIES                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │extractors.py │ │dedup.py      │ │timezone.py   │ │validators.py │         │
│  │              │ │              │ │              │ │              │         │
│  │- trafilatura │ │- url_hash    │ │- ist_convert │ │- schema_     │         │
│  │- readability │ │- title_fuzzy │ │- slot_detect │ │  validate    │         │
│  │- newspaper3k │ │- gemini_     │ │- date_gate   │ │- json_parse  │         │
│  │              │ │  confirm     │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
ai-pm-learning-system/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, lifespan, middleware
│   ├── config.py                  # Settings from env vars (Pydantic BaseSettings)
│   ├── models.py                  # Pydantic models for all data structures
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── triggers.py            # /api/trigger/* endpoints
│   │   ├── dashboard.py           # Dashboard HTML routes
│   │   └── api.py                 # /api/grade, /api/dashboard-data, /health
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rss_pipeline.py        # RSS fetching, content extraction
│   │   ├── scoring.py             # Combined relevance + credibility scoring
│   │   ├── summarizer.py          # 3-step anti-hallucination pipeline
│   │   ├── topic_selector.py      # Daily topic selection + evening carry-over
│   │   ├── grading.py             # Answer grading + reteaching
│   │   ├── email_service.py       # Email generation + sending
│   │   ├── adaptive_mode.py       # Unified mode state machine
│   │   ├── quarterly_report.py    # Quarterly report generation
│   │   └── cleanup.py             # Daily cleanup, archival, cache eviction
│   │
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── gemini_client.py       # Gemini API wrapper with RPD tracking
│   │   ├── drive_client.py        # Google Drive with ETag locking
│   │   └── gmail_client.py        # Gmail API for sending
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── auth.py                # API key, Basic Auth, CSRF verification
│   │   ├── rate_limiter.py        # slowapi configuration
│   │   ├── cache_manager.py       # In-memory + Drive cache coordination
│   │   ├── cost_tracker.py        # API cost tracking + kill switch
│   │   └── logging.py             # loguru setup, structured JSON
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── extractors.py          # Layered content extraction
│   │   ├── dedup.py               # URL + title deduplication
│   │   ├── timezone.py            # IST handling, slot detection
│   │   └── validators.py          # Schema validation, JSON parsing
│   │
│   └── templates/                 # Jinja2 templates
│       ├── base.html
│       ├── dashboard.html
│       ├── topic_detail.html
│       ├── discarded.html
│       ├── health.html
│       ├── email_html.html
│       └── email_plain.txt
│
├── prompts/                       # Gemini prompt templates
│   ├── scoring.txt
│   ├── scoring_examples.json
│   ├── extraction.txt
│   ├── summarization.txt
│   ├── faithfulness.txt
│   ├── grading.txt
│   ├── grading_examples.json
│   └── reteach.txt
│
├── tests/
│   ├── __init__.py
│   ├── test_rss_pipeline.py
│   ├── test_scoring.py
│   ├── test_summarizer.py
│   ├── test_grading.py
│   ├── test_adaptive_mode.py
│   ├── test_drive_client.py
│   └── conftest.py                # Pytest fixtures
│
├── requirements.txt
├── render.yaml                    # Render deployment config
├── .env.example                   # Environment variable template
└── README.md
```

---

## Data Model

### Storage Architecture

All data persisted to Google Drive folder `AI_PM_SYSTEM/` as JSON files with schema versioning.

```
AI_PM_SYSTEM/
├── rss_sources.json              # RSS feed configuration (42 feeds)
├── topics.json                   # Active topics
├── archived_topics.json          # Completed/inactive topics
├── metrics.json                  # Aggregated metrics + adaptive state
├── cache.json                    # URL dedup + grading + summary cache
├── pipeline_state.json           # Current pipeline status (per-slot)
├── discarded.json                # Rejected articles (max 500)
├── errors.json                   # Error log (max 200)
├── daily_logs_{YYYY_MM}.json     # Monthly partitioned logs
├── system_logs_{YYYY_MM}.json    # Monthly system logs
├── quarterly_reports_{YYYY}.json # Yearly quarterly reports
└── backups/
    └── {YYYY-MM-DD}/             # Weekly full backups
```

### Entity Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────┐
│    RSS_SOURCE       │       │    TOPIC            │
├─────────────────────┤       ├─────────────────────┤
│ source_id (PK)      │       │ topic_id (PK)       │
│ name                │       │ topic_name          │
│ feed_url            │──────▶│ source_url          │
│ tier                │       │ source_tier (FK)    │
│ category_bias       │       │ category            │
│ enabled             │       │ current_depth       │
│ consecutive_failures│       │ mastery_score       │
│ last_success        │       │ status              │
└─────────────────────┘       │ retries_used        │
                              │ credibility_score   │
                              │ faithfulness_score  │
                              │ extraction_method   │
                              │ reteaching_entered_at│
                              │ summary {}          │
                              │ history []          │
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┴────────────────────┐
                    │                                         │
                    ▼                                         ▼
┌─────────────────────────┐               ┌─────────────────────────┐
│    GRADING_HISTORY      │               │    CACHE_ENTRY          │
├─────────────────────────┤               ├─────────────────────────┤
│ date                    │               │ cache_key (PK)          │
│ depth                   │               │ added_at                │
│ score                   │               │ ttl_days                │
│ answer_hash             │               │ result {} | summary {}  │
│ decision                │               │ submission_count        │
│ feedback                │               └─────────────────────────┘
│ model_used              │
│ cached                  │
│ reteach_content         │
└─────────────────────────┘

┌─────────────────────────┐               ┌─────────────────────────┐
│    PIPELINE_STATE       │               │    METRICS              │
├─────────────────────────┤               ├─────────────────────────┤
│ date                    │               │ streak_count            │
│ slots: {                │               │ streak_start_date       │
│   morning: SlotState    │               │ longest_streak          │
│   midday: SlotState     │               │ current_topic_mode      │
│   evening: SlotState    │               │ consecutive_low_days    │
│ }                       │               │ consecutive_recovery_days│
│ email_sent              │               │ consecutive_neutral_days│
│ next_day_priority_queue │               │ daily_mastery_averages  │
│ daily_rpd {}            │               │ weekly_category_distrib │
└─────────────────────────┘               │ topic_reduction_history │
                                          │ monthly_cost_tracker    │
                                          └─────────────────────────┘
```

### Complete JSON Schemas

#### pipeline_state.json (v2.0)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "date", "slots", "email_sent", "next_day_priority_queue", "daily_rpd"],
  "properties": {
    "schema_version": { "const": "2.0" },
    "date": { "type": "string", "format": "date" },
    "slots": {
      "type": "object",
      "properties": {
        "morning": { "$ref": "#/definitions/SlotState" },
        "midday": { "$ref": "#/definitions/SlotState" },
        "evening": { "$ref": "#/definitions/SlotState" }
      },
      "required": ["morning", "midday", "evening"]
    },
    "email_sent": { "type": "boolean" },
    "next_day_priority_queue": {
      "type": "array",
      "items": { "$ref": "#/definitions/QueuedArticle" }
    },
    "daily_rpd": {
      "type": "object",
      "additionalProperties": { "type": "integer" }
    }
  },
  "definitions": {
    "SlotState": {
      "type": "object",
      "properties": {
        "run_id": { "type": ["string", "null"] },
        "status": { "enum": ["PENDING", "FETCHING", "SCORING", "SUMMARIZING", "SELECTING", "DONE", "FAILED"] },
        "started_at": { "type": ["string", "null"], "format": "date-time" },
        "completed_at": { "type": ["string", "null"], "format": "date-time" },
        "articles_fetched": { "type": "integer" },
        "articles_new": { "type": "integer" },
        "articles_scored": { "type": "integer" },
        "articles_passed": { "type": "integer" },
        "articles_summarized": { "type": "integer" },
        "topics_selected": { "type": "integer" },
        "errors": { "type": "array", "items": { "type": "object" } },
        "cleanup_ran": { "type": "boolean" },
        "backup_ran": { "type": "boolean" },
        "quarterly_ran": { "type": "boolean" }
      }
    },
    "QueuedArticle": {
      "type": "object",
      "properties": {
        "url": { "type": "string" },
        "url_hash": { "type": "string" },
        "title": { "type": "string" },
        "source_name": { "type": "string" },
        "source_tier": { "type": "integer" },
        "category_bias": { "type": "string" },
        "summary": { "type": "object" },
        "scores": { "type": "object" },
        "added_at": { "type": "string", "format": "date-time" }
      }
    }
  }
}
```

#### topics.json (v2.0)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "last_updated", "topics"],
  "properties": {
    "schema_version": { "const": "2.0" },
    "last_updated": { "type": "string", "format": "date-time" },
    "topics": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["topic_id", "topic_name", "category", "current_depth", "status"],
        "properties": {
          "topic_id": { "type": "string", "format": "uuid" },
          "topic_name": { "type": "string" },
          "category": { "enum": ["ml_engineering", "product_strategy", "mlops", "ai_ethics", "infrastructure"] },
          "current_depth": { "type": "integer", "minimum": 1, "maximum": 5 },
          "mastery_score": { "type": "number", "minimum": 0, "maximum": 100 },
          "status": { "enum": ["active", "completed", "archived", "reteaching"] },
          "retries_used": { "type": "integer", "minimum": 0, "maximum": 2 },
          "source_url": { "type": "string", "format": "uri" },
          "source_title": { "type": "string" },
          "source_tier": { "type": "integer", "minimum": 1, "maximum": 6 },
          "credibility_score": { "type": "number" },
          "faithfulness_score": { "type": "number" },
          "extraction_method": { "enum": ["trafilatura", "readability", "newspaper3k", "rss_description"] },
          "created_at": { "type": "string", "format": "date-time" },
          "last_updated": { "type": "string", "format": "date-time" },
          "last_active": { "type": "string", "format": "date-time" },
          "reteaching_entered_at": { "type": ["string", "null"], "format": "date-time" },
          "summary": { "$ref": "#/definitions/Summary" },
          "history": { "type": "array", "items": { "$ref": "#/definitions/HistoryEntry" } }
        }
      }
    }
  },
  "definitions": {
    "Summary": {
      "type": "object",
      "properties": {
        "why_it_matters": { "type": "string" },
        "core_mechanism": { "type": "string" },
        "product_applications": { "type": "string" },
        "risks_limitations": { "type": "string" },
        "key_takeaways": { "type": "array", "items": { "type": "string" } },
        "tldr": { "type": "string" },
        "keywords_glossary": { "type": "object", "additionalProperties": { "type": "string" } }
      }
    },
    "HistoryEntry": {
      "type": "object",
      "properties": {
        "date": { "type": "string", "format": "date-time" },
        "depth": { "type": "integer" },
        "score": { "type": "number" },
        "answer_hash": { "type": "string" },
        "decision": { "enum": ["advance", "retry", "reteach"] },
        "feedback": { "type": "string" },
        "model_used": { "type": "string" },
        "cached": { "type": "boolean" },
        "reteach_content": { "type": ["object", "null"] }
      }
    }
  }
}
```

---

## API Design

### Endpoint Inventory

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/trigger/rss-fetch` | GET | X-Cron-Secret | Trigger RSS pipeline for current slot |
| `/api/trigger/email-send` | GET | X-Cron-Secret | Trigger email generation and sending |
| `/api/grade` | POST | Dual-auth | Submit and grade answer |
| `/api/dashboard-data` | GET | Dual-auth | JSON data for dashboard |
| `/health` | GET | X-API-Key | System health check |
| `/dashboard` | GET | Basic Auth | Main dashboard HTML |
| `/topic/{topic_id}` | GET | Basic Auth | Topic detail HTML |
| `/discarded` | GET | Basic Auth | Discarded insights HTML |

### API Contracts

#### POST /api/grade

**Request:**
```http
POST /api/grade HTTP/1.1
Content-Type: application/json
X-API-Key: {api_key}

{
  "topic_id": "550e8400-e29b-41d4-a716-446655440000",
  "answer_text": "The transformer architecture..."
}
```

**OR (Basic Auth + CSRF):**
```http
POST /api/grade HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {base64(user:pass)}
Cookie: csrf_token=...

topic_id=550e8400...&answer_text=The+transformer...&csrf_token=...
```

**Response (200 OK):**
```json
{
  "success": true,
  "topic_id": "550e8400-e29b-41d4-a716-446655440000",
  "topic_name": "Transformer Architecture",
  "depth": 2,
  "score": 78,
  "breakdown": {
    "concept_clarity": 22,
    "technical_correctness": 24,
    "application_thinking": 16,
    "ai_pm_relevance": 16
  },
  "feedback": "Strong technical understanding. Consider adding deployment metrics.",
  "decision": "advance",
  "new_depth": 3,
  "retries_remaining": 2,
  "model_used": "gemini-2.5-flash",
  "quality_warning": null,
  "cached": false
}
```

**Response (200 OK - Cache Hit, L2-03):**
```json
{
  "success": true,
  "topic_id": "550e8400-e29b-41d4-a716-446655440000",
  "score": 78,
  "breakdown": {...},
  "feedback": "...",
  "decision": "advance",
  "cached": true,
  "message": "This is a cached result. No progress changes applied. Modify your answer for fresh evaluation."
}
```

**Error Responses:**
- `401 Unauthorized`: Invalid authentication
- `400 Bad Request`: Answer too short (<50 words)
- `429 Too Many Requests`: Rate limit exceeded
- `404 Not Found`: Topic not found

#### GET /api/trigger/rss-fetch

**Request:**
```http
GET /api/trigger/rss-fetch HTTP/1.1
X-Cron-Secret: {cron_secret}
```

**Response (200 OK):**
```json
{
  "status": "completed",
  "slot": "morning",
  "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "RSS pipeline completed: 45 fetched, 12 new, 8 scored, 5 passed, 5 summarized",
  "duration_seconds": 42,
  "cleanup_ran": true,
  "backup_ran": false,
  "quarterly_ran": false
}
```

**Response (200 OK - Already Done):**
```json
{
  "status": "skipped",
  "slot": "morning",
  "message": "Slot already completed for 2026-02-17",
  "last_run": "2026-02-17T02:25:00Z"
}
```

#### GET /health

**Response (200 OK):**
```json
{
  "status": "healthy",
  "last_rss_fetch": {
    "morning": "2026-02-17T02:25:00Z",
    "midday": null,
    "evening": null
  },
  "last_email_sent": "2026-02-16T06:55:00Z",
  "oauth_token_valid": true,
  "daily_token_usage": {
    "input": 11000,
    "output": 7500,
    "cost_usd": 0.004
  },
  "monthly_token_usage": {
    "input": 330000,
    "output": 225000,
    "cost_usd": 0.124
  },
  "daily_rpd": {
    "gemini-2.0-flash-lite": 45,
    "gemini-2.5-flash": 12
  },
  "errors_last_24h": 2,
  "pipeline_state": {
    "morning": "DONE",
    "midday": "PENDING",
    "evening": "PENDING"
  },
  "adaptive_mode": "normal",
  "streak": 15,
  "active_feeds": 42,
  "disabled_feeds": 0
}
```

---

## Security

### Authentication

#### Primary: API Key

```python
# app/core/auth.py
from fastapi import HTTPException, Header
import os

async def verify_api_key(x_api_key: str = Header(None)) -> bool:
    if not x_api_key or x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
```

#### Secondary: HTTP Basic Auth

```python
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

async def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf8"),
        os.getenv("DASHBOARD_USER", "").encode("utf8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        os.getenv("DASHBOARD_PASS", "").encode("utf8")
    )
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return True
```

#### Dual-Auth for API Endpoints (L2-13, L2-19)

```python
async def dual_auth(
    request: Request,
    x_api_key: str = Header(None),
    credentials: Optional[HTTPBasicCredentials] = Depends(security_optional)
) -> bool:
    """Accept either API key OR Basic Auth."""
    # Method 1: API Key
    if x_api_key and x_api_key == os.getenv("API_KEY"):
        return True

    # Method 2: Basic Auth
    if credentials:
        if (credentials.username == os.getenv("DASHBOARD_USER") and
            credentials.password == os.getenv("DASHBOARD_PASS")):
            return True

    raise HTTPException(status_code=401, detail="Authentication required")
```

#### Cron Secret

```python
async def verify_cron_secret(x_cron_secret: str = Header(None)) -> bool:
    if not x_cron_secret or x_cron_secret != os.getenv("CRON_SECRET"):
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    return True
```

### CSRF Protection

```python
# Using fastapi-csrf-protect
from fastapi_csrf_protect import CsrfProtect

@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings(secret_key=os.getenv("CSRF_SECRET"))

# In form-handling routes
@router.post("/api/grade")
async def grade_answer(
    request: Request,
    csrf_protect: CsrfProtect = Depends()
):
    # If Basic Auth path, verify CSRF
    if is_basic_auth_request(request):
        await csrf_protect.validate_csrf(request)
    # ... rest of handler
```

### Rate Limiting

```python
# app/core/rate_limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Rate limits per endpoint type
RATE_LIMITS = {
    "dashboard": "60/minute",
    "grading": "5/minute",
    "triggers": "10/minute",
    "health": "30/minute"
}
```

### Data Protection

| Data Type | Protection |
|-----------|------------|
| API Keys | Render env vars (never in code) |
| OAuth Tokens | Render env vars + auto-refresh |
| User Answers | SHA-256 hashed for cache keys |
| Passwords | HTTP Basic Auth (TLS encrypted) |
| CSRF Tokens | Double Submit Cookie pattern |

### Environment Variables

```env
# Authentication
API_KEY=                      # Primary API key for programmatic access
CRON_SECRET=                  # Separate secret for cron triggers
DASHBOARD_USER=               # Basic Auth username
DASHBOARD_PASS=               # Basic Auth password
CSRF_SECRET=                  # CSRF token signing key

# Google APIs
GEMINI_API_KEY=               # Gemini API access
GOOGLE_CLIENT_ID=             # OAuth client ID
GOOGLE_CLIENT_SECRET=         # OAuth client secret
GOOGLE_REFRESH_TOKEN=         # Long-lived refresh token

# Email
SENDER_EMAIL=                 # Gmail address to send from
RECIPIENT_EMAIL=              # Recipient address

# Model Configuration (L2-17)
GEMINI_BULK_MODEL=gemini-2.0-flash-lite    # Bulk operations
GEMINI_GRADE_MODEL=gemini-2.5-flash        # Grading
```

---

## Deployment

### Infrastructure

#### Render Configuration (render.yaml)

```yaml
services:
  - type: web
    name: ai-pm-learning
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: API_KEY
        sync: false
      - key: CRON_SECRET
        sync: false
      - key: DASHBOARD_USER
        sync: false
      - key: DASHBOARD_PASS
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: GOOGLE_REFRESH_TOKEN
        sync: false
      - key: SENDER_EMAIL
        sync: false
      - key: RECIPIENT_EMAIL
        sync: false
      - key: GEMINI_BULK_MODEL
        value: gemini-2.0-flash-lite
      - key: GEMINI_GRADE_MODEL
        value: gemini-2.5-flash
```

#### Render Free Tier Constraints

| Resource | Limit | Mitigation |
|----------|-------|------------|
| RAM | 512 MB | Lightweight processing, no in-memory caching |
| CPU | 0.1 vCPU | Async operations, no CPU-intensive tasks |
| Instance Hours | 750/month | Acceptable (sleeps during inactivity) |
| Sleep After | 15 min | External cron wakes app |
| Cold Start | ~30 sec | cron-job.org 60s timeout + retry |

### cron-job.org Configuration

| Job | URL | Schedule (IST) | UTC | Timeout | Retry |
|-----|-----|----------------|-----|---------|-------|
| RSS Morning | `https://{app}.onrender.com/api/trigger/rss-fetch` | 7:55 AM | 2:25 AM | 60s | 1x after 5min |
| RSS Midday | Same URL | 11:55 AM | 6:25 AM | 60s | 1x after 5min |
| RSS Evening | Same URL | 4:55 PM | 11:25 AM | 60s | 1x after 5min |
| Email Send | `https://{app}.onrender.com/api/trigger/email-send` | 12:25 PM | 6:55 AM | 60s | 1x after 5min |

**Header on all jobs:** `X-Cron-Secret: {value}`

### CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy to Render

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio
      - run: pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Render
        uses: johnbeynon/render-deploy-action@v0.0.8
        with:
          service-id: ${{ secrets.RENDER_SERVICE_ID }}
          api-key: ${{ secrets.RENDER_API_KEY }}
```

---

## Testing Strategy

### Test Categories

| Category | Coverage | Tools |
|----------|----------|-------|
| Unit Tests | Core services, utilities | pytest, pytest-asyncio |
| Integration Tests | API endpoints, auth flows | pytest, httpx |
| Mock Tests | External APIs (Gemini, Drive) | pytest-mock, responses |
| Contract Tests | JSON schemas, API contracts | jsonschema |

### Example Test Cases

#### Unit Test: Adaptive Mode Transitions

```python
# tests/test_adaptive_mode.py
import pytest
from app.services.adaptive_mode import update_adaptive_mode

def test_transition_to_reduced_3_after_5_low_days():
    metrics = {
        "current_topic_mode": "normal",
        "consecutive_low_days": 4,
        "consecutive_recovery_days": 0,
        "consecutive_neutral_days": 0
    }

    result = update_adaptive_mode(metrics, today_avg=65.0, topics_graded=3)

    assert result == "reduced_3"
    assert metrics["consecutive_low_days"] == 5

def test_zero_grading_day_is_neutral():
    """L2-05 fix: Zero-grading days don't affect counters."""
    metrics = {
        "current_topic_mode": "reduced_3",
        "consecutive_low_days": 3,
        "consecutive_recovery_days": 0,
        "consecutive_neutral_days": 0
    }

    result = update_adaptive_mode(metrics, today_avg=0, topics_graded=0)

    assert result == "reduced_3"  # No change
    assert metrics["consecutive_low_days"] == 3  # Preserved
    assert metrics["consecutive_neutral_days"] == 1

def test_pause_after_7_neutral_days():
    """L2-05 fix: 7+ days without grading enters pause."""
    metrics = {
        "current_topic_mode": "normal",
        "consecutive_neutral_days": 6
    }

    result = update_adaptive_mode(metrics, today_avg=0, topics_graded=0)

    # Check that pause was logged
    assert metrics["consecutive_neutral_days"] == 7
```

#### Integration Test: Grading Cache Behavior

```python
# tests/test_grading.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_grading_cache_hit_no_state_transition():
    """L2-03 fix: Cache hit returns result but no state change."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # First submission
        response1 = await ac.post(
            "/api/grade",
            json={"topic_id": "test-topic", "answer_text": "..." * 50},
            headers={"X-API-Key": "test-key"}
        )
        assert response1.json()["cached"] == False
        original_depth = response1.json()["depth"]

        # Same submission again
        response2 = await ac.post(
            "/api/grade",
            json={"topic_id": "test-topic", "answer_text": "..." * 50},
            headers={"X-API-Key": "test-key"}
        )
        assert response2.json()["cached"] == True
        assert response2.json()["depth"] == original_depth  # No advancement
```

#### Mock Test: Gemini Client

```python
# tests/test_gemini_client.py
import pytest
from unittest.mock import patch, MagicMock
from app.clients.gemini_client import call_gemini, get_grading_model

@patch("app.clients.gemini_client.genai")
def test_rpd_fallback_at_90(mock_genai):
    """L2-08 fix: Fall back to bulk model at 90 RPD."""
    pipeline_state = {"daily_rpd": {"gemini-2.5-flash": 90}}

    model, quality_warning = get_grading_model(pipeline_state)

    assert model == "gemini-2.0-flash-lite"
    assert quality_warning == True

@patch("app.clients.gemini_client.genai")
def test_model_deprecation_fallback(mock_genai):
    """L2-17 fix: Fall back on 'model not found' error."""
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = \
        Exception("Model gemini-2.5-flash not found")

    # Should fall back to bulk model and log CRITICAL
    # ... test implementation
```

### Coverage Requirements

| Module | Minimum Coverage |
|--------|------------------|
| adaptive_mode.py | 95% |
| grading.py | 90% |
| topic_selector.py | 85% |
| drive_client.py | 85% |
| rss_pipeline.py | 80% |
| Overall | 80% |

---

## Performance Requirements

### Response Time Targets

| Operation | Target | Max |
|-----------|--------|-----|
| Dashboard page load | < 3s | 5s (cold start) |
| Dashboard data API | < 2s | 4s |
| Grading submission | < 5s | 8s |
| Health check | < 500ms | 2s |
| RSS trigger response | < 1s | 2s (ack before background work) |

### Throughput Targets

| Metric | Target |
|--------|--------|
| Daily emails sent | 1 (100% delivery) |
| Articles processed/day | 50-100 |
| Topics selected/day | 1-5 (adaptive) |
| Grading submissions/day | ~5 (user-dependent) |

### Resource Optimization

```python
# Use BackgroundTasks for long-running operations
from fastapi import BackgroundTasks

@router.get("/api/trigger/rss-fetch")
async def trigger_rss(background_tasks: BackgroundTasks):
    # Acknowledge immediately
    run_id = str(uuid.uuid4())

    # Queue actual work
    background_tasks.add_task(run_rss_pipeline, run_id)

    return {"status": "accepted", "run_id": run_id}
```

### Memory Management

```python
# Stream large responses instead of loading all in memory
async def stream_articles(feeds: list[str]):
    for feed in feeds:
        articles = await fetch_feed(feed)
        for article in articles:
            yield article
            # Allow GC between articles
```

---

## Error Handling

### Error Categories

| Category | Handling | Example |
|----------|----------|---------|
| Transient | Retry with backoff | Network timeout, 429 |
| Recoverable | Log + continue | Single feed failure |
| Critical | Alert + graceful degrade | OAuth invalid, budget exceeded |
| Fatal | Stop + alert | Corrupt pipeline state |

### Retry Strategy

```python
# app/core/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True
)
async def call_with_retry(func, *args, **kwargs):
    return await func(*args, **kwargs)
```

### Error Logging

```python
# app/core/logging.py
from loguru import logger
import json

# Structured JSON logging
logger.add(
    sys.stdout,
    format="{message}",
    level="INFO",
    serialize=True
)

def log_error(component: str, operation: str, error: Exception, context: dict = None):
    logger.error(json.dumps({
        "component": component,
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context or {},
        "timestamp": datetime.utcnow().isoformat()
    }))
```

### Graceful Degradation Matrix

| Failure | Degradation |
|---------|-------------|
| Google Drive unreachable | Use /tmp/ fallback (L2-09) |
| Gemini grade model limit | Fall back to bulk model (L2-08) |
| Model deprecated | Alert + bulk fallback (L2-17) |
| Single feed failure | Skip feed, continue others |
| Summarization fails | Use RSS description |
| Budget 90% | Disable faithfulness checks |
| Budget 95% | Disable all AI, serve cached |

---

## Write Safety Protocol (L2-04)

### ETag-Based Optimistic Locking

```python
# app/clients/drive_client.py
import asyncio
from google.oauth2.credentials import Credentials

class DriveClient:
    def __init__(self):
        self._file_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, filename: str) -> asyncio.Lock:
        if filename not in self._file_locks:
            self._file_locks[filename] = asyncio.Lock()
        return self._file_locks[filename]

    async def write_with_etag(
        self,
        filename: str,
        data: dict,
        max_retries: int = 3
    ) -> bool:
        lock = self._get_lock(filename)

        async with lock:
            for attempt in range(max_retries):
                try:
                    # 1. Read current file + capture ETag
                    current, etag = await self._read_with_etag(filename)

                    # 2. Validate current is valid JSON
                    if current is None:
                        current = await self._restore_from_backup(filename)

                    # 3. Apply modifications
                    # (data already contains modifications)

                    # 4. Backup current
                    await self._write_backup(filename, current)

                    # 5. Write with If-Match header
                    success = await self._write_with_condition(
                        filename, data, etag
                    )

                    if success:
                        # 6. Verify write
                        verified = await self._verify_write(filename, data)
                        if verified:
                            return True
                        else:
                            await self._restore_from_backup(filename)

                except PreconditionFailed:
                    # ETag mismatch - re-read and retry
                    logger.warning(f"ETag conflict on {filename}, retry {attempt+1}")
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue

            raise WriteFailedError(f"Failed to write {filename} after {max_retries} attempts")
```

---

## Loophole Fix Implementation Summary

| Fix | Module | Implementation |
|-----|--------|----------------|
| L2-01 Per-slot tracking | `pipeline_state.json`, `triggers.py` | Slots object with independent status |
| L2-02 4 cron jobs | `triggers.py` | Morning trigger runs cleanup/backup/quarterly |
| L2-03 Display-only cache | `grading.py` | Cache hit returns with `cached: true`, no state change |
| L2-04 ETag locking | `drive_client.py` | `If-Match` header, retry on 412 |
| L2-05 Zero-grading days | `adaptive_mode.py` | Neutral days don't affect counters |
| L2-06 Evening carry-over | `topic_selector.py` | `next_day_priority_queue` processed first |
| L2-07 Unified mode machine | `adaptive_mode.py` | Single `MODE_CONFIG` source of truth |
| L2-08 RPD tracking | `gemini_client.py` | Track RPD, fallback at 90 |
| L2-09 /tmp/ fallback | `drive_client.py` | Short-term fallback, sync on reconnect |
| L2-10 Streak definition | `email_service.py` | Consecutive `email_sent == true` days |
| L2-11 Two-phase dedup | `dedup.py` | 85% definite, 60-85% Gemini confirm |
| L2-12 Combined scoring | `scoring.py` | Single Gemini call for relevance + credibility |
| L2-13 Dual-auth grade | `auth.py`, `api.py` | API key OR Basic Auth + CSRF |
| L2-14 Reteaching timeout | `cleanup.py` | 14-day auto-revert to active |
| L2-15 Mastery semantics | `grading.py` | Latest score; daily avg includes all |
| L2-17 Model env vars | `config.py`, `gemini_client.py` | Env vars + deprecation fallback |
| L2-18 Split blocklists | `extractors.py` | BLOCKED_DOMAINS + BLOCKED_URL_PATTERNS |
| L2-19 Dual-auth dashboard | `auth.py`, `api.py` | API key OR Basic Auth for data endpoint |
| L2-20 Summary cache key | `summarizer.py` | SHA256(url + extraction_method) |

---

## Open Questions

| # | Question | Impact | Current Decision |
|---|----------|--------|------------------|
| 1 | Will 42 feeds + cleanup + backup fit in Render timeout? | Medium | Use BackgroundTasks after 200 OK |
| 2 | How to handle Gemini rate limits during peak? | Medium | RPD tracking + automatic fallback |
| 3 | Should we implement dead letter queue retry? | Low | Manual retry via errors.json for v2.0 |
| 4 | How to monitor cron-job.org reliability? | Medium | Alert email on 3+ consecutive failures |
| 5 | Schema migration strategy for future versions? | Medium | Version check on read, migrate in-place |

---

## Dependencies

### Python Packages (requirements.txt)

```
# Core Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0

# Authentication & Security
fastapi-csrf-protect==0.3.2
slowapi==0.1.9

# Google APIs
google-generativeai==0.3.2
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.116.0

# Content Extraction
feedparser==6.0.10
trafilatura==1.6.3
readability-lxml==0.8.1
newspaper3k==0.2.8
chardet==5.2.0

# Text Processing
fuzzywuzzy==0.18.0
python-Levenshtein==0.23.0

# HTTP Clients
httpx==0.26.0
tenacity==8.2.3

# Templates & Charts
jinja2==3.1.3
matplotlib==3.8.2

# Logging
loguru==0.7.2

# Utilities
python-dateutil==2.8.2

# Testing (dev)
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-mock==3.12.0
responses==0.24.1
httpx==0.26.0
```

---

*Generated via @tdd brainstorm agent — TDD v2.0*
