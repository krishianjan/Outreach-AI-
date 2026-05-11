"""
email_lookup/vector_storage.py
Phase 0 hardened version.

WHAT CHANGED from your original:
  - Atomic writes (write-then-rename) — corrupt JSON impossible if process dies mid-write
  - Corrupt JSON auto-recovery — reads empty dict instead of crashing
  - TTL enforcement on reads — stale cache entries are treated as misses
  - Dedup key normalisation — "Stripe.com" and "stripe.com " hash to same key
  - Cache stats: hit_count, miss_count, stale_count tracked in memory
  - Thread-safe: RLock on all read/write operations

WHAT IS UNCHANGED:
  - Cache file location (reads CACHE_FILE from config, defaults to email_cache.json)
  - Data structure stored in cache (compatible with existing entries)
  - Function signatures: save_emails(), get_emails(), domain_exists()
"""

import hashlib
import json
import os
import threading
import time
from typing import Optional

import config
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_cache_file: str = config.CACHE_FILE
_ttl_hours: int = config.CACHE_TTL_HOURS
_lock = threading.RLock()

_stats = {"hits": 0, "misses": 0, "stale": 0, "writes": 0}


# ---------------------------------------------------------------------------
# Key normalisation
# ---------------------------------------------------------------------------

def _cache_key(domain: str, role: Optional[str] = None) -> str:
    """
    Normalise domain + optional role to a consistent cache key.
    "Stripe.com ", " stripe.com", "stripe.com" all map to same hash.
    """
    base = domain.lower().strip().rstrip("/")
    if role:
        base += ":" + role.lower().strip()
    return hashlib.md5(base.encode()).hexdigest()


def _raw_domain_key(domain: str) -> str:
    """Normalised domain string (not hashed) — used as the JSON dict key."""
    return domain.lower().strip().rstrip("/")


# ---------------------------------------------------------------------------
# File I/O — atomic and safe
# ---------------------------------------------------------------------------

def _safe_load() -> dict:
    """Load cache file. Returns empty dict on missing or corrupt JSON."""
    if not os.path.exists(_cache_file):
        return {}
    try:
        with open(_cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                log.warning("Cache file contains non-dict JSON — resetting")
                return {}
            return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cache file corrupt or unreadable (%s) — starting fresh", e)
        return {}


def _atomic_save(data: dict) -> None:
    """
    Write cache atomically: write to .tmp file, then rename.
    On POSIX (Linux/Mac), os.replace() is atomic.
    On Windows, os.replace() is as atomic as it gets.
    """
    tmp_path = _cache_file + f".tmp.{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, _cache_file)
        log.debug("Cache: atomic write OK → %s (%d entries)", _cache_file, len(data))
    except OSError as e:
        log.error("Cache: atomic write FAILED — %s", e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Public API (same signatures as original vector_storage.py)
# ---------------------------------------------------------------------------

def save_emails(domain: str, contacts: list, source: str = "unknown") -> None:
    """
    Save discovered contacts for a domain.

    contacts: list of dicts, each with at minimum {"value": "email@co.com"}
    source: "hunter" | "scraper" | "dry_run" | ...

    Thread-safe, atomic write.
    """
    domain_key = _raw_domain_key(domain)
    entry = {
        "domain": domain_key,
        "contacts": contacts,
        "source": source,
        "cached_at": time.time(),
        "ttl_hours": _ttl_hours,
    }

    with _lock:
        cache = _safe_load()
        cache[domain_key] = entry
        _atomic_save(cache)
        _stats["writes"] += 1

    log.info("Cache: saved %d contacts for %s (source=%s)", len(contacts), domain_key, source)


def get_emails(domain: str) -> Optional[list]:
    """
    Retrieve cached contacts for a domain, respecting TTL.

    Returns:
        list of contact dicts — if cache hit and fresh
        None                  — if miss, stale, or corrupt entry
    """
    domain_key = _raw_domain_key(domain)

    with _lock:
        cache = _safe_load()
        entry = cache.get(domain_key)

    if entry is None:
        _stats["misses"] += 1
        log.debug("Cache miss: %s", domain_key)
        return None

    # TTL check
    cached_at = entry.get("cached_at", 0)
    entry_ttl = entry.get("ttl_hours", _ttl_hours)
    age_hours = (time.time() - cached_at) / 3600

    if age_hours > entry_ttl:
        _stats["stale"] += 1
        log.info("Cache stale: %s (age=%.1fh, ttl=%dh)", domain_key, age_hours, entry_ttl)
        return None

    _stats["hits"] += 1
    contacts = entry.get("contacts", [])
    log.info("Cache hit: %s → %d contacts (age=%.1fh)", domain_key, len(contacts), age_hours)
    return contacts


def domain_exists(domain: str) -> bool:
    """
    Check if domain is in cache AND fresh. Does not load contacts.
    Use this for deduplication checks before spending API credits.
    """
    return get_emails(domain) is not None


def invalidate(domain: str) -> bool:
    """Force-remove a domain from cache (e.g. after finding bad data)."""
    domain_key = _raw_domain_key(domain)
    with _lock:
        cache = _safe_load()
        if domain_key in cache:
            del cache[domain_key]
            _atomic_save(cache)
            log.info("Cache: invalidated %s", domain_key)
            return True
    return False


def get_all_domains() -> list:
    """Return all cached domain keys (for UI display / stats)."""
    with _lock:
        cache = _safe_load()
    return list(cache.keys())


def get_cache_stats() -> dict:
    """Return in-memory hit/miss stats + file stats."""
    with _lock:
        cache = _safe_load()
        total = len(cache)
        # Count stale entries
        now = time.time()
        stale_count = sum(
            1 for v in cache.values()
            if (now - v.get("cached_at", 0)) / 3600 > v.get("ttl_hours", _ttl_hours)
        )

    return {
        "total_domains_cached": total,
        "stale_entries": stale_count,
        "fresh_entries": total - stale_count,
        "session_hits": _stats["hits"],
        "session_misses": _stats["misses"],
        "session_stale_hits": _stats["stale"],
        "session_writes": _stats["writes"],
        "cache_file": _cache_file,
        "ttl_hours": _ttl_hours,
    }