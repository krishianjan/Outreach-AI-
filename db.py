"""
db.py
Phase 2 — SQLite database layer (WAL mode, thread-safe, full schema)

Single source of truth for all persistent state.
Every Gradio thread gets its own connection — WAL mode allows concurrent reads.

Usage:
    from db import get_conn, init_db

    init_db()                          # call once at app startup
    with get_conn() as conn:
        rows = conn.execute('SELECT * FROM contacts WHERE domain_id=?', (1,)).fetchall()
"""

import sqlite3
import os
import time
from contextlib import contextmanager
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH: str = os.environ.get('DB_PATH', os.path.join(
    os.environ.get('DATA_DIR', '.'),
    'outreach.db'
))
# On Hugging Face Spaces: set DATA_DIR=/data for persistent volume
# Locally: defaults to ./outreach.db


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def _make_conn(path: str = DB_PATH) -> sqlite3.Connection:
    """
    Create a new SQLite connection with all pragmas set.
    Each Gradio thread should call this and use the connection locally.
    Do NOT share connections across threads.
    """
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')        # concurrent reads + writes
    conn.execute('PRAGMA foreign_keys=ON')          # enforce FK constraints
    conn.execute('PRAGMA synchronous=NORMAL')        # safe speed with WAL
    conn.execute('PRAGMA cache_size=-8000')          # 8MB page cache
    conn.execute('PRAGMA temp_store=MEMORY')         # temp tables in RAM
    return conn


@contextmanager
def get_conn(path: str = DB_PATH):
    """
    Context manager: get a connection, auto-commit on exit, auto-close.

    Usage:
        with get_conn() as conn:
            conn.execute('INSERT ...')
            # auto-committed and closed
    """
    conn = _make_conn(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
-- Domain cache with enriched metadata
CREATE TABLE IF NOT EXISTS domains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT    UNIQUE NOT NULL,
    org_name        TEXT    DEFAULT '',
    mx_valid        INTEGER DEFAULT 0,
    mail_provider   TEXT    DEFAULT '',
    is_catch_all    INTEGER DEFAULT 0,
    pattern         TEXT    DEFAULT '',
    title           TEXT    DEFAULT '',
    description     TEXT    DEFAULT '',
    linkedin_url    TEXT    DEFAULT '',
    github_url      TEXT    DEFAULT '',
    twitter_url     TEXT    DEFAULT '',
    tech_hints      TEXT    DEFAULT '[]',
    scraped_at      REAL    NOT NULL DEFAULT 0,
    cache_ttl_hours INTEGER DEFAULT 48,
    source          TEXT    DEFAULT 'unknown',
    CONSTRAINT domain_min_len CHECK(length(domain) >= 3)
);

-- Individual contacts found for each domain
CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id       INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    email           TEXT    NOT NULL,
    first_name      TEXT    DEFAULT '',
    last_name       TEXT    DEFAULT '',
    position        TEXT    DEFAULT '',
    email_type      TEXT    DEFAULT 'personal',
    confidence      INTEGER DEFAULT 0,
    hunter_score    INTEGER DEFAULT 0,
    verify_status   TEXT    DEFAULT 'unknown',
    verify_grade    TEXT    DEFAULT 'LOW',
    verify_score    REAL    DEFAULT 0.0,
    is_catch_all    INTEGER DEFAULT 0,
    send_recommended INTEGER DEFAULT 0,
    source          TEXT    DEFAULT 'unknown',
    created_at      REAL    NOT NULL,
    verified_at     REAL    DEFAULT 0,
    UNIQUE(domain_id, email)
);

-- Outreach leads (one row per target person + purpose)
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    domain      TEXT    NOT NULL,
    email       TEXT    NOT NULL,
    first_name  TEXT    DEFAULT '',
    last_name   TEXT    DEFAULT '',
    position    TEXT    DEFAULT '',
    purpose     TEXT    DEFAULT 'job_seeker',
    status      TEXT    DEFAULT 'discovered',
    notes       TEXT    DEFAULT '',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL,
    CONSTRAINT valid_status CHECK(status IN (
        'discovered','verified','drafted','sent',
        'opened','replied','booked','skipped'
    ))
);

-- Email sequences (D0, D3, D7, D14 per lead)
CREATE TABLE IF NOT EXISTS email_sequences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    sequence_day    INTEGER NOT NULL DEFAULT 0,
    subject         TEXT    NOT NULL DEFAULT '',
    body            TEXT    NOT NULL DEFAULT '',
    subject_variants TEXT   DEFAULT '[]',
    send_at         REAL    DEFAULT 0,
    sent_at         REAL    DEFAULT 0,
    opened_at       REAL    DEFAULT 0,
    replied_at      REAL    DEFAULT 0,
    status          TEXT    DEFAULT 'pending',
    model_used      TEXT    DEFAULT '',
    CONSTRAINT valid_day CHECK(sequence_day IN (0, 3, 7, 14)),
    UNIQUE(lead_id, sequence_day)
);

-- API credit usage log
CREATE TABLE IF NOT EXISTS api_usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    api_name     TEXT    NOT NULL,
    endpoint     TEXT    DEFAULT '',
    credits_used INTEGER DEFAULT 1,
    domain       TEXT    DEFAULT '',
    success      INTEGER DEFAULT 1,
    error_msg    TEXT    DEFAULT '',
    model        TEXT    DEFAULT '',
    ts           REAL    NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contacts_email      ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_domain_id  ON contacts(domain_id);
CREATE INDEX IF NOT EXISTS idx_leads_status        ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_domain        ON leads(domain);
CREATE INDEX IF NOT EXISTS idx_leads_email         ON leads(email);
CREATE INDEX IF NOT EXISTS idx_seq_lead_day        ON email_sequences(lead_id, sequence_day);
CREATE INDEX IF NOT EXISTS idx_seq_status          ON email_sequences(status, send_at);
CREATE INDEX IF NOT EXISTS idx_api_usage_ts        ON api_usage(ts);
CREATE INDEX IF NOT EXISTS idx_api_usage_name      ON api_usage(api_name, ts);
"""


def init_db(path: str = DB_PATH) -> None:
    """
    Create all tables and indexes if they don't exist.
    Safe to call on every app startup — idempotent.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = _make_conn(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        log.info("DB initialised at %s", path)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def upsert_domain(conn, domain: str, **kwargs) -> int:
    """
    Insert or update a domain row. Returns domain_id.
    kwargs: any column in the domains table.
    """
    now = time.time()
    existing = conn.execute('SELECT id FROM domains WHERE domain=?', (domain,)).fetchone()

    if existing:
        if kwargs:
            sets = ', '.join(f'{k}=?' for k in kwargs)
            vals = list(kwargs.values()) + [domain]
            conn.execute(f'UPDATE domains SET {sets} WHERE domain=?', vals)
        return existing['id']
    else:
        kwargs.setdefault('scraped_at', now)
        cols = ['domain'] + list(kwargs.keys())
        placeholders = ', '.join('?' * len(cols))
        vals = [domain] + list(kwargs.values())
        cursor = conn.execute(
            f'INSERT OR IGNORE INTO domains ({", ".join(cols)}) VALUES ({placeholders})',
            vals
        )
        return cursor.lastrowid or conn.execute('SELECT id FROM domains WHERE domain=?', (domain,)).fetchone()['id']


def upsert_contact(conn, domain_id: int, email: str, **kwargs) -> int:
    """
    Insert or update a contact row. Returns contact_id.
    """
    now = time.time()
    kwargs.setdefault('created_at', now)
    existing = conn.execute(
        'SELECT id FROM contacts WHERE domain_id=? AND email=?', (domain_id, email)
    ).fetchone()

    if existing:
        if kwargs:
            sets = ', '.join(f'{k}=?' for k in kwargs if k != 'created_at')
            update_vals = [v for k, v in kwargs.items() if k != 'created_at'] + [existing['id']]
            if sets:
                conn.execute(f'UPDATE contacts SET {sets} WHERE id=?', update_vals)
        return existing['id']
    else:
        cols = ['domain_id', 'email'] + list(kwargs.keys())
        placeholders = ', '.join('?' * len(cols))
        vals = [domain_id, email] + list(kwargs.values())
        cursor = conn.execute(
            f'INSERT OR IGNORE INTO contacts ({", ".join(cols)}) VALUES ({placeholders})',
            vals
        )
        return cursor.lastrowid or conn.execute(
            'SELECT id FROM contacts WHERE domain_id=? AND email=?', (domain_id, email)
        ).fetchone()['id']


# ---------------------------------------------------------------------------
# Lead helpers
# ---------------------------------------------------------------------------

def create_lead(conn, email: str, domain: str, purpose: str = 'job_seeker', **kwargs) -> int:
    """Create a new lead. Returns lead_id."""
    now = time.time()
    cursor = conn.execute(
        '''INSERT OR IGNORE INTO leads
           (email, domain, purpose, status, created_at, updated_at,
            first_name, last_name, position)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (email, domain, purpose, 'discovered', now, now,
         kwargs.get('first_name', ''), kwargs.get('last_name', ''), kwargs.get('position', ''))
    )
    if cursor.lastrowid:
        return cursor.lastrowid
    return conn.execute('SELECT id FROM leads WHERE email=? AND domain=? AND purpose=?',
                        (email, domain, purpose)).fetchone()['id']


def update_lead_status(conn, lead_id: int, status: str) -> None:
    conn.execute('UPDATE leads SET status=?, updated_at=? WHERE id=?',
                 (status, time.time(), lead_id))


def save_sequence(conn, lead_id: int, day: int, subject: str, body: str,
                  subject_variants: list = None, model_used: str = '') -> int:
    """Save an email sequence entry. Returns sequence_id."""
    import json as _json
    send_at = time.time() + (day * 86400)
    cursor = conn.execute(
        '''INSERT OR REPLACE INTO email_sequences
           (lead_id, sequence_day, subject, body, subject_variants, send_at, status, model_used)
           VALUES (?,?,?,?,?,?,?,?)''',
        (lead_id, day, subject, body,
         _json.dumps(subject_variants or []), send_at, 'pending', model_used)
    )
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_contacts_for_domain(conn, domain: str) -> list:
    """Return all contacts for a domain as list of dicts."""
    rows = conn.execute(
        '''SELECT c.* FROM contacts c
           JOIN domains d ON c.domain_id = d.id
           WHERE d.domain = ?
           ORDER BY c.confidence DESC''',
        (domain,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_domain_cache(conn, domain: str, ttl_hours: int = 48) -> dict | None:
    """
    Return cached domain row if fresh, else None.
    Replaces vector_storage.get_emails() for the SQLite era.
    """
    row = conn.execute('SELECT * FROM domains WHERE domain=?', (domain,)).fetchone()
    if not row:
        return None
    age_hours = (time.time() - row['scraped_at']) / 3600
    if age_hours > (row['cache_ttl_hours'] or ttl_hours):
        return None
    return dict(row)


def get_due_sequences(conn) -> list:
    """Return sequences due to send (send_at <= now, status=pending)."""
    rows = conn.execute(
        '''SELECT s.*, l.email, l.first_name, l.domain, l.purpose
           FROM email_sequences s
           JOIN leads l ON s.lead_id = l.id
           WHERE s.status = 'pending' AND s.send_at <= ?
           ORDER BY s.send_at ASC''',
        (time.time(),)
    ).fetchall()
    return [dict(r) for r in rows]


def log_api_call(conn, api_name: str, success: bool = True,
                 credits: int = 1, domain: str = '', endpoint: str = '',
                 error: str = '', model: str = '') -> None:
    conn.execute(
        '''INSERT INTO api_usage (api_name, endpoint, credits_used, domain, success, error_msg, model, ts)
           VALUES (?,?,?,?,?,?,?,?)''',
        (api_name, endpoint, credits, domain, int(success), error, model, time.time())
    )


def get_dashboard_stats(conn) -> dict:
    """Return summary stats for UI dashboard."""
    domains_total   = conn.execute('SELECT count(*) FROM domains').fetchone()[0]
    contacts_total  = conn.execute('SELECT count(*) FROM contacts').fetchone()[0]
    leads_total     = conn.execute('SELECT count(*) FROM leads').fetchone()[0]
    emails_sent     = conn.execute("SELECT count(*) FROM leads WHERE status='sent'").fetchone()[0]
    emails_replied  = conn.execute("SELECT count(*) FROM leads WHERE status='replied'").fetchone()[0]
    hunter_today    = conn.execute(
        "SELECT COALESCE(sum(credits_used),0) FROM api_usage WHERE api_name='Hunter' AND ts > ?",
        (time.time() - 86400,)
    ).fetchone()[0]
    gemini_today    = conn.execute(
        "SELECT count(*) FROM api_usage WHERE api_name='Gemini' AND ts > ?",
        (time.time() - 86400,)
    ).fetchone()[0]

    return {
        'domains_cached':  domains_total,
        'contacts_found':  contacts_total,
        'leads_total':     leads_total,
        'emails_sent':     emails_sent,
        'emails_replied':  emails_replied,
        'reply_rate':      f'{(emails_replied / emails_sent * 100):.1f}%' if emails_sent else '—',
        'hunter_credits_today': hunter_today,
        'gemini_calls_today':   gemini_today,
    }