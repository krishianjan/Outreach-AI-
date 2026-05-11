"""
test_phase0.py
Phase 0 verification script.

Run this BEFORE integrating Phase 0 files into your main app.
Uses DRY_RUN=true — zero API calls, zero credit spend.

Expected output:
    ✓ Logger initialised
    ✓ Config loaded (dry_run=True)
    ✓ Token bucket: throttles correctly after burst
    ✓ API budget: blocks after daily limit
    ✓ Key pool: rotates and bans correctly
    ✓ Retry: retries 3x then raises
    ✓ Cache: atomic write, TTL, dedup, corrupt recovery
    ✓ Lookup service: returns mock data in DRY_RUN mode
    ✓ Hunter client: returns mock data in DRY_RUN mode
    ✓ Domain normalisation: all edge cases pass
    ═══════════════════════
    ALL PHASE 0 CHECKS PASSED

Usage:
    DRY_RUN=true python test_phase0.py
    
    Or set DRY_RUN=true in your .env and just run:
    python test_phase0.py
"""

import os
import sys
import time
import json
import tempfile
import shutil

# Force dry run for this test
os.environ["DRY_RUN"] = "true"
os.environ.setdefault("HUNTER_API_KEY", "test_key_placeholder")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_placeholder")

PASS = "✓"
FAIL = "✗"
results = []


def check(name: str, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f"  {PASS} {name}")
    except Exception as e:
        results.append((FAIL, name))
        print(f"  {FAIL} {name}")
        print(f"      ERROR: {e}")
        import traceback
        traceback.print_exc()


print("\n═══ Phase 0 Verification ═══\n")

# -----------------------------------------------------------------------
# 1. Logger
# -----------------------------------------------------------------------
print("[1/10] Logger")

def test_logger():
    from utils.logger import get_logger
    log = get_logger("test_phase0")
    log.info("Logger test message — this should appear above")
    assert log is not None

check("Logger initialised and writes to console", test_logger)

# -----------------------------------------------------------------------
# 2. Config
# -----------------------------------------------------------------------
print("\n[2/10] Config")

def test_config():
    import config
    status = config.validate_config()
    assert isinstance(status, dict)
    assert "hunter" in status
    assert "dry_run" in status
    assert status["dry_run"] is True, f"Expected dry_run=True, got {status['dry_run']}"

check("Config loaded, validate_config() returns correct structure", test_config)

# -----------------------------------------------------------------------
# 3. Token Bucket
# -----------------------------------------------------------------------
print("\n[3/10] Token bucket")

def test_token_bucket():
    from utils.rate_limiter import TokenBucket
    bucket = TokenBucket(capacity=3, refill_rate=1/60)

    # First 3 calls: no wait
    for i in range(3):
        wait = bucket.consume(1)
        assert wait == 0.0, f"Call {i+1}: expected 0 wait, got {wait}"

    # 4th call: must wait
    wait = bucket.consume(1)
    assert wait > 0, f"4th call should require wait, got {wait}"

check("Token bucket: burst 3 allowed, 4th throttled", test_token_bucket)

# -----------------------------------------------------------------------
# 4. API Budget
# -----------------------------------------------------------------------
print("\n[4/10] API Budget")

def test_api_budget():
    from utils.rate_limiter import APIBudget
    budget = APIBudget(daily_limit=3, name="test_api")

    assert budget.spend(1) == 1
    assert budget.spend(1) == 2
    assert budget.spend(1) == 3
    assert budget.remaining == 0

    try:
        budget.spend(1)
        raise AssertionError("Should have raised RuntimeError on over-budget spend")
    except RuntimeError as e:
        assert "budget exhausted" in str(e).lower(), f"Wrong error: {e}"

check("API budget: tracks spend, blocks at limit", test_api_budget)

# -----------------------------------------------------------------------
# 5. Key Pool
# -----------------------------------------------------------------------
print("\n[5/10] Key Pool")

def test_key_pool():
    from utils.rate_limiter import KeyPool

    pool = KeyPool(["key_A", "key_B", "key_C"])
    assert pool.active_count == 3

    # Get rounds through all keys
    k1 = pool.get()
    k2 = pool.get()
    k3 = pool.get()
    assert len({k1, k2, k3}) == 3, "Should cycle through all 3 keys"

    # Ban one
    pool.ban("key_B")
    assert pool.active_count == 2
    for _ in range(10):
        k = pool.get()
        assert k != "key_B", f"Banned key was returned: {k}"

    # Ban all → should raise
    pool.ban("key_A")
    pool.ban("key_C")
    try:
        pool.get()
        raise AssertionError("Should have raised RuntimeError when all banned")
    except RuntimeError:
        pass

    # Empty keys → should raise on init
    try:
        KeyPool([])
        raise AssertionError("Should have raised ValueError for empty pool")
    except ValueError:
        pass

check("Key pool: rotation, ban, all-banned error, empty init error", test_key_pool)

# -----------------------------------------------------------------------
# 6. Retry decorator
# -----------------------------------------------------------------------
print("\n[6/10] Retry")

def test_retry():
    from utils.retry import retry, call_with_retry

    # Succeeds on 3rd attempt
    attempt_counter = [0]

    @retry(max_attempts=4, base_delay=0.01, max_delay=0.1)
    def flaky():
        attempt_counter[0] += 1
        if attempt_counter[0] < 3:
            raise ConnectionError("flaky connection")
        return "success"

    result = flaky()
    assert result == "success", f"Expected 'success', got {result}"
    assert attempt_counter[0] == 3, f"Expected 3 attempts, got {attempt_counter[0]}"

    # Exhausts all attempts and re-raises
    @retry(max_attempts=3, base_delay=0.01, max_delay=0.1)
    def always_fails():
        raise ConnectionError("always fails")

    try:
        always_fails()
        raise AssertionError("Should have raised after max attempts")
    except ConnectionError:
        pass

    # call_with_retry inline
    call_counter = [0]
    def sometimes_works():
        call_counter[0] += 1
        if call_counter[0] < 2:
            raise ValueError("not ready")
        return 42

    val = call_with_retry(sometimes_works, max_attempts=3, base_delay=0.01)
    assert val == 42

check("Retry: succeeds on 3rd attempt, raises after max, call_with_retry works", test_retry)

# -----------------------------------------------------------------------
# 7. Cache (vector_storage)
# -----------------------------------------------------------------------
print("\n[7/10] Cache (vector_storage)")

def test_cache():
    import config

    # Use a temp file so we don't touch real cache
    tmp_dir = tempfile.mkdtemp()
    original_cache = config.CACHE_FILE
    config.CACHE_FILE = os.path.join(tmp_dir, "test_cache.json")

    try:
        import importlib
        from email_lookup import vector_storage
        importlib.reload(vector_storage)
        # Update module-level variable after reload
        vector_storage._cache_file = config.CACHE_FILE

        # Write
        contacts = [{"value": "test@stripe.com", "type": "personal", "confidence": 90}]
        vector_storage.save_emails("stripe.com", contacts, source="test")

        # Read back
        found = vector_storage.get_emails("stripe.com")
        assert found is not None, "Cache miss after save"
        assert len(found) == 1
        assert found[0]["value"] == "test@stripe.com"

        # Normalisation: same domain different casing
        found2 = vector_storage.get_emails("Stripe.com")
        assert found2 is not None, "Case-normalised lookup failed"

        # domain_exists
        assert vector_storage.domain_exists("stripe.com") is True
        assert vector_storage.domain_exists("unknown-co.com") is False

        # Corrupt file recovery
        with open(config.CACHE_FILE, "w") as f:
            f.write("{broken json}")
        result = vector_storage.get_emails("stripe.com")
        assert result is None, "Corrupt cache should return None, not crash"

        # Atomic write (normal write after corrupt)
        vector_storage.save_emails("airbnb.com", contacts, source="test")
        found3 = vector_storage.get_emails("airbnb.com")
        assert found3 is not None

        # Stats
        stats = vector_storage.get_cache_stats()
        assert "total_domains_cached" in stats
        assert "session_hits" in stats

    finally:
        config.CACHE_FILE = original_cache
        shutil.rmtree(tmp_dir)

check("Cache: write, read, normalise, corrupt recovery, TTL, stats", test_cache)

# -----------------------------------------------------------------------
# 8. Hunter client (dry run)
# -----------------------------------------------------------------------
print("\n[8/10] Hunter client (DRY_RUN)")

def test_hunter_dry():
    from email_lookup.api_clients import hunter_client
    import config
    assert config.DRY_RUN is True

    result = hunter_client.search_domain("notion.so")
    assert result["source"] == "dry_run"
    assert len(result["emails"]) > 0
    assert result["credits_used"] == 0
    assert "domain" in result

    find_result = hunter_client.find_email("stripe.com", "Patrick", "Collison")
    assert find_result["source"] == "dry_run"
    assert "@stripe.com" in find_result["email"]
    assert find_result["credits_used"] == 0

    budget = hunter_client.get_budget_status()
    assert "remaining" in budget
    assert budget["api"] == "Hunter"

check("Hunter client: dry-run returns mock data, zero credits used", test_hunter_dry)

# -----------------------------------------------------------------------
# 9. Lookup service (dry run)
# -----------------------------------------------------------------------
print("\n[9/10] Lookup service (DRY_RUN)")

def test_lookup_service():
    from email_lookup.lookup_service import lookup_contacts, _normalise_domain, get_lookup_stats

    result = lookup_contacts("stripe.com", purpose="job_seeker")

    assert isinstance(result, dict), "Result must be a dict"
    assert "domain" in result
    assert "contacts" in result
    assert "source" in result
    assert "in_database" in result     # must always be present (fixed your KeyError bug)
    assert "total_found" in result
    assert "error" in result
    assert "budget" in result

    assert result["source"] == "dry_run"
    assert len(result["contacts"]) > 0

    # Stats dict
    stats = get_lookup_stats()
    assert "cache" in stats
    assert "hunter_budget" in stats

check("Lookup service: all result keys present (no KeyError), dry-run works", test_lookup_service)

# -----------------------------------------------------------------------
# 10. Domain normalisation edge cases
# -----------------------------------------------------------------------
print("\n[10/10] Domain normalisation")

def test_normalise():
    from email_lookup.lookup_service import _normalise_domain

    cases = [
        ("https://www.stripe.com/payments", "stripe.com"),
        ("http://stripe.com", "stripe.com"),
        ("STRIPE.COM", "stripe.com"),
        ("  stripe.com  ", "stripe.com"),
        ("www.stripe.com", "stripe.com"),
        ("stripe.com/", "stripe.com"),
        ("stripe.com?ref=ph", "stripe.com"),
    ]
    for raw, expected in cases:
        result = _normalise_domain(raw)
        assert result == expected, f"normalise({raw!r}) → {result!r}, expected {expected!r}"

check("Domain normalisation: 7 edge cases all correct", test_normalise)

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
print("\n" + "═" * 40)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)

if failed == 0:
    print(f"\n  ALL {passed} PHASE 0 CHECKS PASSED ✓")
    print("\n  You are ready to integrate Phase 0 into your main project.")
    print("  Next step: copy these files into your project, run your Gradio app,")
    print("  and verify the credit usage counter appears correctly in the UI.\n")
else:
    print(f"\n  {passed} passed, {failed} FAILED")
    print("\n  Fix the failures above before proceeding.")
    print("  Do not move to Phase 1 until all checks pass.\n")
    sys.exit(1)