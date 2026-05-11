

"""
email_lookup/email_verifier.py
Phase 1 — Hardened rewrite


REAL-WORLD LIMITS:
  - Gmail/Google Workspace (~70% of YC startups): always returns 250 = catch-all
  - Port 25 may be blocked by your ISP (common on residential IPs)
  - SMTP probing too fast → IP blacklisted. Min 5s between probes per domain.
  - Rate limit: max 3 SMTP probes per domain per 30min

Usage:
    from email_lookup.email_verifier import verify_email, verify_batch

    result = verify_email('patrick@stripe.com', source='hunter', hunter_score=92)
    # result['grade']  → 'HIGH' | 'MEDIUM' | 'LOW'
    # result['status'] → 'valid' | 'invalid' | 'catch_all' | 'unknown' | 'blocked'
    # result['send_recommended'] → True | False
"""

import re
import socket
import time
import threading
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# RFC 5322-compliant email regex (local part up to 64 chars, domain validated separately)
EMAIL_FORMAT_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)

# SMTP response codes
SMTP_VALID_CODES   = {250, 251}
SMTP_INVALID_CODES = {550, 551, 552, 553, 554}
SMTP_TEMP_CODES    = {421, 450, 451, 452}

# Mail providers known to catch-all (SMTP probe returns 250 for anything)
CATCH_ALL_PROVIDERS = {
    'google.com', 'googlemail.com',      # Google Workspace
    'outlook.com', 'hotmail.com',         # Microsoft 365
    'protonmail.ch',                      # ProtonMail
}

# Per-domain SMTP probe rate limit (max 3 per 30min)
_domain_probe_times: dict = {}
_probe_lock = threading.Lock()
PROBE_COOLDOWN_SECS = 1800  # 30 min
MAX_PROBES_PER_WINDOW = 3
SMTP_TIMEOUT = 8  # seconds per connection attempt


# ---------------------------------------------------------------------------
# Status definitions
# ---------------------------------------------------------------------------

class VerifyStatus:
    VALID      = 'valid'       # SMTP confirmed exists
    INVALID    = 'invalid'     # SMTP confirmed does not exist
    CATCH_ALL  = 'catch_all'   # Domain accepts everything (can't confirm individual)
    UNKNOWN    = 'unknown'     # Temp failure or inconclusive
    BLOCKED    = 'blocked'     # Port 25 blocked / connection refused
    BAD_FORMAT = 'bad_format'  # Failed regex
    NO_MX      = 'no_mx'       # Domain has no mail exchanger — definitely dead


# ---------------------------------------------------------------------------
# Step 1: Format validation
# ---------------------------------------------------------------------------

def check_format(email: str) -> bool:
    return bool(EMAIL_FORMAT_RE.match(email.strip()))


# ---------------------------------------------------------------------------
# Step 2: MX record lookup (free, instant, eliminates ~30% of dead domains)
# ---------------------------------------------------------------------------

def get_mx_records(domain: str) -> list:
    """
    Returns list of (priority, mx_host) tuples sorted by priority.
    Returns empty list if domain has no MX records.
    Uses stdlib socket + dnspython if available, falls back gracefully.
    """
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5.0)
        records = [(r.preference, str(r.exchange).rstrip('.')) for r in answers]
        return sorted(records, key=lambda x: x[0])
    except ImportError:
        # dnspython not installed — skip MX, proceed to SMTP
        log.debug("dnspython not installed — skipping MX lookup for %s", domain)
        return [(-1, domain)]  # signal: try SMTP directly
    except Exception as e:
        log.debug("MX lookup failed for %s: %s", domain, e)
        return []


def detect_mail_provider(mx_hosts: list) -> Optional[str]:
    """Identify mail provider from MX records to predict catch-all behavior."""
    if not mx_hosts:
        return None
    for _, host in mx_hosts:
        host_l = host.lower()
        if 'google' in host_l or 'gmail' in host_l:
            return 'google_workspace'
        if 'outlook' in host_l or 'microsoft' in host_l or 'protection.outlook' in host_l:
            return 'microsoft_365'
        if 'protonmail' in host_l:
            return 'protonmail'
        if 'zoho' in host_l:
            return 'zoho'
        if 'mailgun' in host_l:
            return 'mailgun'
    return 'custom'


# ---------------------------------------------------------------------------
# Step 3 & 4: SMTP probe
# ---------------------------------------------------------------------------

def _can_probe_domain(domain: str) -> bool:
    """Rate-limit check: max 3 probes per domain per 30min."""
    with _probe_lock:
        now = time.time()
        times = [t for t in _domain_probe_times.get(domain, []) if now - t < PROBE_COOLDOWN_SECS]
        _domain_probe_times[domain] = times
        if len(times) >= MAX_PROBES_PER_WINDOW:
            log.info("SMTP rate limit: %s has %d probes in last 30min — skipping", domain, len(times))
            return False
        _domain_probe_times[domain].append(now)
        return True


def _smtp_probe(mx_host: str, target_email: str, sender_domain: str = 'check.outreach.io') -> int:
    """
    Perform SMTP RCPT TO probe without sending email.
    
    Returns the SMTP response code for RCPT TO:
      250 = mailbox exists (or catch-all)
      550 = mailbox does not exist
      421/45x = temporary failure
      -1 = connection failed / timeout / port blocked
    
    CRITICAL: Never sends actual email data. Only uses EHLO + MAIL FROM + RCPT TO.
    """
    try:
        with socket.create_connection((mx_host, 25), timeout=SMTP_TIMEOUT) as sock:
            sock.settimeout(SMTP_TIMEOUT)

            def recv():
                data = b''
                while True:
                    chunk = sock.recv(1024)
                    data += chunk
                    if data.endswith(b'\r\n') or len(data) > 4096:
                        break
                return data.decode('utf-8', errors='ignore')

            banner = recv()
            if not banner.startswith('220'):
                log.debug("SMTP: %s bad banner: %r", mx_host, banner[:80])
                return -1

            # EHLO
            sock.sendall(f'EHLO {sender_domain}\r\n'.encode())
            recv()  # consume response

            # MAIL FROM (throwaway sender)
            sock.sendall(f'MAIL FROM:<verify@{sender_domain}>\r\n'.encode())
            recv()

            # RCPT TO (target)
            sock.sendall(f'RCPT TO:<{target_email}>\r\n'.encode())
            rcpt_resp = recv()

            # Parse code
            code_match = re.match(r'^(\d{3})', rcpt_resp)
            code = int(code_match.group(1)) if code_match else -1

            # Quit cleanly
            try:
                sock.sendall(b'QUIT\r\n')
            except Exception:
                pass

            return code

    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        log.debug("SMTP probe failed: %s → %s: %s", mx_host, target_email, e)
        return -1


def smtp_verify(
    email: str,
    mx_host: str,
    domain: str,
) -> tuple:
    """
    Full SMTP probe sequence: probe real email + probe fake email (catch-all detection).

    Returns:
        (status: str, rcpt_code: int, is_catch_all: bool)
    """
    if not _can_probe_domain(domain):
        return VerifyStatus.UNKNOWN, -1, False

    # Step A: probe a definitely-fake address to detect catch-all
    fake_local = 'zzz_definitely_fake_xyz_123'
    fake_email = f'{fake_local}@{domain}'

    log.debug("SMTP: probing fake address %s on %s", fake_email, mx_host)
    fake_code = _smtp_probe(mx_host, fake_email)

    if fake_code in SMTP_VALID_CODES:
        # Domain accepts anything — catch-all
        log.info("SMTP: %s is catch-all (fake addr returned %d)", domain, fake_code)
        return VerifyStatus.CATCH_ALL, fake_code, True

    # Step B: probe the real target address
    log.debug("SMTP: probing real address %s on %s", email, mx_host)
    time.sleep(2)  # brief pause between probes — avoid rapid-fire detection
    real_code = _smtp_probe(mx_host, email)

    if real_code in SMTP_VALID_CODES:
        return VerifyStatus.VALID, real_code, False
    elif real_code in SMTP_INVALID_CODES:
        return VerifyStatus.INVALID, real_code, False
    elif real_code in SMTP_TEMP_CODES:
        return VerifyStatus.UNKNOWN, real_code, False
    elif real_code == -1:
        return VerifyStatus.BLOCKED, -1, False
    else:
        return VerifyStatus.UNKNOWN, real_code, False


# ---------------------------------------------------------------------------
# Step 5: Composite confidence score
# ---------------------------------------------------------------------------

def compute_confidence(
    smtp_status: str,
    pattern_confidence: float,
    source: str,
    hunter_score: int = 0,
    mail_provider: Optional[str] = None,
) -> dict:
    """
    Combine all signals into a single confidence score and send recommendation.

    Thresholds (calibrated against dry-run cases):
      HIGH   ≥ 0.65  → send with confidence
      MEDIUM ≥ 0.42  → send with appropriate hedging
      LOW    < 0.42  → skip or use only as last resort
    """
    SOURCE_WEIGHTS = {
        'hunter':   0.90,
        'scraper':  0.75,
        'inferred': 0.40,
        'cache':    0.80,
    }
    SMTP_WEIGHTS = {
        VerifyStatus.VALID:      1.00,
        VerifyStatus.CATCH_ALL:  0.50,   # inconclusive but not dead
        VerifyStatus.UNKNOWN:    0.40,
        VerifyStatus.BLOCKED:    0.30,
        VerifyStatus.INVALID:    0.00,
        VerifyStatus.NO_MX:      0.00,
        VerifyStatus.BAD_FORMAT: 0.00,
    }

    smtp_w   = SMTP_WEIGHTS.get(smtp_status, 0.30)
    source_w = SOURCE_WEIGHTS.get(source, 0.40)
    hunter_w = (hunter_score / 100.0) if hunter_score else pattern_confidence

    if hunter_score:
        # Hunter gives its own reliability score — weight it heavily
        score = (hunter_w * 0.50) + (smtp_w * 0.30) + (source_w * 0.20)
    else:
        score = (pattern_confidence * 0.35) + (smtp_w * 0.40) + (source_w * 0.25)

    # Google Workspace catch-all with Hunter's own score: still usable
    # No penalty needed — hunter_score already encodes their confidence

    grade = 'HIGH' if score >= 0.65 else 'MEDIUM' if score >= 0.42 else 'LOW'

    return {
        'confidence_score': round(score, 3),
        'grade': grade,
        'send_recommended': score >= 0.42,
        'components': {
            'smtp_weight':    round(smtp_w, 2),
            'source_weight':  round(source_w, 2),
            'pattern_hunter': round(hunter_w, 2),
        },
    }


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def verify_email(
    email: str,
    source: str = 'inferred',
    hunter_score: int = 0,
    pattern_confidence: float = 0.38,
    skip_smtp: bool = False,
) -> dict:
    """
    Full verification pipeline for a single email address.

    Args:
        email              — the address to verify
        source             — 'hunter' | 'scraper' | 'inferred' | 'cache'
        hunter_score       — 0-100 confidence from Hunter API (0 if not from Hunter)
        pattern_confidence — 0.0-1.0 confidence from pattern_engine (used when no hunter_score)
        skip_smtp          — True to only do format + MX (no SMTP probe)

    Returns:
        {
            'email': str,
            'status': str,               # VerifyStatus constant
            'grade': str,                # 'HIGH' | 'MEDIUM' | 'LOW'
            'confidence_score': float,   # 0.0-1.0
            'send_recommended': bool,
            'mail_provider': str | None, # 'google_workspace' | 'microsoft_365' | etc.
            'is_catch_all': bool,
            'mx_host': str | None,
            'verified_at': float,        # timestamp
        }
    """
    email = email.strip().lower()
    log.info("verify_email: %s (source=%s, hunter_score=%d)", email, source, hunter_score)

    base = {
        'email': email,
        'status': VerifyStatus.UNKNOWN,
        'grade': 'LOW',
        'confidence_score': 0.0,
        'send_recommended': False,
        'mail_provider': None,
        'is_catch_all': False,
        'mx_host': None,
        'verified_at': time.time(),
    }

    # Step 1: Format
    if not check_format(email):
        log.warning("verify_email: bad format %r", email)
        base['status'] = VerifyStatus.BAD_FORMAT
        return base

    domain = email.split('@')[1]

    # Step 2: MX lookup
    mx_records = get_mx_records(domain)
    if not mx_records:
        log.warning("verify_email: no MX records for %s — domain dead", domain)
        base['status'] = VerifyStatus.NO_MX
        return base

    mail_provider = detect_mail_provider(mx_records)
    base['mail_provider'] = mail_provider
    mx_host = mx_records[0][1] if mx_records[0][0] >= 0 else domain
    base['mx_host'] = mx_host

    # Step 3: Known catch-all provider check (skip SMTP — we know the answer)
    smtp_status = VerifyStatus.UNKNOWN
    is_catch_all = False

    if mail_provider in ('google_workspace', 'microsoft_365', 'protonmail') and not skip_smtp:
        log.info("verify_email: %s uses %s — marking catch_all without SMTP probe", domain, mail_provider)
        smtp_status = VerifyStatus.CATCH_ALL
        is_catch_all = True

    elif not skip_smtp:
        # Step 4: SMTP probe
        try:
            smtp_status, rcpt_code, is_catch_all = smtp_verify(email, mx_host, domain)
            log.info("verify_email: SMTP result for %s → %s (code=%d)", email, smtp_status, rcpt_code)
        except Exception as e:
            log.warning("verify_email: SMTP probe exception for %s: %s", email, e)
            smtp_status = VerifyStatus.UNKNOWN
    else:
        smtp_status = VerifyStatus.UNKNOWN

    base['status'] = smtp_status
    base['is_catch_all'] = is_catch_all

    # Step 5: Composite score
    conf = compute_confidence(
        smtp_status=smtp_status,
        pattern_confidence=pattern_confidence,
        source=source,
        hunter_score=hunter_score,
        mail_provider=mail_provider,
    )
    base.update(conf)

    log.info("verify_email: %s → %s grade=%s score=%.2f recommend=%s",
             email, smtp_status, conf['grade'], conf['confidence_score'], conf['send_recommended'])
    return base


def verify_batch(
    emails: list,
    source: str = 'inferred',
    max_per_domain: int = 3,
) -> list:
    """
    Verify a batch of emails with per-domain rate limiting.

    emails: list of dicts with keys: email, hunter_score (opt), pattern_confidence (opt)
    Returns: same list with verification results merged in.
    """
    results = []
    domain_counts: dict = {}

    for item in emails:
        email = item.get('email', '').strip().lower()
        if not email:
            continue

        domain = email.split('@')[1] if '@' in email else ''

        # Per-domain cap: don't SMTP-probe more than max_per_domain from same domain
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        skip_smtp = domain_counts[domain] > max_per_domain

        result = verify_email(
            email=email,
            source=source,
            hunter_score=item.get('hunter_score', 0),
            pattern_confidence=item.get('pattern_confidence', 0.38),
            skip_smtp=skip_smtp,
        )
        # Merge original item fields with verification result
        merged = {**item, **result}
        results.append(merged)

        if not skip_smtp:
            time.sleep(1.5)  # inter-probe delay for same domain

    return results