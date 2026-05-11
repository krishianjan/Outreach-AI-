"""
utils/rate_limiter.py
Phase 0 — Three guards in one file:

1. TokenBucket     — controls burst rate (req/sec) per API
2. APIBudget       — daily credit counter (prevents burning Hunter's 50/month)
3. KeyPool         — round-robin key rotation with ban-on-429

All pure stdlib. Thread-safe. Zero external deps.

Usage:
    from utils.rate_limiter import TokenBucket, APIBudget, KeyPool

    hunter_throttle = TokenBucket(capacity=3, refill_rate=1/60)   # 1 req/min sustained
    hunter_budget   = APIBudget(daily_limit=8, name="Hunter")       # 8 calls/day max
    hunter_keys     = KeyPool(["key1", "key2"])                     # rotate keys

    # Before every Hunter call:
    wait = hunter_throttle.consume()
    if wait: time.sleep(wait)
    hunter_budget.spend()                # raises RuntimeError if exhausted
    key = hunter_keys.get()             # raises RuntimeError if all banned
"""

import itertools
import threading
import time
from utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Token Bucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """
    Leaky-bucket rate limiter.

    capacity     — max burst (tokens)
    refill_rate  — tokens added per second

    Examples:
        # Hunter: allow burst of 3, then 1 per 60s
        bucket = TokenBucket(capacity=3, refill_rate=1/60)

        # Gemini Flash: 15 req/min → ~0.25/sec
        bucket = TokenBucket(capacity=5, refill_rate=0.25)
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> float:
        """
        Try to consume `tokens`. Returns seconds to sleep (0.0 if no wait).
        Call time.sleep(bucket.consume()) before your API call.
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            wait = (tokens - self._tokens) / self.refill_rate
            return wait

    def consume_blocking(self, tokens: float = 1.0) -> None:
        """Consume tokens, sleeping if necessary. Use in non-async code."""
        wait = self.consume(tokens)
        if wait > 0:
            log.debug("Rate limiter: sleeping %.2fs", wait)
            time.sleep(wait)


# ---------------------------------------------------------------------------
# 2. API Budget (daily credit counter)
# ---------------------------------------------------------------------------

class APIBudget:
    """
    Hard daily limit on API credits. Resets every 24 hours.
    Raises RuntimeError if limit would be exceeded — never silently wastes credits.

    Hunter free tier: 50 req/month ≈ ~1-2/day.
    Set daily_limit conservatively — you can always raise it.
    """

    def __init__(self, daily_limit: int, name: str = "api"):
        self.daily_limit = daily_limit
        self.name = name
        self._count = 0
        self._reset_at = time.time() + 86400
        self._lock = threading.Lock()

    def _maybe_reset(self) -> bool:
        """Check reset — must be called WITHOUT holding the lock. Returns True if reset occurred."""
        if time.time() >= self._reset_at:
            with self._lock:
                # Double-check after acquiring lock (another thread may have reset already)
                if time.time() >= self._reset_at:
                    old = self._count
                    self._count = 0
                    self._reset_at = time.time() + 86400
                    return True
        return False

    def can_spend(self, amount: int = 1) -> bool:
        self._maybe_reset()
        with self._lock:
            return (self._count + amount) <= self.daily_limit

    def spend(self, amount: int = 1) -> int:
        """
        Deduct `amount` credits. Raises RuntimeError if budget exhausted.
        Returns total used today.
        """
        self._maybe_reset()
        with self._lock:
            if self._count + amount > self.daily_limit:
                secs_left = int(self._reset_at - time.time())
                raise RuntimeError(
                    f"[{self.name}] Daily budget exhausted "
                    f"({self._count}/{self.daily_limit}). "
                    f"Resets in {secs_left//3600}h {(secs_left%3600)//60}m."
                )
            self._count += amount
            count = self._count
        # Log outside the lock — prevents deadlock with logging handler's own lock
        log.debug("APIBudget[%s]: spent %d → %d/%d used", self.name, amount, count, self.daily_limit)
        return count

    @property
    def remaining(self) -> int:
        self._maybe_reset()
        with self._lock:
            return max(0, self.daily_limit - self._count)

    @property
    def used(self) -> int:
        with self._lock:
            return self._count

    def status(self) -> dict:
        self._maybe_reset()
        with self._lock:
            used = self._count
            limit = self.daily_limit
            resets_in = max(0, int(self._reset_at - time.time()))
        # Build dict outside lock — no logging inside lock
        return {
            "api": self.name,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "resets_in_seconds": resets_in,
        }


# ---------------------------------------------------------------------------
# 3. Key Pool (round-robin rotation + ban)
# ---------------------------------------------------------------------------

class KeyPool:
    """
    Manages a pool of API keys. Rotates round-robin.
    On 429/403, call pool.ban(key) to skip that key.

    Usage:
        pool = KeyPool(["keyA", "keyB", "keyC"])
        key = pool.get()           # round-robin, skips banned
        pool.ban(key)              # mark exhausted/blocked
        pool.unban_all()           # call at midnight reset
    """

    def __init__(self, keys: list):
        valid = [k.strip() for k in keys if k and k.strip()]
        if not valid:
            raise ValueError("KeyPool: no valid API keys provided")
        self._keys = valid
        self._cycle = itertools.cycle(valid)
        self._banned: set = set()
        self._lock = threading.Lock()
        log.info("KeyPool: initialized with %d key(s)", len(valid))

    def get(self) -> str:
        with self._lock:
            for _ in range(len(self._keys)):
                key = next(self._cycle)
                if key not in self._banned:
                    return key
            raise RuntimeError(
                "KeyPool: all API keys are banned or exhausted. "
                "Check your .env for additional keys or wait for rate limit reset."
            )

    def ban(self, key: str) -> None:
        with self._lock:
            self._banned.add(key)
            suffix = key[-6:] if len(key) >= 6 else key
            log.warning("KeyPool: key ...%s banned (429/403). %d/%d keys remain active.",
                        suffix, len(self._keys) - len(self._banned), len(self._keys))

    def unban_all(self) -> None:
        with self._lock:
            self._banned.clear()
            log.info("KeyPool: all keys unbanned (daily reset)")

    @property
    def active_count(self) -> int:
        return len(self._keys) - len(self._banned)


# ---------------------------------------------------------------------------
# Pre-built instances — import and use directly
# ---------------------------------------------------------------------------

# Hunter.io — 50 req/month free tier
# Burst of 3, then 1 per 90s sustained. Daily cap of 8 (conservative).
# Adjust HUNTER_DAILY_LIMIT in .env to override.

import os

_hunter_daily = int(os.environ.get("HUNTER_DAILY_LIMIT", "8"))
_hunter_keys_raw = [
    os.environ.get("HUNTER_API_KEY", ""),
    os.environ.get("HUNTER_API_KEY_2", ""),  # add second key in .env if you have it
    os.environ.get("HUNTER_API_KEY_3", ""),
]

# Lazy init — only create if keys are present
def _make_hunter_pool():
    valid = [k for k in _hunter_keys_raw if k.strip()]
    if not valid:
        return None
    return KeyPool(valid)


hunter_throttle = TokenBucket(capacity=3, refill_rate=1 / 90)
hunter_budget = APIBudget(daily_limit=_hunter_daily, name="Hunter")
hunter_keys: KeyPool | None = None  # initialized on first use


def get_hunter_key() -> str:
    global hunter_keys
    if hunter_keys is None:
        hunter_keys = _make_hunter_pool()
    if hunter_keys is None:
        raise RuntimeError("No HUNTER_API_KEY found in environment")
    return hunter_keys.get()


# Gemini Flash — 15 req/min, 1500/day free
_gemini_daily = int(os.environ.get("GEMINI_DAILY_LIMIT", "200"))
_gemini_keys_raw = [os.environ.get("GEMINI_API_KEY", "")]

gemini_throttle = TokenBucket(capacity=5, refill_rate=0.2)   # ~12 req/min sustained
gemini_budget = APIBudget(daily_limit=_gemini_daily, name="Gemini")


# Groq — very generous free tier, mostly uncapped in practice
groq_throttle = TokenBucket(capacity=10, refill_rate=0.5)   # 30 req/min sustained