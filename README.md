# ⚡ AI Outreach Platform

> **End-to-end AI-powered professional outreach**  finds real contacts, verifies emails, generates personalised multi-day campaigns using LLMs, and tracks replies in a live pipeline.

**[🚀 Live Demo](https://huggingface.co/spaces/krishianjan/Outreach-AI)** · Built by [Krishi Anjan](https://linkedin.com/in/krishianjan)

---

## Objective /Goal

An autonomous outreach engine that takes a company name → finds decision-maker emails via Hunter.io + multi-tier web scraping → verifies them via SMTP probing → routes to the optimal LLM (Gemini Flash or Groq) to generate a complete 4-email campaign grounded in the user's draft — all with per-session data isolation so multiple users can run it simultaneously from a single deployment.

---



## Feature Breakdown

### 🔍 Contact Discovery Engine
| What | How | Impact |
|------|-----|--------|
| Company name → domain resolution | DuckDuckGo HTML search, no API key needed | Works for any company, not just well-known ones |
| Contact lookup | Hunter.io API with key rotation pool | Finds name, role, email in one call |
| Fallback tier 1 | ScrapingGraph AI — NL query → structured JSON | Handles JS-rendered pages, beats CSS selector scrapers |
| Fallback tier 2 | httpx + BeautifulSoup, Gaussian delay (1.5–4.5s), 20 real UA rotation | Avoids bot detection on contact/team pages |
| Fallback tier 3 | Google Cache URL | Last resort for blocked sites |
| Pattern inference | Detect `{first}.{last}` format from 1 known email, generate 8 variants | Zero extra Hunter credits for new targets |
| Email verification | DNS MX check → SMTP RCPT TO probe → catch-all detection | Eliminates dead domains before any send |

### 🤖 Multi-Model LLM Router
| Task | Model | Why |
|------|-------|-----|
| Email draft (Day 0) | Gemini 1.5 Flash | 128k context, JSON mode enforced at API level |
| Subject line variants | Groq Llama 3.3 70B | Sub-500ms, generous free tier |
| Follow-up bumps | Groq Llama 3.3 70B | Short output, speed matters |
| Smart suggestions | Groq Llama 3.3 70B | Fast 3-tip generation after campaign |
| VIP single target | Gemini 1.5 Pro | Best quality for high-stakes outreach |
| Fallback chain | Gemini Flash → Gemini Pro → Groq | Never fails silently |

**Email quality enforcements in system prompt:**
- Mandatory structure: `Hi [FirstName],` → 3 paragraphs → full sign-off
- 150–200 word minimum — not a summary, a complete professional email
- Forbidden phrases listed by name: "Revolutionizing", "Synergy", "Circle back", etc.
- Anti-hallucination: model told never to invent metrics not provided by sender
- P.S. line only if real GitHub/portfolio URL exists

### 📊 Live Pipeline & Dashboard
- **Session-scoped data** — each browser tab generates a UUID; all DB queries filter by `session_id`, so multiple users share one deployment without seeing each other's data
- **Real-time stats** — emails sent, reply rate, Hunter credits used today update on Mark as Sent
- **Status progression** — `discovered → verified → drafted → sent → opened → replied → booked`
- **Export** — one-click CSV of all leads

### 🛡️ Production Engineering
| Concern | Solution |
|---------|----------|
| API credit burn | `TokenBucket` + `APIBudget` per API, configurable daily limits |
| Key exhaustion | `KeyPool` round-robin rotation, bans keys on 429, restores on reset |
| Concurrent writes | SQLite WAL mode, connection-per-request pattern |
| Cache corruption | Atomic write-then-rename, corrupt JSON recovery |
| Bot detection | Gaussian delay distribution, real browser UA pool, session reuse |
| Secret management | HF Spaces repository secrets, `.env` excluded from git + Docker image |

---

## Architecture

```
Browser (React + Vite)
  │  X-Session-ID header (UUID per tab — scopes all data)
  ▼
FastAPI (api_routes.py)
  ├── /api/find-domain   → DuckDuckGo search → domain
  ├── /api/lookup        → Hunter.io + 3-tier scraper → contacts[]
  ├── /api/generate      → model_router → Gemini/Groq → 4-email sequence
  ├── /api/enhance       → model_router → rewrite any email
  ├── /api/suggest       → Groq → 3 reply-rate tips
  ├── /api/leads         → SQLite (session-scoped)
  └── /api/stats         → SQLite (session-scoped)
  ▼
SQLite (WAL mode)
  ├── domains     — cached company intel (global)
  ├── contacts    — discovered contacts (global)
  ├── leads       — outreach pipeline (session-scoped)
  ├── email_sequences — campaign content (per lead)
  └── api_usage   — credit tracking (session-scoped)
```

---

### 🛠️ Tech Stack

⚡ FastAPI (api_routes.py)
├── 🔍 /api/find-domain → DuckDuckGo search → domain
├── 📧 /api/lookup → Hunter.io + 3-tier scraper → contacts[]
├── 🤖 /api/generate → model_router → Gemini/Groq → 4-email sequence
├── ✏️ /api/enhance → model_router → rewrite any email
├── 💡 /api/suggest → Groq → 3 reply-rate tips
├── 📋 /api/leads → SQLite (session-scoped)
└── 📊 /api/stats → SQLite (session-scoped)
▼



---

## Local Setup

```bash
git clone https://github.com/YOUR_USERNAME/outreach-ai
cd outreach-ai

# Backend
cp .env.example .env          # add your API keys
pip install -r requirements.txt
python api_routes.py           # runs on :7860

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev                       # runs on :5173
```

### Required API Keys (all free tiers)

| Key | Free Tier | Get it |
|-----|-----------|--------|
| `HUNTER_API_KEY` | 50 req/month | [hunter.io](https://hunter.io) |
| `GEMINI_API_KEY` | 1,500 req/day | [aistudio.google.com](https://aistudio.google.com) |
| `GROQ_API_KEY` | ~14,000 req/day | [console.groq.com](https://console.groq.com) |
| `SCRAPEGRAPH_API_KEY` | 100 pages/day | [scrapegraphai.com](https://scrapegraphai.com) *(optional)* |

---

## Deploy to HF Spaces (15 min)

```bash
# 1. Create a Docker Space at huggingface.co/new-space
# 2. Push
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/outreach-ai
git push hf main

# 3. Set secrets in Space Settings → Repository secrets:
#    HUNTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, DRY_RUN=false
```

The multi-stage Dockerfile builds React (Node 20) then runs FastAPI (Python 3.11). Frontend is served as static files from the same FastAPI process — single URL, zero CORS config needed in production.

---

## Project Structure

```
├── api_routes.py              # FastAPI — all 11 REST endpoints
├── model_router.py            # LLM task classifier + fallback chain
├── db.py                      # SQLite schema, WAL setup, session-scoped queries
├── config.py                  # API keys, rate limit config
├── migrate_cache.py           # JSON cache → SQLite migration
├── Dockerfile                 # Multi-stage: Node build → Python runtime
├── requirements.txt
├── .env.example
│
├── email_lookup/
│   ├── lookup_service.py      # Orchestrator: cache → Hunter → scraper
│   ├── fallback_scraper.py    # 3-tier scraping stack
│   ├── pattern_engine.py      # Email format inference from known samples
│   ├── email_verifier.py      # MX + SMTP + confidence scoring
│   └── api_clients/
│       ├── hunter_client.py   # Hunter.io with token bucket + key rotation
│       └── gemini_email_generator.py  # Prompt engineering, JSON parse guard
│
├── utils/
│   ├── rate_limiter.py        # TokenBucket, APIBudget, KeyPool
│   ├── retry.py               # Exponential backoff decorator
│   └── logger.py              # Structured rotating file logger
│
└── frontend/                  # React + TypeScript + Vite
    └── src/
        ├── app/components/    # Dashboard, Outreach, Pipeline, Settings
        ├── hooks/             # useOutreach.ts — all API calls
        └── utils/             # api.ts (session header), session.ts (UUID)
```

---

## What Makes This Different from a Tutorial Project

1. **Real production failure handling** — Every API call has retry with exponential backoff, key rotation on 429, atomic cache writes, corrupt JSON recovery, and budget guards that prevent silent credit burn.

2. **Multi-user ready from day one** — Session UUID scoping means 10 people can use the same HF Spaces link simultaneously with zero data mixing — no auth required.

3. **Model routing isn't vibes** — The router has a specific reason for every assignment: Gemini for email drafts because it enforces JSON mode at the API level (eliminating a class of parse failures), Groq for subject lines because it's 10x faster for short outputs. Previous approach of "try Groq, fallback to Gemini" caused production failures due to Groq returning empty `body` fields on complex JSON schemas.

---

*Built as a portfolio project demonstrating full-stack AI engineering: LLM prompt engineering, multi-model orchestration, production API design, and zero-infra deployment.*
