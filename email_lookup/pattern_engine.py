"""
email_lookup/pattern_engine.py
Phase 1 — NEW FILE

Two jobs:
  1. detect_pattern()  — given one known email + name, identify the format template
  2. infer_variants()  — given a name + domain, generate all plausible email candidates

Both are pure Python, zero API calls, zero cost.
Used by lookup_service.py and email_verifier.py.

Pattern syntax: {first} {last} {f}=first_initial {l}=last_initial {domain}
"""

import re
import unicodedata
from typing import Optional
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pattern corpus
# Global frequency table sourced from Hunter.io public pattern statistics.
# Frequencies represent proportion of companies using each format.
# ---------------------------------------------------------------------------

PATTERN_CORPUS = [
    # (format_template, global_frequency, startup_frequency_boost)
    # startup_frequency_boost: YC-stage companies skew toward shorter formats
    ('{first}@{domain}',             0.38, 0.05),   # hello@ pattern common in early startups
    ('{first}.{last}@{domain}',      0.26, 0.00),
    ('{f}{last}@{domain}',           0.12, 0.00),   # jsmith@
    ('{first}{last}@{domain}',       0.08, 0.00),   # johnsmith@
    ('{last}@{domain}',              0.06, 0.00),
    ('{f}.{last}@{domain}',          0.05, 0.00),   # j.smith@
    ('{first}_{last}@{domain}',      0.03, 0.00),
    ('{first}{l}@{domain}',          0.02, 0.00),   # johns@
]

# Roles that are almost always generic inboxes (skip SMTP probing for these)
GENERIC_ROLES = {
    'hello', 'info', 'contact', 'support', 'team', 'press',
    'media', 'jobs', 'careers', 'hr', 'sales', 'admin',
    'help', 'marketing', 'growth', 'partnerships', 'legal',
}


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalise_name(name: str) -> str:
    """
    Normalise a name for email generation:
    - Strip accents (José → jose)
    - Remove apostrophes (O'Brien → obrien)
    - Replace spaces/hyphens with nothing
    - Lowercase

    Keeps the name usable as an email local part.
    """
    if not name:
        return ''
    # Strip accents via unicode normalisation
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
    # Remove chars not safe in email local parts
    clean = re.sub(r"[^a-zA-Z0-9]", '', ascii_only).lower()
    return clean


# ---------------------------------------------------------------------------
# 1. Pattern detection (given one known email sample)
# ---------------------------------------------------------------------------

def detect_pattern(known_email: str, first: str, last: str) -> Optional[str]:
    """
    Given a confirmed email address and the person's name, identify the format.

    Example:
        detect_pattern('john.doe@stripe.com', 'John', 'Doe') → '{first}.{last}'

    Returns None if no known pattern matches.
    Use this on Hunter results to extract the company's email pattern for free,
    then infer other employees' emails without spending more Hunter credits.
    """
    if not known_email or '@' not in known_email:
        return None

    local = known_email.split('@')[0].lower()
    first_n = normalise_name(first)
    last_n = normalise_name(last)

    if not first_n or not last_n:
        return None

    f = first_n[0]
    l = last_n[0]

    # Most specific patterns first — order matters for disambiguation
    candidates = [
        (f'{first_n}.{last_n}', '{first}.{last}'),
        (f'{first_n}_{last_n}', '{first}_{last}'),
        (f'{first_n}{last_n}',  '{first}{last}'),
        (f'{f}.{last_n}',       '{f}.{last}'),
        (f'{f}{last_n}',        '{f}{last}'),
        (f'{first_n}{l}',       '{first}{l}'),
        (f'{first_n}',          '{first}'),
        (f'{last_n}',           '{last}'),
    ]

    for local_form, template in candidates:
        if local == local_form:
            log.debug("detect_pattern: %r → %r", known_email, template)
            return template

    log.debug("detect_pattern: no match for local=%r name=%s %s", local, first_n, last_n)
    return None


# ---------------------------------------------------------------------------
# 2. Variant inference (generate all plausible candidates)
# ---------------------------------------------------------------------------

def infer_variants(
    first: str,
    last: str,
    domain: str,
    known_pattern: Optional[str] = None,
    is_startup: bool = True,
) -> list:
    """
    Generate ranked email candidates for a person.

    Args:
        first         — first name (raw, any case)
        last          — last name (raw, any case)
        domain        — company domain, e.g. 'stripe.com'
        known_pattern — if Hunter already revealed the company pattern,
                        pass it here and that variant gets boosted to rank 1
        is_startup    — boosts shorter formats (firstname@) for YC-stage companies

    Returns:
        List of dicts sorted by confidence descending:
        [
            {
                'email': 'patrick@stripe.com',
                'pattern': '{first}@{domain}',
                'confidence': 0.43,
                'is_known_pattern': True,
                'method': 'pattern_inferred',
            },
            ...
        ]
    """
    first_n = normalise_name(first)
    last_n  = normalise_name(last)

    if not first_n or not last_n:
        log.warning("infer_variants: empty name after normalise (%r, %r)", first, last)
        return []

    f = first_n[0]
    l = last_n[0]
    domain = domain.lower().strip()

    variants = []
    for template, base_freq, startup_boost in PATTERN_CORPUS:
        confidence = base_freq + (startup_boost if is_startup else 0.0)

        # If the company pattern is known, boost that variant to top
        is_known = False
        if known_pattern and template.replace('@{domain}', '') == known_pattern.replace('@{domain}', ''):
            confidence = 1.0
            is_known = True

        email = (template
                 .replace('{first}', first_n)
                 .replace('{last}',  last_n)
                 .replace('{f}',     f)
                 .replace('{l}',     l)
                 .replace('{domain}',domain))

        variants.append({
            'email': email,
            'pattern': template,
            'confidence': round(confidence, 3),
            'is_known_pattern': is_known,
            'method': 'pattern_inferred',
        })

    # Sort: known pattern first, then by frequency
    variants.sort(key=lambda x: (x['is_known_pattern'], x['confidence']), reverse=True)

    log.debug("infer_variants: %s %s @%s → %d candidates", first_n, last_n, domain, len(variants))
    return variants


# ---------------------------------------------------------------------------
# 3. Apply a known pattern to a new name
# ---------------------------------------------------------------------------

def apply_pattern(template: str, first: str, last: str, domain: str) -> Optional[str]:
    """
    Apply a known company pattern to generate a single email guess.

    Example:
        apply_pattern('{first}.{last}', 'Elon', 'Musk', 'x.com') → 'elon.musk@x.com'
    """
    first_n = normalise_name(first)
    last_n  = normalise_name(last)
    if not first_n or not last_n:
        return None

    f = first_n[0]
    l = last_n[0]
    domain = domain.lower().strip()

    # Template may or may not include @{domain}
    full_template = template if '@{domain}' in template else f'{template}@{{domain}}'

    email = (full_template
             .replace('{first}', first_n)
             .replace('{last}',  last_n)
             .replace('{f}',     f)
             .replace('{l}',     l)
             .replace('{domain}',domain))

    return email


# ---------------------------------------------------------------------------
# 4. Generic role detection
# ---------------------------------------------------------------------------

def is_generic_role_email(email: str) -> bool:
    """
    Returns True if the email looks like a team inbox rather than a personal address.
    Generic inboxes: hello@, info@, support@, etc.
    """
    if '@' not in email:
        return False
    local = email.split('@')[0].lower()
    return local in GENERIC_ROLES