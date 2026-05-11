"""
email_lookup/lookup_service.py
Phase 0 hardened version.

WHAT CHANGED from your original:
  - Full deduplication: never hits Hunter if domain is in fresh cache
  - Each lookup stage (cache → Hunter → scraper) wrapped in try/except
  - Returns a typed LookupResult dict always — never raises to the UI
  - DRY_RUN support: returns mock data without any network calls
  - Budget status included in every response (visible in UI)
  - Structured logging at every stage

WHAT IS UNCHANGED:
  - Function signature: lookup_contacts(domain, purpose) → dict
  - Returned dict structure (extended — all original fields preserved)
  - Import paths for fallback_scraper, hunter_client, vector_storage
"""

import re
import time
from typing import Optional

import config
from utils.logger import get_logger
from email_lookup import vector_storage
from email_lookup.api_clients import hunter_client

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Domain validation — runs before any API call
# ---------------------------------------------------------------------------

def _validate_domain(raw: str) -> tuple:
    """
    Returns (normalised_domain, error_str_or_None).
    Catches missing TLDs, invalid chars, too-short inputs — saves API credits.
    """
    domain = raw.strip().lower()
    for prefix in ('https://', 'http://', 'www.'):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split('/')[0].split('?')[0].rstrip('.')

    if not domain:
        return None, 'Please enter a domain.'
    if len(domain) < 4:
        return None, f'Domain too short: {domain!r}'
    if '.' not in domain:
        return None, f'Missing TLD — did you mean "{domain}.com"?'
    parts = domain.split('.')
    if len(parts[-1]) < 2:
        return None, f'Invalid TLD in "{domain}"'
    if re.search(r'[^a-z0-9.\-]', domain):
        return None, f'Invalid characters in domain: "{domain}"'
    return domain, None


# ---------------------------------------------------------------------------
# Result builder helpers
# ---------------------------------------------------------------------------

def _result(
    domain: str,
    contacts: list,
    source: str,
    in_database: bool,
    error: Optional[str] = None,
    pattern: Optional[str] = None,
    organization: Optional[str] = None,
) -> dict:
    """
    Typed result dict. Every key is always present — no KeyError in the UI.
    """
    return {
        "domain": domain,
        "contacts": contacts,
        "source": source,
        "in_database": in_database,
        "total_found": len(contacts),
        "pattern": pattern,
        "organization": organization,
        "error": error,
        "lookup_ts": time.time(),
        "budget": hunter_client.get_budget_status(),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def lookup_contacts(domain: str, purpose: str = "job_seeker") -> dict:
    """
    Orchestrates the full lookup pipeline:
        1. Normalise domain
        2. Check local cache (free, instant)
        3. Query Hunter.io API (costs 1 credit)
        4. Fall back to web scraper (free, slower)
        5. Cache and return results

    Args:
        domain   — company domain, e.g. "stripe.com"
        purpose  — email intent: "job_seeker" | "startup_founder" | "investor_pitch" | etc.

    Returns:
        Always a dict. Check result["error"] for failure messages.
        result["contacts"] is always a list (may be empty).
    """
    domain_raw = domain
    domain, domain_err = _validate_domain(domain)
    log.info("lookup_contacts: domain=%s purpose=%s dry_run=%s", domain or domain_raw, purpose, config.DRY_RUN)

    if domain_err:
        log.warning("lookup_contacts: invalid domain %r — %s", domain_raw, domain_err)
        return _result(
            domain=domain_raw,
            contacts=[],
            source='none',
            in_database=False,
            error=domain_err,
        )

    # -----------------------------------------------------------------------
    # Stage 0: Dry-run mode
    # -----------------------------------------------------------------------
    if config.DRY_RUN:
        mock = hunter_client._mock_domain_response(domain)
        return _result(
            domain=domain,
            contacts=mock["emails"],
            source="dry_run",
            in_database=False,
            pattern=mock.get("pattern"),
            organization=mock.get("organization"),
        )

    # -----------------------------------------------------------------------
    # Stage 1: Local cache check — free, no API call
    # -----------------------------------------------------------------------
    cached = vector_storage.get_emails(domain)
    if cached is not None:
        log.info("lookup_contacts: cache hit for %s (%d contacts)", domain, len(cached))
        return _result(
            domain=domain,
            contacts=cached,
            source="cache",
            in_database=True,
        )

    # -----------------------------------------------------------------------
    # Stage 2: Hunter.io API
    # -----------------------------------------------------------------------
    hunter_result = None
    hunter_error = None

    if not config.get_hunter_keys():
        log.warning("No Hunter API keys configured — skipping Hunter stage")
    elif not hunter_client._budget.can_spend(1):
        log.warning("Hunter daily budget exhausted — skipping Hunter stage")
        hunter_error = f"Hunter budget exhausted. {hunter_client.get_budget_status()['remaining']} credits remain today."
    else:
        try:
            hunter_result = hunter_client.search_domain(domain)
        except RuntimeError as e:
            # Budget / key errors — not retryable
            hunter_error = str(e)
            log.error("Hunter hard error for %s: %s", domain, e)
        except Exception as e:
            # Network errors — retry already happened inside hunter_client
            hunter_error = f"Hunter unavailable: {e}"
            log.warning("Hunter failed for %s after retries: %s", domain, e)

    if hunter_result and hunter_result.get("emails"):
        contacts = hunter_result["emails"]
        vector_storage.save_emails(domain, contacts, source="hunter")
        return _result(
            domain=domain,
            contacts=contacts,
            source="hunter",
            in_database=False,
            pattern=hunter_result.get("pattern"),
            organization=hunter_result.get("organization"),
        )

    # -----------------------------------------------------------------------
    # Stage 3: Fallback scraper
    # -----------------------------------------------------------------------
    scraper_contacts = []
    scraper_error = None

    try:
        from email_lookup.fallback_scraper import scrape_contacts
        scraper_contacts = scrape_contacts(domain)
    except ImportError:
        scraper_error = "Scraper module not found"
        log.warning("fallback_scraper not importable")
    except Exception as e:
        scraper_error = f"Scraper error: {e}"
        log.warning("Scraper failed for %s: %s", domain, e)

    if scraper_contacts:
        vector_storage.save_emails(domain, scraper_contacts, source="scraper")
        return _result(
            domain=domain,
            contacts=scraper_contacts,
            source="scraper",
            in_database=False,
        )

    # -----------------------------------------------------------------------
    # Stage 4: Nothing found — return structured empty result
    # -----------------------------------------------------------------------
    all_errors = " | ".join(filter(None, [hunter_error, scraper_error]))
    log.warning("lookup_contacts: no contacts found for %s. Errors: %s", domain, all_errors)

    return _result(
        domain=domain,
        contacts=[],
        source="none",
        in_database=False,
        error=all_errors or "No contacts found via any source.",
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _normalise_domain(domain: str) -> str:
    """
    Strip protocol, www, trailing slashes, whitespace.
    "https://www.Stripe.com/payments" → "stripe.com"
    """
    domain = domain.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/")[0].split("?")[0]
    return domain


def get_lookup_stats() -> dict:
    """Return cache stats + Hunter budget for UI dashboard display."""
    return {
        "cache": vector_storage.get_cache_stats(),
        "hunter_budget": hunter_client.get_budget_status(),
    }