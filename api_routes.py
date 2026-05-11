"""
api_routes.py — FastAPI backend for React UI
All fixes applied:
  - Real company->domain via DuckDuckGo HTML search (no API key needed)
  - Purpose-aware contact ranking (job_seeker gets engineers, investor gets CEO)
  - Real activity feed from DB (zero static data)
  - /api/enhance endpoint for email rewrite
  - verify_grade + email alias in every contact response
  - Hunter credits only spent when domain is confirmed
  - /api/contacts/manual for when search finds nothing
"""

import csv, io, json, os, re, time, urllib.parse, urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import config
from db import (get_conn, get_dashboard_stats, create_lead,
                update_lead_status, save_sequence, log_api_call)
from email_lookup.lookup_service import lookup_contacts
from email_lookup.api_clients.gemini_email_generator import (
    generate_email_sequence, generate_subject_variants
)
from model_router import generate as model_generate
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter()

# ── Purpose → target roles ─────────────────────────────────────────────────

PURPOSE_ROLE_PRIORITY = {
    'job_seeker':      ['engineering manager','head of engineering','vp engineering',
                        'cto','co-founder','founder','recruiter','talent','hiring manager',
                        'tech lead','director of engineering'],
    'investor_pitch':  ['ceo','co-founder','founder','managing partner',
                        'general partner','partner','managing director'],
    'b2b_sales':       ['vp sales','head of sales','chief revenue officer','cro',
                        'vp revenue','head of revenue','sales director',
                        'head of growth','vp growth'],
    'referral_request':['ceo','co-founder','founder','vp engineering','cto'],
    'startup_founder': ['ceo','co-founder','founder','cto','chief of staff'],
    'cold_outreach':   ['ceo','co-founder','founder'],
    'partnership':     ['vp partnerships','head of partnerships','business development',
                        'ceo','co-founder','founder'],
    'interview_prep':  ['ceo','co-founder','founder','cto','engineering manager'],
}

SKIP_DOMAINS = {
    'linkedin','twitter','x','facebook','crunchbase','wikipedia','bloomberg',
    'techcrunch','duckduckgo','google','youtube','github','glassdoor',
    'pitchbook','forbes','wsj','producthunt','ycombinator','venturebeat',
    'medium','substack','notion','reddit','quora',
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def _ok(data: dict) -> dict:
    return {"success": True, "error": None, **data}

def _err(msg: str, code: int = 400):
    raise HTTPException(status_code=code, detail={"success": False, "error": msg})

def _sid(request: Request) -> str:
    """Extract session ID from request header. Empty string = no session."""
    return request.headers.get('X-Session-ID', '')


def _normalize_contact(c: dict) -> dict:
    """Add verify_grade, email alias, hunter_score — all required by React frontend."""
    confidence = int(c.get("confidence", c.get("hunter_score", 0)))
    return {
        **c,
        "email":        c.get("value", c.get("email", "")),
        "value":        c.get("value", c.get("email", "")),
        "verify_grade": c.get("verify_grade",
            "HIGH"   if confidence >= 80 else
            "MEDIUM" if confidence >= 50 else "LOW"),
        "hunter_score": confidence,
    }


def _rank_contacts_by_purpose(contacts: list, purpose: str) -> list:
    """
    Sort contacts so the most relevant role for this purpose appears first.
    job_seeker -> engineers first; investor_pitch -> CEO/founder first; etc.
    """
    priority_roles = PURPOSE_ROLE_PRIORITY.get(purpose, ['ceo', 'founder'])

    def score(c):
        role = (c.get("position") or "").lower()
        for i, target in enumerate(priority_roles):
            if target in role:
                return (len(priority_roles) - i) * 100 + int(c.get("confidence", 0))
        return int(c.get("confidence", 0))

    return sorted(contacts, key=score, reverse=True)


def _find_domain_via_search(company: str, category_hint: str = "") -> tuple:
    """
    Resolve a company name to its real domain using DuckDuckGo HTML search.
    No API key needed. Falls back to heuristic if network is unavailable.
    Returns (domain, confidence_float).
    """
    query = f"{company} {category_hint} official website".strip()
    params = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })

    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8", errors="ignore")

        encoded_urls = re.findall(r"uddg=(https?%3A%2F%2F[^&\"]+)", html)
        for encoded in encoded_urls[:10]:
            decoded = urllib.parse.unquote(encoded)
            m = re.match(r"https?://(?:www\.)?([a-z0-9\-\.]+\.[a-z]{2,})", decoded, re.I)
            if not m:
                continue
            domain = m.group(1).lower()
            # Skip known noise domains
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue
            # Must look like a real company domain (not an article page)
            if "/" in domain:
                continue
            log.info("DuckDuckGo resolved %r -> %r", company, domain)
            return domain, 0.80

    except Exception as e:
        log.debug("DuckDuckGo search failed for %r: %s", company, e)

    # Heuristic fallback — low confidence
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    domain = f"{slug}.com"
    log.debug("Heuristic domain for %r: %s", company, domain)
    return domain, 0.35


def _build_real_activity(conn, limit: int = 8, session_id: str = '') -> list:
    """Build activity feed from DB — scoped to session_id so users see only their own."""
    ICONS = {
        "Hunter": "🎯", "Gemini": "✉️", "Groq": "⚡",
        "Scraper": "🕷️", "Lookup": "🔍",
    }
    STATUS_ICONS = {
        "sent": "📤", "drafted": "📝", "replied": "💬",
        "opened": "👁", "discovered": "🔍", "booked": "📅", "verified": "✅",
    }

    items = []

    # API usage — session scoped
    if session_id:
        api_rows = conn.execute(
            "SELECT api_name, domain, endpoint, success, error_msg, ts "
            "FROM api_usage WHERE session_id=? ORDER BY ts DESC LIMIT 20",
            (session_id,)
        ).fetchall()
        lead_rows = conn.execute(
            "SELECT email, domain, status, updated_at FROM leads WHERE session_id=? ORDER BY updated_at DESC LIMIT 10",
            (session_id,)
        ).fetchall()
    else:
        api_rows = []
        lead_rows = []

    for r in api_rows:
        age = int(time.time() - r["ts"])
        t = f"{age}s ago" if age < 60 else f"{age//60}m ago" if age < 3600 else f"{age//3600}h ago"
        icon = ICONS.get(r["api_name"], "📊")
        msg = f"{r['domain'] or 'system'} → {r['endpoint'] or r['api_name']} {'✓' if r['success'] else '✗'}"
        items.append({"icon": icon, "message": msg, "time_ago": t,
                      "success": bool(r["success"]), "ts": r["ts"]})

    for lead in lead_rows:
        age = int(time.time() - lead["updated_at"])
        t = f"{age}s ago" if age < 60 else f"{age//60}m ago" if age < 3600 else f"{age//3600}h ago"
        icon = STATUS_ICONS.get(lead["status"], "📋")
        items.append({"icon": icon, "message": f"{lead['email']} → {lead['status']}",
                      "time_ago": t, "success": True, "ts": lead["updated_at"]})

    items.sort(key=lambda x: x["ts"], reverse=True)
    for item in items:
        item.pop("ts", None)
    return items[:limit]


# ── Request models ───────────────────────────────────────────────────────────

class FindDomainRequest(BaseModel):
    company_name: str
    category_hint: str = ""

class LookupRequest(BaseModel):
    company_name: str
    domain: Optional[str] = None
    purpose: str = "job_seeker"

class ManualContactRequest(BaseModel):
    domain: str
    first_name: str
    last_name: str
    position: str = ""
    purpose: str = "job_seeker"

class GenerateRequest(BaseModel):
    email: str
    domain: str
    purpose: str = "job_seeker"
    sender: dict = {}
    preferred_model: str = "auto"
    is_followup: bool = False
    previous_email: str = ""
    first_name: str = ""
    last_name: str = ""
    position: str = ""
    rough_draft: str = ""       # optional user rough draft to enhance

class EnhanceRequest(BaseModel):
    rough_draft: str
    purpose: str = "job_seeker"
    contact_name: str = ""
    company: str = ""
    sender_name: str = ""
    sender_title: str = ""
    preferred_model: str = "auto"

class StatusUpdate(BaseModel):
    status: str

class SettingsUpdate(BaseModel):
    hunter_daily_limit: Optional[int] = None
    gemini_daily_limit: Optional[int] = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    """
    Returns configuration status for all API keys.
    Frontend uses this to show which services are active.
    If groq/gemini show false despite key in .env, restart the backend process.
    """
    # Re-read from environment in case .env was updated after startup
    import os
    groq_key      = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key    = os.environ.get("GEMINI_API_KEY", "").strip()
    hunter_key    = os.environ.get("HUNTER_API_KEY", "").strip()
    sg_key        = os.environ.get("SCRAPEGRAPH_API_KEY", "").strip()

    return {
        "status":       "ok",
        "dry_run":      config.DRY_RUN,
        "hunter":       bool(hunter_key),
        "gemini":       bool(gemini_key),
        "groq":         bool(groq_key),
        "scrapegraph":  bool(sg_key),
        "note": "If keys show false despite being in .env, restart: python api_routes.py",
    }


@router.get("/stats")
def get_stats(request: Request):
    session_id = _sid(request)
    try:
        with get_conn() as conn:
            stats = get_dashboard_stats(conn, session_id=session_id)
        from email_lookup.api_clients.hunter_client import get_budget_status
        budget = get_budget_status()
        import os
        groq_live   = bool(os.environ.get("GROQ_API_KEY","").strip())
        gemini_live = bool(os.environ.get("GEMINI_API_KEY","").strip())
        return _ok({**stats,
                    "hunter_daily_limit": config.HUNTER_DAILY_LIMIT,
                    "gemini_daily_limit": config.GEMINI_DAILY_LIMIT,
                    "hunter_budget": budget,
                    "dry_run": config.DRY_RUN,
                    "gemini_configured": gemini_live,
                    "groq_configured":   groq_live})
    except Exception as e:
        log.error("/stats error: %s", e)
        return _ok({"domains_cached": 0, "contacts_found": 0, "leads_total": 0,
                    "emails_sent": 0, "emails_replied": 0, "reply_rate": "—",
                    "hunter_credits_today": 0, "gemini_calls_today": 0,
                    "hunter_daily_limit": config.HUNTER_DAILY_LIMIT,
                    "gemini_daily_limit": config.GEMINI_DAILY_LIMIT,
                    "dry_run": config.DRY_RUN})


@router.get("/activity")
def get_activity(request: Request):
    session_id = _sid(request)
    try:
        with get_conn() as conn:
            feed = _build_real_activity(conn, limit=8, session_id=session_id)
        return _ok({"activity": feed})
    except Exception as e:
        log.warning("/activity error: %s", e)
        return _ok({"activity": []})


@router.post("/find-domain")
def find_domain(req: FindDomainRequest):
    """
    Resolve company name to real domain.
    Uses DuckDuckGo HTML search — no API key needed.
    """
    if not req.company_name.strip():
        _err("Company name is required")

    if config.DRY_RUN:
        slug = re.sub(r"[^a-z0-9]", "", req.company_name.lower())
        return _ok({"domain": f"{slug}.com", "confidence": 0.4,
                    "company_name": req.company_name, "source": "heuristic"})

    domain, confidence = _find_domain_via_search(req.company_name, req.category_hint)
    return _ok({"domain": domain, "confidence": confidence,
                "company_name": req.company_name,
                "source": "search" if confidence > 0.5 else "heuristic"})


@router.post("/lookup")
def lookup(req: LookupRequest, request: Request):
    session_id = _sid(request)
    """
    Find contacts for a company. If no domain provided, resolves it first.
    Returns contacts ranked by relevance to purpose.
    When zero contacts found, returns instructions for manual entry.
    """
    domain = req.domain
    domain_source = "provided"

    if not domain:
        if config.DRY_RUN:
            slug = re.sub(r"[^a-z0-9]", "", req.company_name.lower())
            domain = f"{slug}.com"
            domain_source = "heuristic"
        else:
            domain, _ = _find_domain_via_search(req.company_name)
            domain_source = "search"

    result = lookup_contacts(domain, req.purpose)
    contacts = result.get("contacts", [])

    # Normalize + rank by purpose
    contacts = [_normalize_contact(c) for c in contacts]
    contacts = _rank_contacts_by_purpose(contacts, req.purpose)

    # Log
    try:
        with get_conn() as conn:
            log_api_call(conn, "Lookup", success=not bool(result.get("error")),
                         domain=domain, endpoint="domain_search",
                         error=result.get("error", ""), session_id=session_id)
    except Exception:
        pass

    return _ok({
        "domain":         result.get("domain", domain),
        "company_name":   req.company_name,
        "contacts":       contacts,
        "total_found":    len(contacts),
        "source":         result.get("source", "unknown"),
        "domain_source":  domain_source,
        "pattern":        result.get("pattern"),
        "organization":   result.get("organization"),
        "error":          result.get("error"),
        "budget":         result.get("budget", {}),
        "needs_manual":   len(contacts) == 0,   # frontend shows manual entry form when True
        "purpose_target": PURPOSE_ROLE_PRIORITY.get(req.purpose, ["ceo"])[:3],
    })


@router.post("/contacts/manual")
def add_manual_contact(req: ManualContactRequest):
    """
    When search finds no contacts, user can enter name manually.
    Backend generates email variants via pattern inference.
    """
    from email_lookup.pattern_engine import infer_variants

    variants = infer_variants(req.first_name, req.last_name, req.domain)
    top_variants = variants[:3]

    contacts = []
    for v in top_variants:
        contacts.append(_normalize_contact({
            "value":      v["email"],
            "email":      v["email"],
            "first_name": req.first_name,
            "last_name":  req.last_name,
            "position":   req.position or "Unknown",
            "confidence": int(v["confidence"] * 100),
            "source":     "pattern_inferred",
            "type":       "personal",
            "pattern":    v["pattern"],
        }))

    return _ok({
        "domain":     req.domain,
        "contacts":   contacts,
        "total_found": len(contacts),
        "source":     "pattern_inferred",
        "note":       f"Generated {len(contacts)} email variants for {req.first_name} {req.last_name}",
    })


@router.post("/generate")
def generate(req: GenerateRequest, request: Request):
    session_id = _sid(request)
    """
    Generate full 4-day email campaign.
    If rough_draft provided, enhances it instead of writing from scratch.
    """
    if not req.email:
        _err("Email address is required")

    contact = {
        "value":      req.email,
        "email":      req.email,
        "first_name": req.first_name,
        "last_name":  req.last_name,
        "position":   req.position,
        "domain":     req.domain,
    }

    # Override model router if user selected a specific model
    import model_router as _mrouter
    original_classify = None
    if req.preferred_model in ("gemini_flash", "groq"):
        original_classify = _mrouter.classify_task
        def forced_classify(task, count=1, vip=False):
            r = original_classify(task, count, vip)
            r["model"] = req.preferred_model
            r["fallback_chain"] = [req.preferred_model] + [
                m for m in ["gemini_flash", "groq", "gemini_pro"] if m != req.preferred_model
            ]
            return r
        _mrouter.classify_task = forced_classify

    try:
        # Fetch domain intel
        company_intel = {"title": req.domain, "description": "", "tech_hints": [], "headlines": [], "social": {}}
        if not config.DRY_RUN:
            try:
                from email_lookup.fallback_scraper import scrape_domain_intel
                intel = scrape_domain_intel(req.domain)
                if intel:
                    company_intel.update(intel)
            except Exception:
                pass

        # If user provided a rough draft, inject it as context
        previous = req.previous_email
        if req.rough_draft and not req.is_followup:
            previous = f"USER'S ROUGH DRAFT (improve this, do not use as-is):\n{req.rough_draft}"

        seq = generate_email_sequence(
            contact=contact,
            company_intel=company_intel,
            sender=req.sender,
            purpose=req.purpose,
            is_vip=False,
            is_followup=req.is_followup,
            previous_email=previous,
        )
    finally:
        if original_classify:
            _mrouter.classify_task = original_classify

    if not seq.get("success"):
        _err(seq.get("error", "Email generation failed — check API keys and rate limits"), 500)

    # Save to DB
    lead_id = None
    try:
        with get_conn() as conn:
            lead_id = create_lead(conn, req.email, req.domain, req.purpose,
                                  session_id=session_id,
                                  first_name=req.first_name, last_name=req.last_name,
                                  position=req.position)
            update_lead_status(conn, lead_id, "drafted")
            d0 = seq.get("day_0", {})
            save_sequence(conn, lead_id, 0, d0.get("subject", ""), d0.get("body", ""),
                          subject_variants=d0.get("subject_variants", []),
                          model_used=seq.get("model_used", ""))
            for day in [3, 7, 14]:
                dd = seq.get(f"day_{day}", {})
                if dd.get("body"):
                    save_sequence(conn, lead_id, day, dd.get("subject", ""), dd["body"],
                                  model_used=seq.get("model_used", ""))
            log_api_call(conn, "Gemini", credits=1, domain=req.domain,
                         model=seq.get("model_used", ""), endpoint="generate",
                         session_id=session_id)
    except Exception as e:
        log.warning("Could not save lead to DB: %s", e)

    return _ok({
        "lead_id":    lead_id,
        "model_used": seq.get("model_used", "unknown"),
        "day_0":      seq.get("day_0", {}),
        "day_3":      seq.get("day_3", {}),
        "day_7":      seq.get("day_7", {}),
        "day_14":     seq.get("day_14", {}),
    })


@router.post("/enhance")
def enhance_email(req: EnhanceRequest):
    """
    Take user's rough draft and rewrite it professionally using AI.
    Returns improved email + 3 subject lines + list of improvements made.
    """
    if not req.rough_draft.strip():
        _err("Rough draft is required")

    PURPOSE_CONTEXT = {
        "job_seeker":       "applying for a founding/early engineer role",
        "investor_pitch":   "pitching for investment",
        "b2b_sales":        "selling a product or service",
        "cold_outreach":    "making a professional connection",
        "referral_request": "requesting a referral",
        "startup_founder":  "proposing a collaboration",
        "partnership":      "proposing a partnership",
    }
    intent = PURPOSE_CONTEXT.get(req.purpose, req.purpose)

    schema = ('{"subject_lines":["a","b","c"],'
              '"body":"full professional email",'
              '"ps_line":"optional P.S. or empty string",'
              '"improvements_made":["change 1","change 2"]}')

    system = (
        "You are an elite cold email copywriter. Rewrite rough drafts into professional, "
        "compelling emails that get replies from busy founders and executives. "
        "Rules: never use buzzwords (synergy/leverage/circle back/touch base/hop on a call), "
        "always open with something specific about the recipient or their company, "
        "one clear ask only, under 150 words for the body, sound human not robotic. "
        "RESPOND ONLY IN JSON matching this schema, no markdown, no preamble: " + schema
    )

    user = (
        f"Rewrite this rough draft professionally.\n\n"
        f"ROUGH DRAFT:\n{req.rough_draft}\n\n"
        f"CONTEXT:\n"
        f"- Recipient: {req.contact_name or 'the founder'} at {req.company or 'their company'}\n"
        f"- Sender: {req.sender_name or 'the sender'}, {req.sender_title or ''}\n"
        f"- Purpose: {intent}\n\n"
        f"REQUIREMENTS:\n"
        f"- Preserve the sender's core message and intent\n"
        f"- Add one specific, real reference about {req.company or 'their company'}\n"
        f"- Full professional email: greeting + body + sign-off with sender name\n"
        f"- Generate 3 subject line variants (curiosity / direct / question format)\n"
        f"- List what you improved in improvements_made array"
    )

    result = model_generate(
        task="email_draft",
        system_prompt=system,
        user_prompt=user,
        max_tokens=1000,
        parse_json=True,
    )

    parsed = result.get("parsed_json")
    if not parsed:
        # Fallback: return raw text as body
        parsed = {
            "subject_lines": [f"Re: {req.company}", "Quick thought", "Worth a conversation?"],
            "body": result.get("text", req.rough_draft),
            "ps_line": "",
            "improvements_made": ["AI rewrite applied"],
        }

    try:
        with get_conn() as conn:
            log_api_call(conn, "Gemini", credits=1, domain=req.company or "",
                         model=result.get("model_used", ""), endpoint="enhance")
    except Exception:
        pass

    return _ok({
        "subject_lines":    parsed.get("subject_lines", []),
        "body":             parsed.get("body", ""),
        "ps_line":          parsed.get("ps_line", ""),
        "improvements_made": parsed.get("improvements_made", []),
        "model_used":       result.get("model_used", "unknown"),
    })


@router.post("/verify")
def verify_single_email(body: dict):
    email = body.get("email", "").strip().lower()
    if not email or "@" not in email:
        _err("Valid email required")
    try:
        from email_lookup.email_verifier import verify_email
        result = verify_email(email, source="inferred", skip_smtp=False)
        return _ok(result)
    except Exception as e:
        log.warning("/verify error for %s: %s", email, e)
        return _ok({"email": email, "status": "unknown", "grade": "LOW",
                    "confidence_score": 0.0, "send_recommended": False,
                    "is_catch_all": False, "mail_provider": None, "mx_host": None,
                    "verified_at": time.time()})


@router.get("/leads")
def get_leads(request: Request, status: Optional[str] = None, search: Optional[str] = None):
    session_id = _sid(request)
    try:
        with get_conn() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE session_id=? ORDER BY updated_at DESC LIMIT 200",
                    (session_id,)
                ).fetchall()
            else:
                rows = []
        leads = [dict(r) for r in rows]
        if status and status != "all":
            leads = [l for l in leads if l.get("status") == status]
        if search:
            s = search.lower()
            leads = [l for l in leads
                     if s in l.get("email","").lower() or s in l.get("domain","").lower()]
        return _ok({"leads": leads, "total": len(leads)})
    except Exception as e:
        log.error("/leads error: %s", e)
        return _ok({"leads": [], "total": 0})


@router.get("/leads/{lead_id}/sequences")
def get_lead_sequences(lead_id: int):
    """Return all email sequences for a lead — for the pipeline email viewer."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM email_sequences WHERE lead_id=? ORDER BY sequence_day",
                (lead_id,)
            ).fetchall()
        return _ok({"sequences": [dict(r) for r in rows], "lead_id": lead_id})
    except Exception as e:
        return _ok({"sequences": [], "lead_id": lead_id})


@router.patch("/leads/{lead_id}/status")
def update_status(lead_id: int, body: StatusUpdate):
    valid = {"discovered","verified","drafted","sent","opened","replied","booked","skipped"}
    if body.status not in valid:
        _err(f"Invalid status. Must be one of: {', '.join(sorted(valid))}")
    try:
        with get_conn() as conn:
            update_lead_status(conn, lead_id, body.status)
            log_api_call(conn, "Tracker", credits=0, domain="",
                         endpoint=f"status_update:{body.status}", success=True)
        return _ok({"lead_id": lead_id, "status": body.status})
    except Exception as e:
        _err(str(e), 500)


@router.post("/settings")
def update_settings(body: SettingsUpdate):
    if body.hunter_daily_limit is not None and 1 <= body.hunter_daily_limit <= 50:
        config.HUNTER_DAILY_LIMIT = body.hunter_daily_limit
        try:
            from utils.rate_limiter import hunter_budget
            hunter_budget.daily_limit = body.hunter_daily_limit
        except Exception:
            pass
    if body.gemini_daily_limit is not None and 1 <= body.gemini_daily_limit <= 1500:
        config.GEMINI_DAILY_LIMIT = body.gemini_daily_limit
        try:
            from utils.rate_limiter import gemini_budget
            gemini_budget.daily_limit = body.gemini_daily_limit
        except Exception:
            pass
    return _ok({"hunter_daily_limit": config.HUNTER_DAILY_LIMIT,
                "gemini_daily_limit": config.GEMINI_DAILY_LIMIT})


@router.post("/suggest")
def suggest(req: dict):
    """
    Generate 3 concrete, actionable suggestions to increase reply rate.
    Called after campaign generation — runs via Groq (fast, free).
    Body: { purpose, company, sequence_preview }
    """
    purpose  = req.get("purpose", "cold_outreach")
    company  = req.get("company", "")
    preview  = req.get("sequence_preview", "")[:150]

    PURPOSE_HINTS = {
        "job_seeker":      "build a working code demo or prototype related to their tech stack",
        "investor_pitch":  "create a 90-day traction chart showing key growth metrics",
        "b2b_sales":       "prepare a personalized ROI calculation or 1-page case study",
        "partnership":     "draft a one-page brief showing clear mutual value proposition",
        "cold_outreach":   "research a specific recent launch, post, or milestone from the team",
        "referral_request":"find a mutual connection or shared experience to open with",
        "startup_founder": "share a related technical insight or small proof-of-concept",
    }
    hint = PURPOSE_HINTS.get(purpose, "create a specific, relevant proof point")

    schema = '{"suggestions":[{"icon":"emoji","title":"short title","detail":"1-sentence specific action"}]}'
    system = (
        "You are a strategic outreach advisor. Give exactly 3 concrete, specific, actionable suggestions "
        "to increase the reply rate for this exact outreach. Each suggestion must be something the sender "
        "can actually DO before sending the email — not generic advice. "
        "RESPOND ONLY IN JSON matching this schema, no markdown, no preamble: " + schema
    )
    user = (
        f"Purpose: {purpose}\n"
        f"Target company: {company or 'the company'}\n"
        f"Email preview: {preview}\n"
        f"Strategic hint: {hint}\n\n"
        f"Give 3 specific, actionable suggestions tailored to this exact outreach."
    )

    result = model_generate(
        task="subject lines",   # routes to Groq — fast, free
        system_prompt=system,
        user_prompt=user,
        max_tokens=400,
        parse_json=True,
    )

    parsed = result.get("parsed_json") or {}
    suggestions = parsed.get("suggestions")

    # Robust fallback if model doesn't return proper JSON
    if not isinstance(suggestions, list) or not suggestions:
        suggestions = [
            {"icon": "🔨", "title": "Build a demo",
             "detail": f"Create a quick working prototype relevant to {company or 'their product'} to attach to Day 3 follow-up."},
            {"icon": "📊", "title": "Add a proof point",
             "detail": "Include one specific metric or result from your past work — numbers get replies."},
            {"icon": "🎯", "title": "Reference something real",
             "detail": f"Find a specific recent post, launch, or feature from {company or 'their team'} and mention it by name."},
        ]

    try:
        with get_conn() as conn:
            log_api_call(conn, "Groq", credits=1, domain=company,
                         model=result.get("model_used", ""), endpoint="suggest")
    except Exception:
        pass

    return _ok({"suggestions": suggestions, "model_used": result.get("model_used", "unknown")})


@router.get("/export/csv")
def export_csv():
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT email, domain, first_name, last_name, position, "
                "status, purpose, created_at FROM leads ORDER BY created_at DESC"
            ).fetchall()
    except Exception as e:
        _err(str(e), 500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email","Domain","First Name","Last Name","Position",
                     "Status","Purpose","Created"])
    for r in rows:
        writer.writerow([r["email"], r["domain"], r["first_name"], r["last_name"],
                         r["position"], r["status"], r["purpose"],
                         time.strftime("%Y-%m-%d", time.localtime(r["created_at"]))])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.read().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=outreach_leads.csv"},
    )


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pathlib import Path
    from db import init_db

    init_db()

    app = FastAPI(title="AI Outreach Platform API", version="3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All /api/* routes — registered BEFORE static files
    app.include_router(router, prefix="/api")

    # Serve React build if it exists (produced by `pnpm build` or Docker stage 1)
    # Falls back to API-only mode during local development
    dist_path = Path(__file__).parent / "frontend" / "dist"
    if dist_path.exists():
        app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")
        log.info("Serving frontend from %s", dist_path)
    else:
        log.info("No frontend/dist found — running in API-only mode (run pnpm build to add frontend)")

    port = int(os.environ.get("PORT", 7860))
    log.info("Starting server on 0.0.0.0:%d — dry_run=%s", port, config.DRY_RUN)
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)