"""
email_lookup/api_clients/gemini_email_generator.py
Phase 3 — Complete prompt rewrite.

Core fixes:
- System prompt enforces MANDATORY structure (greeting, 3 paragraphs, sign-off)
- Bans generic subjects ("Revolutionizing X", "Optimizing Y")
- Minimum 150 words enforced
- User prompt injects ALL sender context (skills, projects, metrics, GitHub)
- Rough draft is prominently featured — model extracts facts and rewrites
- P.S. only uses real URLs provided by sender, never made-up placeholders
- Provides a concrete example email so model understands the standard required
"""

import json
from typing import Optional

import config
from model_router import generate as model_generate
from utils.logger import get_logger

log = get_logger(__name__)

# ── Purpose definitions ────────────────────────────────────────────────────────

PURPOSE_INTENTS = {
    'job_seeker':        'seeking a founding/early engineer or technical role at this company',
    'startup_founder':   'exploring a strategic collaboration or technical partnership',
    'investor_pitch':    'pitching an investment opportunity to this founder',
    'referral_request':  'requesting a warm introduction or referral to someone in their network',
    'b2b_sales':         'introducing a product or service that solves a specific pain point they have',
    'cold_outreach':     'making a genuine professional connection with this person',
    'partnership':       'proposing a mutually valuable business partnership',
    'interview_prep':    'researching the company ahead of an upcoming interview',
}


# ── System prompt ──────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return """You are a world-class cold email writer. Founders raise millions, engineers land dream roles, and deals close because of emails you write. They work because they feel personal, specific, and real — never like templates.

MANDATORY EMAIL STRUCTURE — follow this EXACTLY, no exceptions:
  Line 1:   Hi [FirstName],
  [blank]
  Para 1:   ONE specific observation about their company/product/recent work. Show you actually researched them. (2 sentences)
  [blank]
  Para 2:   Who you are + ONE specific proof point. Use the ACTUAL skills, projects, metrics, and background provided — not adjectives. (2-3 sentences)
  [blank]
  Para 3:   ONE clear, easy ask — 15-minute call, specific day. (1-2 sentences)
  [blank]
  Best,
  [Sender full name]
  [Title] | [Company]
  [Real LinkedIn URL if provided]
  [Real GitHub/portfolio URL if provided]

RULES — violating any of these makes the email worthless:
1. Body MUST be 150-200 words — not a summary, not bullet points, a complete professional email
2. Subject lines MUST be specific: contain the company name OR a specific technology/project/role — NEVER generic phrases
3. ABSOLUTELY FORBIDDEN in subject lines: "Revolutionizing", "Optimizing", "Transforming", "Leveraging", "Synergy", "Game-changing", "Disruptive", "Innovative", "Solutions"
4. ABSOLUTELY FORBIDDEN anywhere: "I hope this finds you well", "touch base", "circle back", "hop on a call", "reach out", "utilize", "leverage", "synergy", "disruptive"
5. If user provided a rough draft: extract every fact, skill, project, metric, and URL from it — do NOT ignore the draft
6. P.S. line: ONLY include if real GitHub/portfolio/demo URLs were provided. If none, leave ps_line as empty string ""
7. Follow-ups must be complete emails with greeting and sign-off — not 1 fragment sentence
8. Each follow-up must add NEW value: Day 3 = resource/insight, Day 7 = brief bump, Day 14 = graceful close

RESPOND ONLY IN VALID JSON. No markdown fences, no preamble, no text before or after the JSON:
{"subject_lines":["specific s1","specific s2","specific s3"],"body":"Hi Name,\\n\\nPara1...\\n\\nPara2...\\n\\nPara3...\\n\\nBest,\\nSender Name\\nTitle | Company\\nURL","ps_line":"","follow_up_day3":"Hi Name,\\n\\nDay3 content...\\n\\nBest,\\nName","follow_up_day7":"Hi Name,\\n\\nDay7 bump...\\n\\nBest,\\nName","follow_up_day14":"Hi Name,\\n\\nDay14 close...\\n\\nBest,\\nName","tone":"direct","word_count":0}"""


# ── User prompt ────────────────────────────────────────────────────────────────

def _build_user_prompt(
    contact: dict,
    company_intel: dict,
    sender: dict,
    purpose: str,
    is_followup: bool = False,
    previous_email: str = '',
) -> str:
    intent = PURPOSE_INTENTS.get(purpose, purpose)

    first_name  = contact.get('first_name', 'there')
    last_name   = contact.get('last_name', '')
    position    = contact.get('position', 'Founder')
    company_name = company_intel.get('title') or contact.get('domain', 'their company')
    description  = company_intel.get('description', '')
    headlines    = ' | '.join(company_intel.get('headlines', [])[:2])
    tech_hints   = ', '.join(company_intel.get('tech_hints', []))
    linkedin_url = (company_intel.get('social') or {}).get('linkedin', '')

    # Build sender context — inject EVERY field the user provided
    sender_name    = sender.get('name', '[Your Name]')
    sender_title   = sender.get('title', '')
    sender_company = sender.get('company', '')
    sender_li      = sender.get('linkedin', '')
    sender_skills  = sender.get('skills', '') or (sender.get('extra') or {}).get('skills', '')
    sender_projects = sender.get('projects', '') or (sender.get('extra') or {}).get('projects', '')
    sender_metrics  = sender.get('metrics', '') or (sender.get('extra') or {}).get('metrics', '')
    sender_fund     = (sender.get('extra') or {}).get('fund', '')
    sender_portfolio = (sender.get('extra') or {}).get('portfolio', '')
    sender_customers = (sender.get('extra') or {}).get('customers', '')
    sender_subject_hint = sender.get('subject_hint', '')

    sender_lines = [
        f"Full name: {sender_name}",
        f"Title: {sender_title}",
    ]
    if sender_company: sender_lines.append(f"Background: {sender_company}")
    if sender_li:      sender_lines.append(f"LinkedIn: {sender_li}")
    if sender_skills:  sender_lines.append(f"Key skills: {sender_skills}")
    if sender_projects: sender_lines.append(f"GitHub / Portfolio: {sender_projects}")
    if sender_metrics:  sender_lines.append(f"Key results/metrics: {sender_metrics}")
    if sender_fund:     sender_lines.append(f"Fund/Firm: {sender_fund}")
    if sender_portfolio: sender_lines.append(f"Notable portfolio: {sender_portfolio}")
    if sender_customers: sender_lines.append(f"Notable customers: {sender_customers}")
    for k, v in (sender.get('extra') or {}).items():
        if v and k not in ('skills','projects','metrics','fund','portfolio','customers','subject_hint'):
            sender_lines.append(f"{k.replace('_',' ').title()}: {v}")

    # Extract rough draft section
    draft_section = ''
    if previous_email and 'USER\'S ROUGH DRAFT' in previous_email:
        draft_section = previous_email
    elif previous_email and ('ROUGH DRAFT' in previous_email.upper() or 'USER INSTRUCTION' in previous_email):
        draft_section = previous_email
    elif previous_email and not is_followup:
        draft_section = f"\nUSER'S ROUGH DRAFT — extract every fact, skill, project, URL from this and use in the email:\n{previous_email}\n"

    # Concrete example calibrated to this purpose
    if purpose == 'job_seeker':
        example = f"""
EXAMPLE of the quality required (adapt facts for {company_name}):

Hi {first_name},

I've been following {company_name} since [specific thing about their product/mission] — [why that's impressive or relevant]. The problem you're solving around [specific domain] is genuinely hard to get right.

I'm {sender_name or '[Name]'}, {sender_title or '[Title]'} at {sender_company or '[Company]'}. {f'I recently built {sender_projects.split()[0] if sender_projects else "[a relevant project]"} — [what it does and the result it achieved].' if sender_projects else '[Describe a specific project and its measurable result.]'} {f'My stack includes {sender_skills.split(",")[0].strip() if sender_skills else "[relevant tech]"} and [relevant tech #2].' if sender_skills else ''}

Would a 15-minute call this week work? I'd love to hear what the engineering challenges look like right now.

Best,
{sender_name or '[Name]'}
{sender_title or '[Title]'} | {sender_company or '[Company]'}
{sender_projects.split()[0] if sender_projects else ''}"""

    elif purpose == 'investor_pitch':
        example = f"""
EXAMPLE of the quality required:

Hi {first_name},

I noticed {company_name} recently [specific milestone or focus area] — [specific observation about their strategy or market position].

I'm {sender_name or '[Name]'} from {sender_fund or sender_company or '[Fund]'}. {f'We backed {sender_portfolio.split(",")[0].strip() if sender_portfolio else "[notable company]"} early and have been actively looking at [relevant space].' if sender_fund or sender_portfolio else '[Describe your investment background with a specific example.]'} {f'Key metrics that caught my attention: {sender_metrics}.' if sender_metrics else ''}

Would a 15-minute call this week work? Happy to share what we've seen in this space.

Best,
{sender_name or '[Name]'}
{sender_title or 'Investor'} | {sender_fund or sender_company or '[Fund]'}"""

    else:
        example = f"""
EXAMPLE of the quality required:

Hi {first_name},

I came across {company_name} while [specific context] — [specific thing about their work that's impressive or relevant to the sender].

I'm {sender_name or '[Name]'}, {sender_title or '[Title]'} at {sender_company or '[Company]'}. [One specific proof point — project, metric, or result from the sender's background that is directly relevant to the recipient.]

[One clear, easy ask — 15-min call, specific and low-friction.]

Best,
{sender_name or '[Name]'}
{sender_title or '[Title]'} | {sender_company or '[Company]'}"""

    subject_hint_line = f"\nSubject hint from user (build on this): {sender_subject_hint}\n" if sender_subject_hint else ''

    followup_context = ''
    if is_followup and previous_email and 'USER\'S ROUGH DRAFT' not in previous_email:
        followup_context = f"\nPREVIOUS EMAIL SENT (Day 0):\n{previous_email}\nThis is a follow-up sequence — reference the previous email, add new value.\n"

    return f"""Write a complete, professional cold email campaign following your MANDATORY STRUCTURE.

TARGET:
- Name: {first_name} {last_name}
- Role: {position} at {company_name}
- Company description: {description or 'not available — infer from company name'}
- Key headlines/copy: {headlines or 'not available'}
- Tech stack: {tech_hints or 'not available'}
- Company LinkedIn: {linkedin_url or 'not available'}
{subject_hint_line}
SENDER — USE ALL OF THESE DETAILS IN THE EMAIL:
{chr(10).join(sender_lines)}

PURPOSE: {intent}
{draft_section}{followup_context}
REQUIREMENTS:
1. Start body with EXACTLY: "Hi {first_name},"
2. Para 1: Reference something SPECIFIC about {company_name} — their product, what problem they solve, a specific feature or market insight. If you don't have details, make an intelligent inference from the company name and description.
3. Para 2: Use {sender_name}'s REAL background from the sender details above — actual skills, actual projects, actual metrics. NOT "I have experience in" — say WHAT you built and WHAT it achieved.
4. Para 3: Single ask — 15-min call this week. Easy to say yes.
5. Sign-off: {sender_name} / {sender_title} / {sender_company}{' / ' + sender_li if sender_li else ''}{' / ' + sender_projects.split()[0] if sender_projects else ''}
6. Subject lines: must include "{company_name}" or a specific technology/role. Three variants: (a) curiosity/specific, (b) direct value, (c) question. NO generic phrases.
7. P.S.: {'Use this real URL: ' + (sender_projects.split()[0] if sender_projects else sender_li) if (sender_projects or sender_li) else 'Leave ps_line as empty string — no fabricated URLs'}
8. word_count field: count actual words in body
{example}"""


# ── Response parser ────────────────────────────────────────────────────────────

def _parse_sequence(result: dict, contact: dict) -> dict:
    parsed = result.get('parsed_json')
    raw    = result.get('text', '')
    model  = result.get('model_used', 'unknown')
    fname  = contact.get('first_name', 'there')

    if parsed and isinstance(parsed, dict) and parsed.get('body'):
        body = parsed.get('body', raw)
        # Validate body has proper structure — if it doesn't, that's the model's fault but we report it
        has_greeting  = body.strip().startswith('Hi ') or body.strip().startswith('Dear ')
        word_count    = len(body.split())

        log.info("Email generated: model=%s words=%d greeting=%s", model, word_count, has_greeting)

        subjects = parsed.get('subject_lines', [])
        return {
            'success': True,
            'model_used': model,
            'day_0': {
                'subject':          subjects[0] if subjects else 'Following up',
                'subject_variants': subjects,
                'body':             body,
                'ps_line':          parsed.get('ps_line', ''),
                'tone':             parsed.get('tone', 'direct'),
                'word_count':       parsed.get('word_count', word_count),
            },
            'day_3': {
                'subject': f"Re: {subjects[0]}" if subjects else 'Quick follow-up',
                'body':    parsed.get('follow_up_day3', f"Hi {fname},\n\nJust checking if my last note reached you — happy to share more context or adjust the approach.\n\nBest,\n[Name]"),
                'subject_variants': [],
            },
            'day_7': {
                'subject': 'Still relevant?',
                'body':    parsed.get('follow_up_day7', f"Hi {fname},\n\nQuick bump on my previous note — still think this could be valuable for you, but totally understand if the timing is off.\n\nBest,\n[Name]"),
                'subject_variants': [],
            },
            'day_14': {
                'subject': 'Closing the loop',
                'body':    parsed.get('follow_up_day14', f"Hi {fname},\n\nI'll assume the timing isn't right — no worries at all. Feel free to reach out if that changes. Best of luck with everything you're building.\n\nBest,\n[Name]"),
                'subject_variants': [],
            },
            'raw_text': raw,
        }

    # Plain text fallback — model returned text instead of JSON
    log.warning("JSON parse failed — using plain text body. model=%s len=%d", model, len(raw))
    subjects_fallback = [
        f"Quick question for {contact.get('first_name','you')} at {contact.get('domain','')}",
        f"Your work at {contact.get('domain','your company')} + a thought from me",
        f"Worth a 15-min call?",
    ]
    return {
        'success': True,
        'model_used': model,
        'day_0': {
            'subject':          subjects_fallback[0],
            'subject_variants': subjects_fallback,
            'body':             raw or f"Hi {fname},\n\n[Email generation returned plain text — paste your draft here]\n\nBest,\n[Name]",
            'ps_line':          '',
            'tone':             'direct',
            'word_count':       len(raw.split()),
        },
        'day_3':  {'subject': 'Following up',    'body': f"Hi {fname},\n\nJust checking in on my previous note.\n\nBest,\n[Name]", 'subject_variants': []},
        'day_7':  {'subject': 'Quick bump',       'body': f"Hi {fname},\n\nOne last nudge — happy to adjust if the timing or approach isn't right.\n\nBest,\n[Name]", 'subject_variants': []},
        'day_14': {'subject': 'Closing the loop', 'body': f"Hi {fname},\n\nClosing this out — no pressure at all. Hope everything's going well.\n\nBest,\n[Name]", 'subject_variants': []},
        'raw_text': raw,
    }


# ── Main public API ────────────────────────────────────────────────────────────

def generate_email_sequence(
    contact: dict,
    company_intel: dict,
    sender: dict,
    purpose: str = 'job_seeker',
    is_vip: bool = False,
    is_followup: bool = False,
    previous_email: str = '',
) -> dict:
    """
    Generate a complete 4-email outreach sequence.

    The model receives:
      - Full structured system prompt with mandatory format rules + forbidden words
      - Rich user prompt with ALL sender context injected (skills, projects, metrics)
      - Rough draft prominently featured for fact extraction
      - Concrete example calibrated to the purpose

    Returns dict with day_0, day_3, day_7, day_14 — each with body, subject_variants, ps_line.
    """
    fname = f"{contact.get('first_name','')} {contact.get('last_name','')}".strip()
    cname = company_intel.get('title') or contact.get('domain', 'their company')
    log.info("generate_email_sequence: %s @ %s purpose=%s vip=%s", fname, cname, purpose, is_vip)

    if config.DRY_RUN:
        # Rich mock that demonstrates the expected quality
        s_name = sender.get('name', 'Your Name')
        s_title = sender.get('title', 'Engineer')
        s_company = sender.get('company', 'Your Company')
        s_skills = sender.get('skills', '') or (sender.get('extra') or {}).get('skills', 'Python, FastAPI, ML')
        s_projects = sender.get('projects', '') or (sender.get('extra') or {}).get('projects', '')
        first = contact.get('first_name', 'there')
        project_line = f"I recently built {s_projects.split()[0] if s_projects else 'a relevant project'} — happy to share the code and walk you through it." if s_projects else f"I've been building in the {s_skills.split(',')[0].strip() if s_skills else 'ML'} space for the past few years and have shipped systems that directly relate to what you're working on."
        ps = f"P.S. Here's the project: {s_projects.split()[0]}" if s_projects else ''

        return {
            'success': True,
            'model_used': 'dry_run',
            'day_0': {
                'subject': f"Built something for {cname} — want to see?",
                'subject_variants': [
                    f"Built something for {cname} — want to see?",
                    f"{cname} + {s_title.split()[0] if s_title else 'engineer'} who ships fast",
                    f"Quick question about {cname}'s engineering roadmap",
                ],
                'body': f"Hi {first},\n\nI've been following {cname} for a while — the way you're approaching [their core problem] is genuinely different from what I see in the space, and the execution shows.\n\n{project_line} My background is in {(s_skills + ', ').split(',')[0].strip() + ' and ' + (s_skills + ',').split(',')[1].strip() if s_skills and ',' in s_skills else s_skills or 'AI/ML systems'} — at {s_company}, I've been building production systems that handle [relevant scale/problem].\n\nWould a 15-minute call this week work? I'd love to hear what the engineering challenges look like right now and share what I've been building.\n\nBest,\n{s_name}\n{s_title} | {s_company}",
                'ps_line': ps,
                'tone': 'direct',
                'word_count': 130,
            },
            'day_3': {
                'subject': f"Re: Built something for {cname} — want to see?",
                'body': f"Hi {first},\n\nJust wanted to share something relevant — [specific resource or insight about {cname}'s space]. Thought it might be useful given what you're building.\n\nStill happy to connect if the timing works.\n\nBest,\n{s_name}",
                'subject_variants': [],
            },
            'day_7': {
                'subject': 'Still relevant?',
                'body': f"Hi {first},\n\nQuick bump on my earlier note — no pressure if the timing isn't right, just want to make sure it didn't get buried.\n\nBest,\n{s_name}",
                'subject_variants': [],
            },
            'day_14': {
                'subject': 'Closing the loop',
                'body': f"Hi {first},\n\nI'll assume the timing's off — no worries at all. Feel free to reach out whenever it makes sense. Hope {cname} keeps shipping great work.\n\nBest,\n{s_name}",
                'subject_variants': [],
            },
        }

    system_prompt = _build_system_prompt()
    user_prompt   = _build_user_prompt(
        contact, company_intel, sender, purpose, is_followup, previous_email
    )

    result = model_generate(
        task='email_draft_vip' if is_vip else 'email_draft',
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        contact_count=1,
        is_vip=is_vip,
        max_tokens=1400,   # increased — full structured emails need more tokens
        parse_json=True,
    )

    if not result.get('text') and not result.get('parsed_json'):
        log.error("All models failed for %s @ %s", fname, cname)
        return {
            'success': False,
            'model_used': result.get('model_used', 'none'),
            'error': result.get('error', 'All models failed — check API keys in Settings'),
            'day_0': {'subject':'','body':'','subject_variants':[],'ps_line':'','tone':'','word_count':0},
            'day_3': {'subject':'','body':'','subject_variants':[]},
            'day_7': {'subject':'','body':'','subject_variants':[]},
            'day_14': {'subject':'','body':'','subject_variants':[]},
        }

    return _parse_sequence(result, contact)


def generate_subject_variants(
    email_body: str,
    company_name: str,
    contact_name: str,
    n: int = 3,
) -> list:
    """Generate N subject line variants for an existing email body."""
    system = (
        f'Generate exactly {n} cold email subject lines. '
        f'Rules: must include "{company_name}" or a specific technology/role, '
        f'NEVER use: revolutionizing, optimizing, transforming, synergy, game-changing. '
        f'Variants: (1) curiosity+specific, (2) direct value, (3) question format. '
        f'RESPOND ONLY with JSON array: ["s1","s2","s3"]'
    )
    user = (
        f'Email body:\n{email_body[:400]}\n\n'
        f'Recipient: {contact_name} at {company_name}\n'
        f'Generate {n} subject lines. Return ONLY the JSON array.'
    )
    result = model_generate(task='subject lines', system_prompt=system,
                            user_prompt=user, max_tokens=150, parse_json=False)
    try:
        text = (result.get('text') or '').strip()
        if text.startswith('['):
            variants = json.loads(text)
            if isinstance(variants, list) and variants:
                return variants[:n]
    except Exception:
        pass
    return [
        f"Your work at {company_name} — quick thought",
        f"{company_name} + someone who ships fast",
        f"Worth 15 min, {contact_name.split()[0]}?",
    ]