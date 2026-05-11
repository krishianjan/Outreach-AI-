"""
test_phase1.py
Phase 1 verification — run before integrating into main app.

Tests scraping logic, pattern engine, email verifier, and domain intel
without making real network calls or spending API credits.

Run: DRY_RUN=true python test_phase1.py
Expected: ALL PHASE 1 CHECKS PASSED
"""

import os, sys, re, time
os.environ.setdefault('DRY_RUN', 'true')
os.environ.setdefault('HUNTER_API_KEY', 'test_key')
os.environ.setdefault('GEMINI_API_KEY', 'test_gemini')

PASS = '✓'
FAIL = '✗'
results = []

def check(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f'  {PASS} {name}')
    except Exception as e:
        results.append((FAIL, name))
        print(f'  {FAIL} {name}')
        print(f'      ERROR: {e}')
        import traceback; traceback.print_exc()

print('\n═══ Phase 1 Verification ═══\n')

# -----------------------------------------------------------------------
print('[1/7] Pattern engine — detect_pattern')
def test_detect():
    from email_lookup.pattern_engine import detect_pattern
    cases = [
        ('john.doe@co.com', 'John', 'Doe', '{first}.{last}'),
        ('jdoe@co.com', 'John', 'Doe', '{f}{last}'),
        ('john@co.com', 'John', 'Doe', '{first}'),
        ('johnd@co.com', 'John', 'Doe', '{first}{l}'),
        ('doe@co.com', 'John', 'Doe', '{last}'),
        ('j.doe@co.com', 'John', 'Doe', '{f}.{last}'),
        ('unknown123@co.com', 'John', 'Doe', None),
    ]
    for email, first, last, expected in cases:
        got = detect_pattern(email, first, last)
        assert got == expected, f'detect_pattern({email!r}) → {got!r}, expected {expected!r}'
check('detect_pattern: 7 cases', test_detect)

# -----------------------------------------------------------------------
print('\n[2/7] Pattern engine — infer_variants')
def test_infer():
    from email_lookup.pattern_engine import infer_variants
    variants = infer_variants('Patrick', 'Collison', 'stripe.com')
    assert len(variants) == 8
    emails = [v['email'] for v in variants]
    assert 'patrick@stripe.com' in emails
    assert 'patrick.collison@stripe.com' in emails
    assert 'pcollison@stripe.com' in emails
    # All sorted by confidence desc
    confidences = [v['confidence'] for v in variants]
    assert confidences == sorted(confidences, reverse=True)
    # Known pattern boost
    variants_with_known = infer_variants('Patrick', 'Collison', 'stripe.com', known_pattern='{first}.{last}')
    assert variants_with_known[0]['email'] == 'patrick.collison@stripe.com'
    assert variants_with_known[0]['is_known_pattern'] is True
check('infer_variants: count, emails, sorting, known_pattern boost', test_infer)

# -----------------------------------------------------------------------
print('\n[3/7] Pattern engine — normalise_name')
def test_normalise():
    from email_lookup.pattern_engine import normalise_name
    cases = [
        ('José', 'jose'),
        ("O'Brien", 'obrien'),
        ('Jean-Pierre', 'jeanpierre'),
        ('María', 'maria'),
        ('John', 'john'),
        ('', ''),
    ]
    for raw, expected in cases:
        got = normalise_name(raw)
        assert got == expected, f'normalise({raw!r}) → {got!r}'
check('normalise_name: accents, apostrophes, hyphens', test_normalise)

# -----------------------------------------------------------------------
print('\n[4/7] Pattern engine — apply_pattern + is_generic_role_email')
def test_apply():
    from email_lookup.pattern_engine import apply_pattern, is_generic_role_email
    assert apply_pattern('{first}.{last}', 'Elon', 'Musk', 'x.com') == 'elon.musk@x.com'
    assert apply_pattern('{f}{last}', 'Elon', 'Musk', 'x.com') == 'emusk@x.com'
    assert apply_pattern('{first}', 'Elon', 'Musk', 'x.com') == 'elon@x.com'
    assert is_generic_role_email('hello@stripe.com') is True
    assert is_generic_role_email('info@cardinal.ai') is True
    assert is_generic_role_email('patrick@stripe.com') is False
    assert is_generic_role_email('not-an-email') is False
check('apply_pattern + is_generic_role_email', test_apply)

# -----------------------------------------------------------------------
print('\n[5/7] Email verifier — format check')
def test_format():
    from email_lookup.email_verifier import check_format
    assert check_format('test@stripe.com') is True
    assert check_format('user+tag@example.co.uk') is True
    assert check_format('not-an-email') is False
    assert check_format('@nodomain.com') is False
    assert check_format('spaces in@email.com') is False
    assert check_format('a' * 65 + '@toolong.com') is False
check('check_format: valid and invalid cases', test_format)

# -----------------------------------------------------------------------
print('\n[6/7] Email verifier — composite confidence scoring')
def test_confidence():
    from email_lookup.email_verifier import compute_confidence, VerifyStatus
    cases = [
        (VerifyStatus.VALID,     0.38, 'hunter',   92, 'HIGH'),
        (VerifyStatus.CATCH_ALL, 0.38, 'hunter',   85, 'HIGH'),
        (VerifyStatus.CATCH_ALL, 0.38, 'inferred',  0, 'MEDIUM'),
        (VerifyStatus.INVALID,   0.26, 'hunter',    0, 'LOW'),
        (VerifyStatus.BLOCKED,   0.12, 'inferred',  0, 'LOW'),
        (VerifyStatus.VALID,     0.26, 'scraper',   0, 'HIGH'),
    ]
    for smtp, pat, src, h, expected_grade in cases:
        r = compute_confidence(smtp, pat, src, h)
        assert r['grade'] == expected_grade, (
            f'smtp={smtp} src={src} h={h} → got {r["grade"]}, expected {expected_grade} (score={r["confidence_score"]})'
        )
        assert 'send_recommended' in r
        assert 'components' in r
check('compute_confidence: 6 cases all correct grades', test_confidence)

# -----------------------------------------------------------------------
print('\n[7/7] Fallback scraper — HTML extraction (no network)')
def test_scraper_extraction():
    # Import internals directly — no real HTTP calls
    from email_lookup.fallback_scraper import _extract_emails_from_html, _extract_domain_intel

    html = '''<html><head>
      <title>Cardinal AI — Autonomous Sales</title>
      <meta name="description" content="AI-powered lead intelligence for B2B sales.">
      <script src="/_next/static/main.js"></script>
      <script src="https://cdn.segment.com/analytics.js"></script>
    </head><body>
      <a href="mailto:alex@cardinal.ai">Alex (CEO)</a>
      <p>Reach us at jordan@cardinal.ai for partnerships</p>
      <a href="mailto:noreply@cardinal.ai">system</a>
      <p>Generic: info@cardinal.ai</p>
      <img src="https://cdn.cardinal.ai/logo.png">
      <a href="https://linkedin.com/company/cardinal-ai">LinkedIn</a>
      <a href="https://github.com/cardinal-ai">GitHub</a>
    </body></html>'''

    contacts = _extract_emails_from_html(html, 'cardinal.ai')
    emails_found = [c['value'] for c in contacts]

    # Personal emails extracted
    assert 'alex@cardinal.ai' in emails_found, f'Expected alex@ in {emails_found}'
    assert 'jordan@cardinal.ai' in emails_found

    # Generic and noreply filtered
    assert 'noreply@cardinal.ai' not in emails_found
    assert 'info@cardinal.ai' not in emails_found  # filtered as generic role

    # CDN URL not extracted
    assert not any('cdn.cardinal' in e for e in emails_found)

    # Domain intel
    intel = _extract_domain_intel(html, 'cardinal.ai')
    assert intel['title'] == 'Cardinal AI — Autonomous Sales'
    assert 'B2B sales' in intel['description']
    assert 'Next.js' in intel['tech_hints']
    assert 'Segment' in intel['tech_hints']
    assert 'linkedin.com' in intel['social'].get('linkedin', '')
    assert 'github.com' in intel['social'].get('github', '')

check('HTML extraction: emails, intel, filters all correct', test_scraper_extraction)

# -----------------------------------------------------------------------
print('\n' + '═' * 40)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)

if failed == 0:
    print(f'\n  ALL {passed} PHASE 1 CHECKS PASSED ✓')
    print('\n  Install dependencies:')
    print('    pip install httpx dnspython scrapegraphai')
    print('  Then add SCRAPEGRAPH_API_KEY to your .env')
    print('  Ready to move to Phase 2 (SQLite migration + campaign engine)\n')
else:
    print(f'\n  {passed} passed, {failed} FAILED')
    print('  Fix failures before proceeding.\n')
    sys.exit(1)