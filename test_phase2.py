"""
test_phase2.py — Phase 2 verification. Zero API calls. Zero credit spend.
Run: DRY_RUN=true python test_phase2.py
Expected: ALL PHASE 2 CHECKS PASSED
"""

import os, sys, json, time, tempfile, shutil
os.environ['DRY_RUN'] = 'true'
os.environ.setdefault('HUNTER_API_KEY', 'test_key')
os.environ.setdefault('GEMINI_API_KEY', 'test_gemini')

PASS, FAIL = '✓', '✗'
results = []

def check(name, fn):
    try:
        fn()
        results.append((PASS, name))
        print(f'  {PASS} {name}')
    except Exception as e:
        results.append((FAIL, name))
        print(f'  {FAIL} {name}\n      ERROR: {e}')
        import traceback; traceback.print_exc()

print('\n═══ Phase 2 Verification ═══\n')

# -----------------------------------------------------------------------
print('[1/8] DB init + WAL mode')
def test_db_init():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test.db')
    import db as _db
    _db.DB_PATH = db_path
    _db.init_db(db_path)
    conn = _db._make_conn(db_path)
    mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
    assert mode == 'wal', f'Expected WAL, got {mode}'
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {'domains','contacts','leads','email_sequences','api_usage'}
    missing = required - tables
    assert not missing, f'Missing tables: {missing}'
    conn.close()
    shutil.rmtree(tmp)
check('SQLite WAL mode + all 5 tables created', test_db_init)

# -----------------------------------------------------------------------
print('\n[2/8] upsert_domain + upsert_contact idempotency')
def test_upsert():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test.db')
    import db as _db
    _db.DB_PATH = db_path
    _db.init_db(db_path)
    with _db.get_conn(db_path) as conn:
        # Domain upsert
        did1 = _db.upsert_domain(conn, 'stripe.com', source='hunter', pattern='{first}@{domain}')
        did2 = _db.upsert_domain(conn, 'stripe.com', source='hunter')  # re-upsert
        assert did1 == did2, f'Upsert should return same ID: {did1} vs {did2}'
        # Contact upsert
        cid1 = _db.upsert_contact(conn, did1, 'cto@stripe.com', first_name='CTO', confidence=88, created_at=time.time())
        cid2 = _db.upsert_contact(conn, did1, 'cto@stripe.com', confidence=90, created_at=time.time())
        assert cid1 == cid2, f'Contact upsert should return same ID: {cid1} vs {cid2}'
        # Count in DB
        count = conn.execute('SELECT count(*) FROM contacts').fetchone()[0]
        assert count == 1, f'Expected 1 contact, got {count}'
    shutil.rmtree(tmp)
check('upsert_domain + upsert_contact idempotency', test_upsert)

# -----------------------------------------------------------------------
print('\n[3/8] Lead creation + status update')
def test_leads():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test.db')
    import db as _db
    _db.init_db(db_path)
    with _db.get_conn(db_path) as conn:
        lid = _db.create_lead(conn, 'alex@cardinal.ai', 'cardinal.ai', 'job_seeker',
                              first_name='Alex', last_name='Chen', position='CEO')
        assert lid > 0
        _db.update_lead_status(conn, lid, 'drafted')
        row = conn.execute('SELECT status FROM leads WHERE id=?', (lid,)).fetchone()
        assert row['status'] == 'drafted'
        # Sequence save
        sid = _db.save_sequence(conn, lid, 0, 'Test Subject', 'Test body', ['Alt 1','Alt 2'], model_used='gemini_flash')
        assert sid > 0
        sid7 = _db.save_sequence(conn, lid, 7, 'Follow-up', 'Bump body', model_used='groq')
        assert sid7 > 0
        # Due sequences
        rows = _db.get_due_sequences(conn)
        assert len(rows) >= 1
        assert rows[0]['subject'] == 'Test Subject'
    shutil.rmtree(tmp)
check('Lead creation, status update, sequence save, get_due_sequences', test_leads)

# -----------------------------------------------------------------------
print('\n[4/8] Dashboard stats')
def test_stats():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test.db')
    import db as _db
    _db.init_db(db_path)
    with _db.get_conn(db_path) as conn:
        did = _db.upsert_domain(conn, 'notion.so', scraped_at=time.time())
        _db.upsert_contact(conn, did, 'ivan@notion.so', created_at=time.time())
        _db.create_lead(conn, 'ivan@notion.so', 'notion.so')
        _db.log_api_call(conn, 'Hunter', credits=1, domain='notion.so')
        _db.log_api_call(conn, 'Gemini', credits=1)
        stats = _db.get_dashboard_stats(conn)
    required_keys = ['domains_cached','contacts_found','leads_total','emails_sent',
                     'hunter_credits_today','gemini_calls_today']
    for k in required_keys:
        assert k in stats, f'Missing stat: {k}'
    assert stats['domains_cached'] == 1
    assert stats['contacts_found'] == 1
    assert stats['hunter_credits_today'] == 1
    shutil.rmtree(tmp)
check('Dashboard stats: all keys present, values correct', test_stats)

# -----------------------------------------------------------------------
print('\n[5/8] Migration — all 3 cache shapes')
def test_migration():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test.db')
    cache_path = os.path.join(tmp, 'email_cache.json')
    import db as _db
    _db.DB_PATH = db_path
    _db.init_db(db_path)

    mock_cache = {
        'stripe.com': ['cto@stripe.com', 'founder@stripe.com'],           # Shape A
        'notion.so': {                                                       # Shape B
            'contacts': [{'value':'ivan@notion.so','first_name':'Ivan','confidence':88,'source':'hunter'}],
            'source': 'hunter', 'cached_at': time.time(), 'pattern': '{first}@{domain}',
        },
        'cardinal.ai': {                                                     # Shape C
            'contacts': [{'value':'alex@cardinal.ai','confidence':60}],
            'cached_at': time.time(),
        },
        'bad.entry': 'not a list or dict',                                  # invalid — should skip
    }
    with open(cache_path, 'w') as f:
        json.dump(mock_cache, f)

    from migrate_cache import run_migration
    result = run_migration(cache_file=cache_path, db_path=db_path)

    assert result['migrated_domains'] == 3, f"Expected 3 domains, got {result['migrated_domains']}"
    assert result['migrated_contacts'] == 4, f"Expected 4 contacts, got {result['migrated_contacts']}"

    # Idempotency
    result2 = run_migration(cache_file=cache_path, db_path=db_path)
    with _db.get_conn(db_path) as conn:
        count = conn.execute('SELECT count(*) FROM contacts').fetchone()[0]
    assert count == 4, f'Idempotency failed: {count} contacts after second run'

    shutil.rmtree(tmp)
check('Migration: 3 shapes, idempotent, invalid entries skipped', test_migration)

# -----------------------------------------------------------------------
print('\n[6/8] Model router — task classification')
def test_router_classify():
    from model_router import classify_task
    cases = [
        ('email_draft',        1, False, 'gemini_flash'),
        ('email_draft',        1, True,  'gemini_pro'),
        ('bulk email drafts',  20, False,'gemini_flash'),
        ('subject lines',      1, False, 'groq'),
        ('follow-up email',    1, False, 'groq'),
        ('company research',   1, False, 'gemini_flash'),
    ]
    for task, count, vip, expected in cases:
        r = classify_task(task, count, vip)
        assert r['model'] == expected, f'classify_task({task!r}, count={count}, vip={vip}) → {r["model"]}, expected {expected}'
        assert 'fallback_chain' in r
        assert expected in r['fallback_chain']
check('Model router: 6 classification cases + fallback_chain present', test_router_classify)

# -----------------------------------------------------------------------
print('\n[7/8] Model router — DRY_RUN generate()')
def test_router_generate():
    from model_router import generate
    result = generate(
        task='email_draft',
        system_prompt='You are a cold email expert.',
        user_prompt='Write an email to Alex at Cardinal AI.',
        contact_count=1,
        is_vip=False,
    )
    assert result['model_used'] == 'dry_run'
    assert result['parsed_json'] is not None
    pj = result['parsed_json']
    assert 'subject_lines' in pj and len(pj['subject_lines']) == 3
    assert 'body' in pj and len(pj['body']) > 20
    assert 'follow_up_day3' in pj
    assert 'follow_up_day7' in pj
check('model_router.generate(): DRY_RUN returns full sequence JSON', test_router_generate)

# -----------------------------------------------------------------------
print('\n[8/8] Gemini email generator — full sequence output')
def test_email_generator():
    from email_lookup.api_clients.gemini_email_generator import (
        generate_email_sequence, generate_subject_variants
    )
    contact = {
        'value': 'alex@cardinal.ai',
        'first_name': 'Alex', 'last_name': 'Chen',
        'position': 'Co-Founder & CEO', 'domain': 'cardinal.ai',
    }
    intel = {
        'title': 'Cardinal AI', 'description': 'AI-powered B2B lead intelligence',
        'tech_hints': ['Next.js', 'Segment'], 'headlines': ['Close More Deals with AI'],
        'social': {'linkedin': 'https://linkedin.com/company/cardinal-ai'},
    }
    sender = {
        'name': 'Krishi Patel', 'title': 'AI/ML Engineer — 4yr exp',
        'linkedin': 'https://linkedin.com/in/krishipatel',
        'background': 'Harvard Labs, Microsoft, Binghamton MS CS',
    }
    result = generate_email_sequence(contact, intel, sender, purpose='job_seeker')
    assert result['success'] is True
    # Day 0
    d0 = result['day_0']
    assert d0['subject'], 'Day 0 subject empty'
    assert len(d0['subject_variants']) == 3
    assert d0['body'] and len(d0['body']) > 50
    # Day 3, 7, 14
    assert result['day_3']['body'], 'Day 3 body empty'
    assert result['day_7']['body'], 'Day 7 body empty'
    assert result['day_14']['body'], 'Day 14 body empty'
    assert result['model_used'] == 'dry_run'

    # Subject variants
    variants = generate_subject_variants(d0['body'], 'Cardinal AI', 'Alex Chen', n=3)
    assert len(variants) == 3
    assert all(isinstance(v, str) for v in variants)
check('Email generator: full sequence, all days present, subject variants', test_email_generator)

# -----------------------------------------------------------------------
print('\n' + '═' * 42)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)

if failed == 0:
    print(f'\n  ALL {passed} PHASE 2 CHECKS PASSED ✓')
    print('\n  Next steps:')
    print('  1. python migrate_cache.py           — migrate your JSON cache to SQLite')
    print('  2. pip install google-generativeai groq')
    print('  3. Add GEMINI_API_KEY + GROQ_API_KEY to .env')
    print('  4. Set DRY_RUN=false and test one real email generation')
    print('  5. Confirm → Phase 3 (Gradio UI upgrade + HF Spaces deploy)\n')
else:
    print(f'\n  {passed} passed, {failed} FAILED — fix before proceeding\n')
    sys.exit(1)