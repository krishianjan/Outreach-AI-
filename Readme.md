---
title: AI Outreach Platform
emoji: 🚀
colorFrom: violet
colorTo: emerald
sdk: gradio
sdk_version: 5.40.0
app_file: app.py
pinned: false
license: mit
short_description: Find contacts, verify emails, generate AI-powered outreach sequences
---

# 🚀 AI Outreach Platform

An AI-powered professional outreach tool that finds email contacts, verifies them, and generates personalised multi-day email campaigns — all from a single domain input.

## Features

- **Contact Discovery** — Hunter.io API + 3-tier web scraping fallback
- **Email Verification** — MX record + SMTP probe + composite confidence scoring
- **Pattern Inference** — Guess any team member's email from one known sample (zero extra API credits)
- **Multi-Model Email Generation** — Gemini Flash (bulk) + Groq (real-time) + Gemini Pro (VIP targets)
- **Full Campaign Sequences** — Day 0, 3, 7, 14 follow-ups generated in one API call
- **Pipeline Tracker** — Kanban-style lead status tracking (discovered → replied → booked)
- **API Budget Guard** — Daily credit caps, key rotation, rate limiting — never accidentally burns credits

## Setup

### Local

```bash
git clone <your-repo>
cd <project>
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
python app.py
```

### Hugging Face Spaces

1. Create a new Space (Gradio SDK)
2. Push this repo: `git push hf main`
3. Set secrets in Space Settings:
   - `HUNTER_API_KEY`
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `SCRAPEGRAPH_API_KEY` (optional)
   - `DRY_RUN=false`

## API Keys (all free tiers available)

| Service | Free Tier | Get Key |
|---------|-----------|---------|
| Hunter.io | 50 req/month | [hunter.io](https://hunter.io) |
| Google Gemini | 1500 req/day | [aistudio.google.com](https://aistudio.google.com) |
| Groq | ~14k req/day | [console.groq.com](https://console.groq.com) |
| ScrapingGraph | 100 pages/day | [scrapegraphai.com](https://scrapegraphai.com) |

## Architecture

```
Domain input
  → Cache check (SQLite)
  → Hunter.io API (with key rotation + budget guard)
  → 3-tier scraper (ScrapingGraph → httpx+BS4 → Google Cache)
  → Pattern inference (pure Python)
  → Email verification (MX + SMTP + composite score)
  → Multi-model generation (Gemini Flash / Groq / Gemini Pro)
  → 4-day campaign sequence stored to SQLite
  → Pipeline kanban display
```

## Built with

- [Gradio](https://gradio.app) — UI
- [Google Gemini](https://aistudio.google.com) — email generation
- [Groq](https://groq.com) — fast inference
- [Hunter.io](https://hunter.io) — contact discovery
- [SQLite WAL](https://sqlite.org) — local persistence