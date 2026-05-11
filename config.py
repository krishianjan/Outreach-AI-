"""
config.py
Phase 0 hardened version.

"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Runtime mode
# ---------------------------------------------------------------------------

DRY_RUN: bool = os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
# When DRY_RUN=true, all API calls return mock data. Safe for testing without burning credits.

# ---------------------------------------------------------------------------
# Hunter.io
# ---------------------------------------------------------------------------

HUNTER_API_KEY: str = os.environ.get("HUNTER_API_KEY", "")
HUNTER_API_KEY_2: str = os.environ.get("HUNTER_API_KEY_2", "")   # optional second key
HUNTER_API_KEY_3: str = os.environ.get("HUNTER_API_KEY_3", "")   # optional third key
HUNTER_DAILY_LIMIT: int = int(os.environ.get("HUNTER_DAILY_LIMIT", "8"))
# Free tier: 50 req/month. 8/day = ~240/month if used every day — adjust down if needed.

def get_hunter_keys() -> list:
    """Return all configured Hunter keys, filtering blanks."""
    return [k for k in [HUNTER_API_KEY, HUNTER_API_KEY_2, HUNTER_API_KEY_3] if k.strip()]

# ---------------------------------------------------------------------------
# Gemini (replaces Claude for email generation)
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_FLASH: str = "gemini-2.5-flash"        # bulk tasks, fast, free tier
GEMINI_MODEL_PRO: str = "gemini-1.5-pro"            # high-stakes emails only
GEMINI_DAILY_LIMIT: int = int(os.environ.get("GEMINI_DAILY_LIMIT", "200"))

# ---------------------------------------------------------------------------
# Groq (Phase 3 — real-time subject lines + follow-ups)
# ---------------------------------------------------------------------------

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Claude (kept for backward compat — router will bypass unless explicitly chosen)
# ---------------------------------------------------------------------------

CLAUDE_API_KEY: str = os.environ.get("CLAUDE_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# ---------------------------------------------------------------------------
# ScrapingGraph AI (Phase 1)
# ---------------------------------------------------------------------------

SCRAPEGRAPH_API_KEY: str = os.environ.get("SCRAPEGRAPH_API_KEY", "")

# ---------------------------------------------------------------------------
# GetProspect (existing — unchanged)
# ---------------------------------------------------------------------------

GETPROSPECT_API_KEY: str = os.environ.get("GETPROSPECT_API_KEY", "")

# ---------------------------------------------------------------------------
# Cache / Storage
# ---------------------------------------------------------------------------

CACHE_FILE: str = os.environ.get("CACHE_FILE", "email_cache.json")
CACHE_TTL_HOURS: int = int(os.environ.get("CACHE_TTL_HOURS", "48"))
# Phase 0: still using JSON cache. Phase 2 migrates to SQLite.
# CACHE_FILE kept so existing vector_storage.py continues to work.

# ---------------------------------------------------------------------------
# Rate limiting defaults (used by utils/rate_limiter.py)
# ---------------------------------------------------------------------------

HUNTER_RATE_CAPACITY: int = 3        # max burst before throttle
HUNTER_RATE_REFILL: float = 1 / 90   # tokens/sec → 1 req per 90s sustained

GEMINI_RATE_CAPACITY: int = 5
GEMINI_RATE_REFILL: float = 0.20     # ~12 req/min

GROQ_RATE_CAPACITY: int = 10
GROQ_RATE_REFILL: float = 0.5        # 30 req/min

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE: str = os.environ.get("LOG_FILE", "outreach.log")

# ---------------------------------------------------------------------------
# Validation — warns on missing keys but never crashes the app
# ---------------------------------------------------------------------------

def validate_config() -> dict:
    """
    Returns a dict of which services are configured.
    Call at startup for a clear readout.

    Example output:
        {'hunter': True, 'gemini': True, 'groq': False, 'dry_run': False}
    """
    status = {
        "dry_run": DRY_RUN,
        "hunter": bool(HUNTER_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "groq": bool(GROQ_API_KEY),
        "claude": bool(CLAUDE_API_KEY),
        "scrapegraph": bool(SCRAPEGRAPH_API_KEY),
        "getprospect": bool(GETPROSPECT_API_KEY),
    }

    # Import here to avoid circular import at module load time
    from utils.logger import get_logger
    log = get_logger("config")

    if DRY_RUN:
        log.warning("DRY_RUN=true — no real API calls will be made")

    if not status["hunter"]:
        log.warning("HUNTER_API_KEY not set — Hunter lookups disabled")
    if not status["gemini"]:
        log.warning("GEMINI_API_KEY not set — email generation disabled")
    if not status["groq"]:
        log.info("GROQ_API_KEY not set — Groq fast inference disabled (Phase 3)")

    log.info("Config loaded | hunter=%s gemini=%s groq=%s dry_run=%s",
             status["hunter"], status["gemini"], status["groq"], DRY_RUN)

    return status