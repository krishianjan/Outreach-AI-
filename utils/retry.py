"""
utils/retry.py
Phase 0 — Exponential backoff retry decorator. Pure stdlib, zero deps.

Wraps any function. On exception, sleeps and retries with jitter.
On final failure, logs full traceback and re-raises — never swallows errors.

Usage:
    from utils.retry import retry

    @retry(max_attempts=4, base_delay=1.0, retryable=(ConnectionError, TimeoutError))
    def call_hunter_api(domain):
        ...

    # Or inline for one-off calls:
    from utils.retry import call_with_retry
    result = call_with_retry(lambda: requests.get(url), max_attempts=3)
"""

import functools
import random
import time
import traceback
from typing import Callable, Tuple, Type

from utils.logger import get_logger

log = get_logger(__name__)

# HTTP status codes that are worth retrying (transient errors)
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def retry(
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 1.0,
    retryable: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable = None,
):
    """
    Decorator: retry on retryable exceptions with exponential backoff + jitter.

    Args:
        max_attempts  — total tries (including first attempt)
        base_delay    — seconds before first retry
        max_delay     — cap on sleep time
        jitter        — max random seconds added to each delay (prevents thundering herd)
        retryable     — exception types that trigger a retry (default: all)
        on_retry      — optional callback(attempt, exception, delay) for custom logging

    Delay formula: min(base_delay * 2^attempt + uniform(0, jitter), max_delay)
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except retryable as e:
                    last_exc = e
                    if attempt == max_attempts - 1:
                        break  # final attempt failed — fall through to raise

                    delay = min(
                        base_delay * (2 ** attempt) + random.uniform(0, jitter),
                        max_delay,
                    )

                    log.warning(
                        "retry: %s attempt %d/%d failed — %s. Sleeping %.2fs",
                        fn.__name__, attempt + 1, max_attempts, str(e), delay
                    )

                    if on_retry:
                        try:
                            on_retry(attempt, e, delay)
                        except Exception:
                            pass

                    time.sleep(delay)

            log.error(
                "retry: %s failed after %d attempts. Last error: %s",
                fn.__name__, max_attempts, str(last_exc)
            )
            raise last_exc

        return wrapper

    return decorator


def call_with_retry(
    fn: Callable,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: Tuple[Type[Exception], ...] = (Exception,),
) -> any:
    """
    Inline retry without decorator. Returns result on success, raises on final failure.

    Example:
        result = call_with_retry(lambda: hunter_api.search(domain), max_attempts=3)
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except retryable as e:
            last_exc = e
            if attempt == max_attempts - 1:
                break
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
            log.warning("call_with_retry attempt %d/%d: %s. Retrying in %.2fs", attempt + 1, max_attempts, e, delay)
            time.sleep(delay)

    log.error("call_with_retry exhausted %d attempts. Error: %s", max_attempts, last_exc)
    raise last_exc


def is_retryable_http(status_code: int) -> bool:
    """True if the HTTP status code is worth retrying."""
    return status_code in RETRYABLE_HTTP_CODES