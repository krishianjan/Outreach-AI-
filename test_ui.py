"""
test_ui.py  — Phase 3 Gradio UI
Tabs: Dashboard | Outreach | Pipeline | Settings
Preserves ALL existing functionality. Adds: budget display, stats, pipeline kanban,
sequence viewer, verify badge, multi-model indicator.
"""

import os
import time
import json

# ── startup ──────────────────────────────────────────────────────────────────
import config
config.validate_config()

from db import init_db, get_conn, get_dashboard_stats, get_contacts_for_domain
from db import create_lead, update_lead_status, save_sequence, log_api_call
from email_lookup.lookup_service import lookup_contacts, get_lookup_stats
from email_lookup.api_clients.gemini_email_generator import (
    generate_email_sequence, generate_subject_variants
)
from email_lookup.email_verifier import verify_email
from email_lookup.pattern_engine import infer_variants, detect_pattern, is_generic_role_email
from utils.logger import get_logger

log = get_logger(__name__)
init_db()

import gradio as gr

# ── UI helpers ────────────────────────────────────────────────────────────────

STATUS_EMOJI = {
    'discovered': '🔍', 'verified': '✅', 'drafted': '📝',
    'sent': '📤', 'opened': '👁', 'replied': '💬',
    'booked': '📅', 'skipped': '⏭',
}
GRADE_COLOR = {'HIGH': '#34d399', 'MEDIUM': '#fbbf24', 'LOW': '#f87171'}
PURPOSE_LABELS = {
    'job_seeker':        '💼 Job Seeker',
    'startup_founder':   '🚀 Startup Outreach',
    'investor_pitch':    '💰 Investor Pitch',
    'referral_request':  '🤝 Referral Request',
    'b2b_sales':         '📈 B2B Sales',
    'cold_outreach':     '📨 Cold Outreach',
    'partnership':       '🔗 Partnership',
    'interview_prep':    '🎯 Interview Prep',
}

# Gradio Dropdown expects (display_label, value) — note the order
PURPOSE_CHOICES = [(label, key) for key, label in PURPOSE_LABELS.items()]


def _stats_html() -> str:
    try:
        with get_conn() as conn:
            s = get_dashboard_stats(conn)
    except Exception:
        s = {}
    hp = min(100, int((s.get('hunter_credits_today', 0) / max(config.HUNTER_DAILY_LIMIT, 1)) * 100))
    gp = min(100, int((s.get('gemini_calls_today', 0) / max(config.GEMINI_DAILY_LIMIT, 1)) * 100))
    reply_rate = s.get('reply_rate', '—')
    mode_badge = (
        '<span style="background:#7c3aed;color:#fff;padding:3px 10px;border-radius:20px;font-size:11px">🔄 DRY RUN</span>'
        if config.DRY_RUN else
        '<span style="background:#065f46;color:#6ee7b7;padding:3px 10px;border-radius:20px;font-size:11px">🟢 LIVE</span>'
    )
    return f"""
<div style="font-family:system-ui,sans-serif;padding:4px 0">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
    <h2 style="margin:0;color:#e2e8f0">📊 Dashboard</h2>{mode_badge}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px">
    {''.join(f'''<div style="background:#1e293b;border-radius:10px;padding:14px;text-align:center;border:1px solid #334155">
      <div style="font-size:26px;font-weight:700;color:{col}">{s.get(key,0)}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">{label}</div>
    </div>''' for key, label, col in [
        ('domains_cached','Domains Cached','#a78bfa'),
        ('contacts_found','Contacts Found','#34d399'),
        ('leads_total','Active Leads','#60a5fa'),
    ])}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px">
    {''.join(f'''<div style="background:#1e293b;border-radius:10px;padding:14px;text-align:center;border:1px solid #334155">
      <div style="font-size:22px;font-weight:700;color:{col}">{s.get(key,'—')}</div>
      <div style="font-size:11px;color:#94a3b8;margin-top:4px">{label}</div>
    </div>''' for key, label, col in [
        ('emails_sent','Emails Sent','#f59e0b'),
        ('emails_replied','Replies','#10b981'),
        ('reply_rate','Reply Rate','#ec4899'),
    ])}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <div style="background:#1e293b;border-radius:10px;padding:14px;border:1px solid #334155">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">
        🎯 Hunter Credits Today &nbsp;<b style="color:#e2e8f0">{s.get('hunter_credits_today',0)}/{config.HUNTER_DAILY_LIMIT}</b>
      </div>
      <div style="background:#374151;border-radius:4px;height:6px">
        <div style="background:#f59e0b;height:6px;border-radius:4px;width:{hp}%;transition:width .3s"></div>
      </div>
    </div>
    <div style="background:#1e293b;border-radius:10px;padding:14px;border:1px solid #334155">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:6px">
        🤖 Gemini Calls Today &nbsp;<b style="color:#e2e8f0">{s.get('gemini_calls_today',0)}/{config.GEMINI_DAILY_LIMIT}</b>
      </div>
      <div style="background:#374151;border-radius:4px;height:6px">
        <div style="background:#34d399;height:6px;border-radius:4px;width:{gp}%;transition:width .3s"></div>
      </div>
    </div>
  </div>
</div>"""


def _contact_card_html(contacts: list, domain: str, lookup_source: str) -> str:
    if not contacts:
        return '<p style="color:#94a3b8;font-style:italic">No contacts found for this domain.</p>'
    src_colors = {'hunter': '#7c3aed', 'scraper': '#0284c7', 'scrapegraph': '#0f766e',
                  'cache': '#374151', 'dry_run': '#92400e'}
    src_color = src_colors.get(lookup_source, '#374151')
    rows = []
    for c in contacts[:8]:
        grade = c.get('verify_grade', '')
        gc = GRADE_COLOR.get(grade, '#64748b')
        name = f"{c.get('first_name','')} {c.get('last_name','')}".strip() or '—'
        rows.append(f"""
<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #1e293b">
  <div style="width:32px;height:32px;border-radius:50%;background:#312e81;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;color:#a78bfa;flex-shrink:0">
    {(c.get('first_name','?')[:1] or '?').upper()}
  </div>
  <div style="flex:1;min-width:0">
    <div style="font-size:13px;font-weight:500;color:#e2e8f0">{name}</div>
    <div style="font-size:11px;color:#94a3b8">{c.get('position','') or 'Unknown role'}</div>
  </div>
  <div style="text-align:right;flex-shrink:0">
    <div style="font-size:12px;color:#a78bfa;font-family:monospace">{c.get('value','')}</div>
    {f'<span style="font-size:10px;padding:2px 6px;border-radius:10px;background:#1e293b;color:{gc}">{grade}</span>' if grade else ''}
  </div>
</div>""")
    return f"""
<div style="font-family:system-ui;background:#0f172a;border-radius:10px;padding:14px;border:1px solid #1e293b">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <span style="font-size:13px;font-weight:600;color:#e2e8f0">Found {len(contacts)} contact{'s' if len(contacts)!=1 else ''} for <code style="color:#a78bfa">{domain}</code></span>
    <span style="font-size:11px;padding:3px 8px;border-radius:10px;background:{src_color};color:#fff">via {lookup_source}</span>
  </div>
  {''.join(rows)}
</div>"""


def _sequence_html(seq: dict) -> str:
    if not seq or not seq.get('success'):
        err = seq.get('error', 'No sequence generated.') if seq else 'Generate an email to see the sequence.'
        return f'<div style="color:#f87171;padding:12px;background:#1e293b;border-radius:8px">⚠️ {err}</div>'

    model = seq.get('model_used', 'unknown')
    model_badge_color = {'gemini_flash': '#166534', 'groq': '#1e3a5f',
                         'gemini_pro': '#4c1d95', 'dry_run': '#44403c'}.get(model, '#1e293b')

    d0 = seq.get('day_0', {})
    subjects = d0.get('subject_variants', [d0.get('subject', '')])
    body = d0.get('body', '')
    ps = d0.get('ps_line', '')

    days_html = ''
    for day in [3, 7, 14]:
        day_data = seq.get(f'day_{day}', {})
        if day_data.get('body'):
            emoji = {3: '📅', 7: '🔔', 14: '🔚'}[day]
            days_html += f"""
<div style="margin-top:12px;padding:12px;background:#1e293b;border-radius:8px;border-left:3px solid #475569">
  <div style="font-size:11px;font-weight:600;color:#94a3b8;margin-bottom:6px">{emoji} DAY {day} FOLLOW-UP</div>
  <div style="font-size:12px;color:#cbd5e1;white-space:pre-wrap">{day_data['body']}</div>
</div>"""

    return f"""
<div style="font-family:system-ui;font-size:13px">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <b style="color:#e2e8f0">✉️ Full Campaign Sequence</b>
    <span style="font-size:11px;padding:3px 8px;border-radius:10px;background:{model_badge_color};color:#fff">🤖 {model}</span>
  </div>
  <div style="background:#1e293b;border-radius:8px;padding:12px;margin-bottom:10px;border-left:3px solid #7c3aed">
    <div style="font-size:11px;font-weight:600;color:#94a3b8;margin-bottom:6px">📨 DAY 0 — PRIMARY EMAIL</div>
    <div style="margin-bottom:8px">
      <div style="font-size:11px;color:#64748b;margin-bottom:4px">SUBJECT VARIANTS</div>
      {''.join(f'<div style="padding:4px 8px;margin:2px 0;background:#0f172a;border-radius:4px;color:#a78bfa;font-size:12px">{i+1}. {s}</div>' for i,s in enumerate(subjects))}
    </div>
    <div style="font-size:11px;color:#64748b;margin-bottom:4px">BODY</div>
    <div style="color:#cbd5e1;white-space:pre-wrap;font-size:12px;line-height:1.6">{body}</div>
    {f'<div style="margin-top:8px;font-size:11px;color:#94a3b8;font-style:italic">{ps}</div>' if ps else ''}
  </div>
  {days_html}
</div>"""


# ── state ─────────────────────────────────────────────────────────────────────

_current_contacts = []   # module-level: current lookup results
_current_sequence = {}   # last generated sequence


# ── handlers ─────────────────────────────────────────────────────────────────

def handle_lookup(domain: str, purpose: str):
    global _current_contacts
    if not domain.strip():
        return (gr.update(), gr.update(choices=[], value=None),
                gr.update(value='Please enter a domain.'))

    from email_lookup.lookup_service import _validate_domain
    _, domain_err = _validate_domain(domain)
    if domain_err:
        return (
            gr.update(value=f'<p style="color:#f87171;padding:12px;background:#1e293b;border-radius:8px">⚠️ {domain_err}</p>'),
            gr.update(choices=[], value=None),
            gr.update(value=domain_err),
        )

    result = lookup_contacts(domain.strip(), purpose)
    contacts = result.get('contacts', [])
    _current_contacts = contacts

    card_html = _contact_card_html(contacts, result.get('domain', domain), result.get('source', 'unknown'))

    choices = []
    for c in contacts:
        name = f"{c.get('first_name','')} {c.get('last_name','')}".strip() or 'Unknown'
        role = c.get('position', '')
        email = c.get('value', c.get('email', ''))
        grade = c.get('verify_grade', '')
        icon = {'HIGH': '🟢', 'MEDIUM': '🟡', 'LOW': '🔴'}.get(grade, '⚪')
        label = f"{icon} {name} — {role} ({email})" if role else f"{icon} {name} ({email})"
        choices.append((label, email))

    if not choices:
        choices = [("No contacts found", "")]

    return (
        gr.update(value=card_html),
        gr.update(choices=choices, value=choices[0][1] if choices else None),
        gr.update(value=result.get('error', '') or ''),
    )


def handle_generate(
    selected_email: str,
    purpose: str,
    sender_name: str,
    sender_title: str,
    sender_company: str,
    sender_phone: str,
    sender_linkedin: str,
    is_followup: bool,
    previous_email: str,
):
    global _current_sequence

    if not selected_email:
        return (gr.update(value='<p style="color:#f87171">Select a contact first.</p>'),
                gr.update(value=''), gr.update(value=''))

    contact = next(
        (c for c in _current_contacts if c.get('value') == selected_email or c.get('email') == selected_email),
        {'value': selected_email, 'first_name': '', 'last_name': '', 'position': ''}
    )

    domain = selected_email.split('@')[1] if '@' in selected_email else ''
    company_intel = {'title': sender_company or domain, 'description': '',
                     'tech_hints': [], 'headlines': [], 'social': {}}

    try:
        from email_lookup.fallback_scraper import scrape_domain_intel
        intel = scrape_domain_intel(domain) if not config.DRY_RUN else {}
        if intel:
            company_intel.update(intel)
    except Exception:
        pass

    sender = {
        'name': sender_name,
        'title': sender_title,
        'linkedin': sender_linkedin,
        'background': f"{sender_company} — {sender_phone}" if sender_company else '',
    }

    seq = generate_email_sequence(
        contact=contact,
        company_intel=company_intel,
        sender=sender,
        purpose=purpose,
        is_followup=is_followup,
        previous_email=previous_email if is_followup else '',
    )
    _current_sequence = seq

    seq_html = _sequence_html(seq)
    d0 = seq.get('day_0', {})
    subject_text = d0.get('subject', '')
    body_text = d0.get('body', '')

    # Save to DB as draft lead
    if seq.get('success') and contact.get('value'):
        try:
            with get_conn() as conn:
                lid = create_lead(conn, contact['value'], domain, purpose,
                                  first_name=contact.get('first_name', ''),
                                  last_name=contact.get('last_name', ''),
                                  position=contact.get('position', ''))
                update_lead_status(conn, lid, 'drafted')
                save_sequence(conn, lid, 0, subject_text, body_text,
                              subject_variants=d0.get('subject_variants', []),
                              model_used=seq.get('model_used', ''))
                for day in [3, 7, 14]:
                    day_data = seq.get(f'day_{day}', {})
                    if day_data.get('body'):
                        save_sequence(conn, lid, day, day_data.get('subject', ''),
                                      day_data['body'], model_used=seq.get('model_used', ''))
                log_api_call(conn, 'Gemini', credits=1, domain=domain,
                             model=seq.get('model_used', ''))
        except Exception as e:
            log.warning("Could not save lead to DB: %s", e)

    return (
        gr.update(value=seq_html),
        gr.update(value=subject_text),
        gr.update(value=body_text),
    )


def handle_refresh_stats():
    return gr.update(value=_stats_html())


def handle_pipeline():
    try:
        with get_conn() as conn:
            rows = conn.execute(
                'SELECT email, domain, status, purpose, first_name, last_name, updated_at FROM leads ORDER BY updated_at DESC LIMIT 50'
            ).fetchall()
        data = []
        for r in rows:
            data.append([
                STATUS_EMOJI.get(r['status'], '?') + ' ' + r['status'].title(),
                r['email'],
                r['domain'],
                PURPOSE_LABELS.get(r['purpose'], r['purpose']),
                f"{r['first_name']} {r['last_name']}".strip() or '—',
                time.strftime('%b %d', time.localtime(r['updated_at'])),
            ])
        return gr.update(value=data if data else [["No leads yet", "", "", "", "", ""]])
    except Exception as e:
        return gr.update(value=[[f"Error: {e}", "", "", "", "", ""]])


def handle_verify(email: str):
    if not email or '@' not in email:
        return '<p style="color:#f87171">Enter a valid email address.</p>'

    contact = next((c for c in _current_contacts if c.get('value') == email), {})
    r = verify_email(
        email=email,
        source=contact.get('source', 'inferred'),
        hunter_score=contact.get('hunter_score', 0),
        pattern_confidence=contact.get('confidence', 50) / 100,
    )
    grade_color = GRADE_COLOR.get(r.get('grade', 'LOW'), '#64748b')
    status_icons = {
        'valid': '✅', 'invalid': '❌', 'catch_all': '⚠️',
        'blocked': '🚫', 'unknown': '❓', 'no_mx': '💀', 'bad_format': '⛔',
    }
    icon = status_icons.get(r.get('status', ''), '❓')
    return f"""
<div style="font-family:system-ui;background:#0f172a;border-radius:10px;padding:16px;border:1px solid #1e293b">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
    <span style="font-size:22px">{icon}</span>
    <div>
      <div style="font-size:14px;font-weight:600;color:#e2e8f0">{email}</div>
      <div style="font-size:12px;color:{grade_color};font-weight:500">{r.get('grade','?')} confidence · {r.get('status','unknown').replace('_',' ').title()}</div>
    </div>
    <div style="margin-left:auto;text-align:right">
      <div style="font-size:22px;font-weight:700;color:{grade_color}">{int(r.get('confidence_score',0)*100)}%</div>
      <div style="font-size:10px;color:#64748b">confidence</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;color:#94a3b8">
    <div>Mail provider: <b style="color:#e2e8f0">{r.get('mail_provider','unknown') or 'unknown'}</b></div>
    <div>Catch-all: <b style="color:#e2e8f0">{'Yes' if r.get('is_catch_all') else 'No'}</b></div>
    <div>MX host: <b style="color:#e2e8f0">{r.get('mx_host','—') or '—'}</b></div>
    <div>Send recommended: <b style="color:{'#34d399' if r.get('send_recommended') else '#f87171'}">{'Yes' if r.get('send_recommended') else 'No'}</b></div>
  </div>
</div>"""


# ── build UI ──────────────────────────────────────────────────────────────────

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.violet,
    secondary_hue=gr.themes.colors.emerald,
    neutral_hue=gr.themes.colors.slate,
    font=gr.themes.GoogleFont("Inter"),
).set(
    body_background_fill="#0a0f1e",
    block_background_fill="#0f172a",
    block_border_color="#1e293b",
    input_background_fill="#1e293b",
    input_border_color="#334155",
    button_primary_background_fill="linear-gradient(90deg,#7c3aed,#4f46e5)",
    button_primary_background_fill_hover="linear-gradient(90deg,#6d28d9,#4338ca)",
    button_primary_text_color="#fff",
)

EXAMPLES = [
    ["cardinal.ai",   "job_seeker"],
    ["notion.so",     "referral_request"],
    ["stripe.com",    "b2b_sales"],
    ["openai.com",    "cold_outreach"],
    ["vercel.com",    "job_seeker"],
]

with gr.Blocks(theme=THEME, title="AI Outreach Platform") as demo:

    gr.HTML("""
<div style="text-align:center;padding:20px 0 8px;font-family:system-ui">
  <h1 style="font-size:28px;font-weight:800;background:linear-gradient(90deg,#a78bfa,#34d399);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0">
    🚀 AI Outreach Platform
  </h1>
  <p style="color:#64748b;margin:6px 0 0;font-size:14px">
    Find contacts · Verify emails · Generate personalised sequences · Track pipeline
  </p>
</div>""")

    with gr.Tabs():

        # ── TAB 1: DASHBOARD ──────────────────────────────────────────────────
        with gr.Tab("📊 Dashboard"):
            stats_display = gr.HTML(value=_stats_html())
            refresh_btn = gr.Button("🔄 Refresh Stats", size="sm", variant="secondary")
            refresh_btn.click(handle_refresh_stats, outputs=stats_display)

            gr.HTML("<hr style='border-color:#1e293b;margin:16px 0'>")
            gr.HTML("<p style='color:#94a3b8;font-size:13px'>💡 <b>Quick start:</b> Go to the Outreach tab, enter a domain, and find contacts in seconds.</p>")

        # ── TAB 2: OUTREACH ───────────────────────────────────────────────────
        with gr.Tab("📨 Outreach"):
            with gr.Row():

                # Left column: discover
                with gr.Column(scale=1):
                    gr.HTML("<p style='font-size:13px;font-weight:600;color:#a78bfa;margin:0 0 8px'>STEP 1 — Find Contacts</p>")

                    domain_input = gr.Textbox(
                        label="Company Domain",
                        placeholder="e.g. cardinal.ai, stripe.com",
                        show_label=True,
                    )
                    purpose_input = gr.Dropdown(
                        choices=PURPOSE_CHOICES,
                        value="job_seeker",
                        label="Outreach Purpose",
                    )
                    find_btn = gr.Button("🔍 Find Contacts", variant="primary", size="lg")

                    contacts_display = gr.HTML(
                        value='<p style="color:#475569;font-style:italic;font-size:13px">Enter a domain above and click Find.</p>'
                    )
                    error_display = gr.Textbox(label="Status / Errors", visible=True, interactive=False, lines=2)

                    gr.HTML("<p style='font-size:12px;color:#64748b;margin:8px 0 4px'>Quick examples:</p>")
                    gr.Examples(
                        examples=EXAMPLES,
                        inputs=[domain_input, purpose_input],
                        label="",
                    )

                # Right column: generate
                with gr.Column(scale=1):
                    gr.HTML("<p style='font-size:13px;font-weight:600;color:#34d399;margin:0 0 8px'>STEP 2 — Generate Email</p>")

                    contact_dropdown = gr.Dropdown(
                        choices=[], label="Select Contact", interactive=True
                    )
                    verify_btn = gr.Button("🛡 Verify Selected Email", size="sm", variant="secondary")
                    verify_display = gr.HTML()

                    with gr.Accordion("👤 Your Details", open=False):
                        sender_name = gr.Textbox(label="Your Name", placeholder="Krishianjan")
                        sender_title = gr.Textbox(label="Your Title", placeholder="AI/ML Engineer")
                        sender_company = gr.Textbox(label="Your Company", placeholder="Harvard Labs / Binghamton")
                        sender_phone = gr.Textbox(label="Phone (optional)")
                        sender_linkedin = gr.Textbox(label="LinkedIn URL")

                    with gr.Accordion("⚙️ Email Options", open=False):
                        is_followup = gr.Checkbox(label="This is a follow-up email")
                        prev_email = gr.Textbox(
                            label="Previous email sent (paste for context)",
                            lines=4, visible=False, placeholder="Paste the email you previously sent..."
                        )
                        is_followup.change(
                            lambda v: gr.update(visible=v),
                            inputs=is_followup, outputs=prev_email
                        )

                    generate_btn = gr.Button("✨ Generate Campaign Sequence", variant="primary", size="lg")

                    subject_out = gr.Textbox(label="Primary Subject Line", interactive=True)
                    body_out = gr.Textbox(label="Email Body (editable)", lines=8, interactive=True)
                    sequence_display = gr.HTML(
                        value='<p style="color:#475569;font-size:13px;font-style:italic">Generate an email to see the full 4-day sequence.</p>'
                    )

            # Wire up
            find_btn.click(
                handle_lookup,
                inputs=[domain_input, purpose_input],
                outputs=[contacts_display, contact_dropdown, error_display],
            )
            verify_btn.click(
                handle_verify,
                inputs=[contact_dropdown],
                outputs=[verify_display],
            )
            generate_btn.click(
                handle_generate,
                inputs=[contact_dropdown, purpose_input,
                        sender_name, sender_title, sender_company,
                        sender_phone, sender_linkedin,
                        is_followup, prev_email],
                outputs=[sequence_display, subject_out, body_out],
            )

        # ── TAB 3: PIPELINE ───────────────────────────────────────────────────
        with gr.Tab("📋 Pipeline"):
            gr.HTML("<p style='font-size:13px;color:#94a3b8;margin-bottom:12px'>All leads generated this session, with their current status.</p>")
            refresh_pipeline_btn = gr.Button("🔄 Refresh Pipeline", size="sm", variant="secondary")
            pipeline_table = gr.Dataframe(
                headers=["Status", "Email", "Domain", "Purpose", "Name", "Updated"],
                datatype=["str", "str", "str", "str", "str", "str"],
                interactive=False,
                wrap=True,
            )
            refresh_pipeline_btn.click(handle_pipeline, outputs=pipeline_table)
            demo.load(handle_pipeline, outputs=pipeline_table)

        # ── TAB 4: SETTINGS ───────────────────────────────────────────────────
        with gr.Tab("⚙️ Settings"):
            gr.HTML(f"""
<div style="font-family:system-ui;font-size:13px">
  <h3 style="color:#e2e8f0">Configuration Status</h3>
  <table style="border-collapse:collapse;width:100%">
    {''.join(f'''<tr>
      <td style="padding:8px 12px;color:#94a3b8;border-bottom:1px solid #1e293b">{name}</td>
      <td style="padding:8px 12px;border-bottom:1px solid #1e293b">
        <span style="color:{'#34d399' if present else '#f87171'};font-weight:600">
          {'✓ Configured' if present else '✗ Not set'}
        </span>
      </td>
    </tr>''' for name, present in [
      ('Hunter API', bool(config.HUNTER_API_KEY)),
      ('Gemini API', bool(config.GEMINI_API_KEY)),
      ('Groq API',   bool(config.GROQ_API_KEY)),
      ('ScrapingGraph API', bool(config.SCRAPEGRAPH_API_KEY)),
      ('Dry Run Mode', config.DRY_RUN),
    ])}
  </table>
  <h3 style="color:#e2e8f0;margin-top:20px">Rate Limits</h3>
  <ul style="color:#94a3b8;line-height:2">
    <li>Hunter: <b style="color:#e2e8f0">{config.HUNTER_DAILY_LIMIT} calls/day</b> (set HUNTER_DAILY_LIMIT in .env)</li>
    <li>Gemini Flash: <b style="color:#e2e8f0">{config.GEMINI_DAILY_LIMIT} calls/day</b></li>
    <li>Groq: very generous free tier (~14k req/day)</li>
    <li>ScrapingGraph: 100 pages/day free tier</li>
  </ul>
  <h3 style="color:#e2e8f0;margin-top:20px">Add to .env to enable features</h3>
  <pre style="background:#1e293b;padding:12px;border-radius:8px;font-size:12px;color:#a78bfa">
HUNTER_API_KEY=your_key
GEMINI_API_KEY=your_key
GROQ_API_KEY=your_key
SCRAPEGRAPH_API_KEY=your_key
HUNTER_DAILY_LIMIT=8
GEMINI_DAILY_LIMIT=200
DRY_RUN=false</pre>
</div>""")


# ── launch ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",   # required for HF Spaces
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        show_error=True,
    )