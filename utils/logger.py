"""
utils/logger.py
Phase 0 — Structured logging for every module.

Drop-in: from utils.logger import get_logger; log = get_logger(__name__)
Writes to both console and outreach.log file.
Rotation: 5MB max, 3 backups — never fills disk.
"""

import logging
import logging.handlers
import os
import sys

_LOG_FILE = os.environ.get("LOG_FILE", "outreach.log")
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_initialized = False


def _setup():
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger("outreach")
    root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Rotating file handler — DEBUG and above (full trace in log file)
    try:
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except (OSError, PermissionError):
        # HF Spaces or read-only FS — just console logging is fine
        root.warning("Could not open log file %s — console only", _LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """
    Usage:
        from utils.logger import get_logger
        log = get_logger(__name__)
        log.info("Found %d contacts for %s", count, domain)
    """
    _setup()
    # Always prefix with 'outreach.' so root handler catches it
    if not name.startswith("outreach"):
        name = f"outreach.{name}"
    return logging.getLogger(name)