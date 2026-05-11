"""
email_lookup/api_clients/hunter_client.py
Phase 0 hardened version.

WHAT CHANGED from your original:
  - Token bucket throttling (1 req/90s sustained, burst 3)
  - Daily budget guard (default 8 calls/day — set HUNTER_DAILY_LIMIT in .env)
  - Key rotation pool (add HUNTER_API_KEY_2 in .env for more capacity)
  - Exponential backoff on 429/5xx
  - Structured logging — every call logged with domain, result count, credits used
  - DRY_RUN mode — returns realistic mock data without hitting API
  - Deduplication via cache (caller's responsibility — lookup_service handles this)
  - Returns typed dict always — never raises for "no results" (only for hard errors)

WHAT IS UNCHANGED:
  - Response structure: same dict format your existing code expects
  - The two main functions: search_domain() and find_email()
"""

import time
import random
from typing import Optional

import config
from utils.logger import get_logger
from utils.rate_limiter import TokenBucket, APIBudget, KeyPool
from utils.retry import retry, is_retryable_http

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Per-client rate limiter instances
# ---------------------------------------------------------------------------

_throttle = TokenBucket(
    capacity=config.HUNTER_RATE_CAPACITY,
    refill_rate=config.HUNTER_RATE_REFILL,
)

_budget = APIBudget(
    daily_limit=config.HUNTER_DAILY_LIMIT,
    name="Hunter",
)

_key_pool: Optional[KeyPool] = None


def _get_pool() -> KeyPool:
    global _key_pool
    if _key_pool is None:
        keys = config.get_hunter_keys()
        _key_pool = KeyPool(keys)
    return _key_pool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _throttle_and_budget():
    """Enforce rate limit + budget before any Hunter API call."""
    # Budget check first — fast, no sleep
    _budget.spend(1)

    # Throttle — may sleep
    wait = _throttle.consume(1)
    if wait > 0:
        log.debug("Hunter throttle: sleeping %.2fs", wait)
        time.sleep(wait)


def _mock_domain_response(domain: str) -> dict:
    """Realistic dry-run response for domain search."""
    return {
        "domain": domain,
        "emails": [
            {
                "value": f"founder@{domain}",
                "type": "personal",
                "confidence": 92,
                "first_name": "Alex",
                "last_name": "Founder",
                "position": "Co-Founder & CEO",
                "source": "dry_run",
            },
            {
                "value": f"cto@{domain}",
                "type": "personal",
                "confidence": 87,
                "first_name": "Jordan",
                "last_name": "Tech",
                "position": "CTO",
                "source": "dry_run",
            },
        ],
        "pattern": "{first}@{domain}",
        "organization": f"{domain.split('.')[0].title()} Inc.",
        "total_results": 2,
        "source": "dry_run",
        "credits_used": 0,
    }


def _mock_find_response(domain: str, first: str, last: str) -> dict:
    """Realistic dry-run response for email finder."""
    guessed = f"{first.lower()}.{last.lower()}@{domain}"
    return {
        "email": guessed,
        "score": 85,
        "result": "webmail",
        "source": "dry_run",
        "credits_used": 0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@retry(max_attempts=4, base_delay=2.0, max_delay=60.0)
def search_domain(domain: str) -> dict:
    """
    Search Hunter.io for all emails at a domain.

    Returns:
        {
            "domain": str,
            "emails": [{"value", "type", "confidence", "first_name", "last_name", "position"}, ...],
            "pattern": str | None,           # e.g. "{first}.{last}@{domain}"
            "organization": str | None,
            "total_results": int,
            "source": "hunter" | "dry_run",
            "credits_used": int,
        }

    Never raises for "no results" — returns empty emails list.
    Raises RuntimeError only for budget exhaustion or all-keys-banned.
    """
    domain = domain.lower().strip().rstrip("/")
    log.info("Hunter.search_domain: %s | budget remaining=%d", domain, _budget.remaining)

    if config.DRY_RUN:
        log.debug("DRY_RUN: skipping real Hunter call for %s", domain)
        return _mock_domain_response(domain)

    _throttle_and_budget()

    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed. Run: pip install httpx")

    key = _get_pool().get()

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain": domain,
                    "api_key": key,
                    "limit": 10,
                    "type": "personal",
                },
                headers={"User-Agent": "OutreachPlatform/1.0"},
            )

        if resp.status_code == 429:
            _get_pool().ban(key)
            raise ConnectionError(f"Hunter 429 on key ...{key[-6:]}")

        if resp.status_code == 401:
            _get_pool().ban(key)
            raise RuntimeError(f"Hunter 401 — invalid key ...{key[-6:]}")

        if is_retryable_http(resp.status_code):
            raise ConnectionError(f"Hunter {resp.status_code} — retryable")

        resp.raise_for_status()
        data = resp.json()

    except httpx.TimeoutException:
        raise ConnectionError(f"Hunter timeout for domain: {domain}")

    emails_raw = data.get("data", {}).get("emails", [])
    pattern = data.get("data", {}).get("pattern")
    org = data.get("data", {}).get("organization")

    emails = []
    for e in emails_raw:
        emails.append({
            "value": e.get("value", ""),
            "type": e.get("type", "generic"),
            "confidence": e.get("confidence", 0),
            "first_name": e.get("first_name", ""),
            "last_name": e.get("last_name", ""),
            "position": e.get("position", ""),
            "source": "hunter",
        })

    result = {
        "domain": domain,
        "emails": emails,
        "pattern": pattern,
        "organization": org,
        "total_results": len(emails),
        "source": "hunter",
        "credits_used": 1,
    }

    log.info("Hunter.search_domain: %s → %d contacts found | pattern=%s", domain, len(emails), pattern)
    return result


@retry(max_attempts=3, base_delay=2.0, max_delay=30.0)
def find_email(domain: str, first_name: str, last_name: str) -> dict:
    """
    Use Hunter's email finder for a specific person.

    Returns:
        {
            "email": str | None,
            "score": int (0-100),
            "result": str,           # "deliverable" | "undeliverable" | "risky" | "webmail"
            "source": "hunter" | "dry_run",
            "credits_used": int,
        }
    """
    domain = domain.lower().strip()
    log.info("Hunter.find_email: %s %s @ %s | budget remaining=%d",
             first_name, last_name, domain, _budget.remaining)

    if config.DRY_RUN:
        return _mock_find_response(domain, first_name, last_name)

    _throttle_and_budget()

    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed. Run: pip install httpx")

    key = _get_pool().get()

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://api.hunter.io/v2/email-finder",
                params={
                    "domain": domain,
                    "first_name": first_name,
                    "last_name": last_name,
                    "api_key": key,
                },
                headers={"User-Agent": "OutreachPlatform/1.0"},
            )

        if resp.status_code == 429:
            _get_pool().ban(key)
            raise ConnectionError(f"Hunter 429 on key ...{key[-6:]}")

        if resp.status_code == 401:
            _get_pool().ban(key)
            raise RuntimeError(f"Hunter 401 — invalid key ...{key[-6:]}")

        if is_retryable_http(resp.status_code):
            raise ConnectionError(f"Hunter {resp.status_code}")

        resp.raise_for_status()
        data = resp.json()

    except httpx.TimeoutException:
        raise ConnectionError(f"Hunter email-finder timeout: {domain}")

    email_data = data.get("data", {})
    result = {
        "email": email_data.get("email"),
        "score": email_data.get("score", 0),
        "result": email_data.get("result", "unknown"),
        "source": "hunter",
        "credits_used": 1,
    }

    log.info("Hunter.find_email: %s %s → %s (score=%d)",
             first_name, last_name, result["email"], result["score"])
    return result


def get_budget_status() -> dict:
    """Return current Hunter API budget status for display in UI."""
    return _budget.status()

    # ---------------------------------------------------------------------------
# Public API Class Wrapper
# ---------------------------------------------------------------------------

class HunterClient:
    def __init__(self, api_key: str = None):
        # We store the key, but the new KeyPool manages rotation automatically
        self.api_key = api_key

    def domain_search(self, domain: str, role: str = None) -> list:
        """Compatibility for old code expecting a list of emails."""
        res = search_domain(domain)
        return res.get("emails", [])

    def search_domain(self, domain: str) -> dict:
        """New hardened function returning full metadata."""
        return search_domain(domain)

    def find_email(self, domain: str, first_name: str, last_name: str) -> dict:
        """New hardened email finder."""
        return find_email(domain, first_name, last_name)

    def get_remaining_searches(self) -> int:
        """Uses your new budget tracker."""
        return _budget.remaining
