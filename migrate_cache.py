"""
migrate_cache.py  — Phase 2+PATCH
One-time migration: email_cache.json -> outreach.db

Patched to handle all real-world cache shapes including flat email dicts.
Safe to re-run (idempotent). Run: python migrate_cache.py
"""

import json, os, sys, time, shutil


def _extract_contacts(value, now: float) -> tuple:
    """
    Return (contacts_raw, pattern, source, cached_at) from any cache shape.

    Shape A: ["email@co.com", ...]
    Shape B: {"contacts":[{value,...}], source, cached_at, pattern}
    Shape C: {"contacts":[...], cached_at}
    Shape D: {"value":"email@co.com", "first_name":...}   <- single flat contact
    Shape E: {"emails": [...]}
    Shape F: {"email": "single@email.com"}
    """
    contacts_raw = []
    pattern   = None
    source    = 'cache'
    cached_at = now

    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and '@' in item:
                contacts_raw.append({'value': item.lower().strip(), 'confidence': 50})
            elif isinstance(item, dict):
                email = (item.get('value') or item.get('email') or '').strip().lower()
                if email and '@' in email:
                    contacts_raw.append({**item, 'value': email})

    elif isinstance(value, dict):
        pattern   = value.get('pattern')
        source    = value.get('source', 'cache')
        cached_at = value.get('cached_at', now)

        # Try list keys: contacts / emails
        raw_list = value.get('contacts') or value.get('emails') or []
        if isinstance(raw_list, list):
            for c in raw_list:
                if isinstance(c, str) and '@' in c:
                    contacts_raw.append({'value': c.lower().strip(), 'confidence': 50})
                elif isinstance(c, dict):
                    email = (c.get('value') or c.get('email') or '').strip().lower()
                    if email and '@' in email:
                        contacts_raw.append({**c, 'value': email})

        # Shape D: dict IS the contact
        if not contacts_raw:
            single = (value.get('value') or value.get('email') or '').strip().lower()
            if single and '@' in single:
                contacts_raw.append({**value, 'value': single})

    return contacts_raw, pattern, source, cached_at


def run_migration(cache_file: str = 'email_cache.json', db_path: str = None):
    import db as _db
    from utils.logger import get_logger
    log = get_logger('migrate_cache')

    if db_path:
        _db.DB_PATH = db_path
    effective_db = db_path or _db.DB_PATH

    if not os.path.exists(cache_file):
        print(f"[migrate] No {cache_file} found — fresh install, nothing to migrate.")
        return {'migrated_domains': 0, 'migrated_contacts': 0, 'skipped': 0}

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[migrate] Cannot read {cache_file}: {e}")
        sys.exit(1)

    if not isinstance(raw, dict):
        print("[migrate] Cache file is not a dict — cannot migrate.")
        return {'migrated_domains': 0, 'migrated_contacts': 0, 'skipped': 0}

    # Keys that are metadata, not company domains — skip silently
    _META_KEYS = {'emails', 'domains', 'contacts', 'metadata', 'version',
                  'updated_at', 'schema', 'cache', 'data', 'results'}

    def _is_valid_domain_key(key: str) -> bool:
        k = key.lower().strip()
        if k in _META_KEYS:
            return False
        if '.' not in k:          # no TLD separator
            return False
        parts = k.split('.')
        if len(parts[-1]) < 2:    # TLD too short
            return False
        return True

    print(f"[migrate] {len(raw)} entries in {cache_file}")
    _db.init_db(effective_db)

    total_domains = total_contacts = skipped = 0
    now = time.time()

    with _db.get_conn(effective_db) as conn:
        for raw_domain, value in raw.items():
            domain = raw_domain.lower().strip().rstrip('/')

            # Skip metadata keys and entries without a valid TLD
            if not _is_valid_domain_key(domain):
                log.debug("Skipping non-domain key: %r", raw_domain)
                skipped += 1
                continue

            if len(domain) < 3:
                skipped += 1
                continue

            contacts_raw, pattern, source, cached_at = _extract_contacts(value, now)

            domain_id = _db.upsert_domain(conn, domain,
                scraped_at=cached_at, source=source, pattern=pattern or '')
            total_domains += 1

            n = 0
            for c in contacts_raw:
                email = c.get('value', '').strip().lower()
                if not email or '@' not in email or len(email) > 254:
                    continue
                try:
                    _db.upsert_contact(conn, domain_id, email,
                        first_name=c.get('first_name', ''),
                        last_name=c.get('last_name', ''),
                        position=c.get('position', ''),
                        email_type=c.get('type', 'personal'),
                        confidence=int(c.get('confidence', 50)),
                        hunter_score=int(c.get('hunter_score', c.get('confidence', 0))),
                        source=c.get('source', source),
                        created_at=cached_at,
                    )
                    n += 1
                    total_contacts += 1
                except Exception as ex:
                    log.debug("Skip %s @ %s: %s", email, domain, ex)

            print(f"  {domain}: {n} contacts")

    # Backup
    bak = cache_file + '.bak'
    if not os.path.exists(bak):
        shutil.copy2(cache_file, bak)
        print(f"\n[migrate] Backed up to {bak}")

    print(f"\n[migrate] COMPLETE — {total_domains} domains, {total_contacts} contacts, {skipped} skipped")
    print(f"  DB: {os.path.abspath(effective_db)}")

    if total_contacts == 0 and total_domains > 0:
        print("\n  WARNING: 0 contacts migrated.")
        print("  To debug, run:")
        print("    python -c \"import json; d=json.load(open('email_cache.json.bak')); print(list(d.items())[:1])\"")
        print("  Paste the output so we can add your cache shape to the parser.")

    log.info("Migration done: %d domains, %d contacts", total_domains, total_contacts)
    return {'migrated_domains': total_domains, 'migrated_contacts': total_contacts, 'skipped': skipped}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Migrate email_cache.json to SQLite')
    p.add_argument('--cache', default='email_cache.json')
    p.add_argument('--db', default=None, help='Override DB path')
    a = p.parse_args()
    run_migration(cache_file=a.cache, db_path=a.db)