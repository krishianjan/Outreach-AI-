"""
model_router.py
Phase 2 — Multi-model AI router

Classifies tasks and routes to the cheapest model that can do the job well.
Implements a fallback chain: if the primary model is rate-limited (429), 
automatically tries the next model in the chain.

Model assignments:
  gemini_flash  — bulk email drafts, company research, lead scoring
                  Free: 1500 req/day, 15 req/min, ~1M token context
  groq          — subject lines, follow-ups, real-time UI tasks
                  Free: very generous (~14k req/day), sub-500ms
  gemini_pro    — VIP targets only (high-stakes emails, single target)
                  Free: limited (50 req/day)

Usage:
    from model_router import generate, classify_task

    result = generate(
        task='email_draft',
        system_prompt='...',
        user_prompt='...',
        contact_count=1,
        is_vip=False,
    )
    # result: {'text': str, 'model_used': str, 'parsed_json': dict | None}
"""

import json
import os
import time
import re
from typing import Optional

import config
from utils.logger import get_logger
from utils.rate_limiter import gemini_throttle, gemini_budget, groq_throttle

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------

def classify_task(
    task: str,
    contact_count: int = 1,
    is_vip: bool = False,
) -> dict:
    """
    Route a task description to the optimal model.

    Returns:
        {'model': str, 'reason': str, 'task_key': str,
         'fallback_chain': list[str]}
    """
    task_l = task.lower()

    # VIP override — always best model
    if is_vip and ('email' in task_l or 'draft' in task_l):
        return {
            'model': 'gemini_pro',
            'reason': 'VIP single-target — maximum quality',
            'task_key': 'email_draft_vip',
            'fallback_chain': ['gemini_pro', 'gemini_flash', 'groq'],
        }

    # Real-time / high-speed tasks → Groq (short outputs only: subjects, bumps)
    if any(k in task_l for k in ['subject', 'follow-up', 'followup', 'follow up', 'quick', 'bump', 'suggest']):
        return {
            'model': 'groq',
            'reason': 'real-time generation — speed priority',
            'task_key': 'subject_or_followup',
            'fallback_chain': ['groq', 'gemini_flash'],
        }

    # Email drafts → ALWAYS Gemini Flash (128k context, reliable JSON, better body quality)
    # Groq is excluded from email draft fallback chain — it produces empty body fields
    if any(k in task_l for k in ['email', 'draft', 'campaign', 'vip']):
        return {
            'model': 'gemini_flash',
            'reason': 'email draft — Gemini required for reliable JSON body output',
            'task_key': 'email_draft',
            'fallback_chain': ['gemini_flash', 'gemini_pro'],  # Groq excluded intentionally
        }

    # Bulk operations → Flash (cheaper, handles context well)
    if contact_count > 5 or any(k in task_l for k in ['bulk', 'batch', 'all contacts']):
        return {
            'model': 'gemini_flash',
            'reason': f'bulk operation ({contact_count} contacts)',
            'task_key': 'bulk_draft',
            'fallback_chain': ['gemini_flash', 'groq'],
        }

    # Research / scoring → Flash
    if any(k in task_l for k in ['research', 'company', 'intel', 'score', 'analyze', 'analyse']):
        return {
            'model': 'gemini_flash',
            'reason': 'research — structured output, batch-able',
            'task_key': 'company_research',
            'fallback_chain': ['gemini_flash', 'groq'],
        }

    # Default single email → Flash
    return {
        'model': 'gemini_flash',
        'reason': 'default — quality + free tier',
        'task_key': 'email_draft',
        'fallback_chain': ['gemini_flash', 'groq', 'gemini_pro'],
    }


# ---------------------------------------------------------------------------
# JSON response parsing
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> Optional[dict]:
    """
    Extract and parse JSON from model response.
    Handles: clean JSON, ```json fences, partial wrapping.
    Returns None if unparseable — caller decides how to handle.
    """
    if not text:
        return None

    text = text.strip()

    # Strip markdown fences
    if text.startswith('```'):
        lines = text.split('\n')
        inner_lines = lines[1:]
        if inner_lines and inner_lines[-1].strip() in ('```', '```json'):
            inner_lines = inner_lines[:-1]
        text = '\n'.join(inner_lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in surrounding text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse JSON from model response (len=%d)", len(text))
    return None


# ---------------------------------------------------------------------------
# Model clients
# ---------------------------------------------------------------------------

def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    model: str = 'gemini_flash',
    max_tokens: int = 1000,
) -> str:
    """Call Gemini API. Returns raw text. Raises on error."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai")

    model_name = {
        'gemini_flash': config.GEMINI_MODEL_FLASH,
        'gemini_pro':   config.GEMINI_MODEL_PRO,
    }.get(model, config.GEMINI_MODEL_FLASH)

    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set in .env")

    # Throttle + budget check
    gemini_throttle.consume_blocking()
    gemini_budget.spend(1)

    genai.configure(api_key=config.GEMINI_API_KEY)
    client = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
        generation_config={
            'max_output_tokens': max_tokens,
            'temperature': 0.7,
        },
    )

    response = client.generate_content(user_prompt)
    return response.text


def _call_groq(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 800,
) -> str:
    """Call Groq API (OpenAI-compatible). Returns raw text. Raises on error."""
    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError("groq not installed. Run: pip install groq")

    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    groq_throttle.consume_blocking()

    client = Groq(api_key=config.GROQ_API_KEY)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user',   'content': user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return response.choices[0].message.content


def _call_model(model: str, system_prompt: str, user_prompt: str, max_tokens: int = 1000) -> str:
    """Dispatch to correct model client."""
    if model in ('gemini_flash', 'gemini_pro'):
        return _call_gemini(system_prompt, user_prompt, model, max_tokens)
    elif model == 'groq':
        return _call_groq(system_prompt, user_prompt, max_tokens)
    else:
        raise ValueError(f"Unknown model: {model}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate(
    task: str,
    system_prompt: str,
    user_prompt: str,
    contact_count: int = 1,
    is_vip: bool = False,
    max_tokens: int = 1000,
    parse_json: bool = True,
) -> dict:
    """
    Generate text using the optimal model for the task.
    Automatically tries fallback models on rate-limit errors.

    Args:
        task          — description used for model selection
        system_prompt — system/instruction prompt
        user_prompt   — user message
        contact_count — number of targets (affects bulk routing)
        is_vip        — True to force best model
        max_tokens    — max response tokens
        parse_json    — True to attempt JSON parsing of response

    Returns:
        {
            'text': str,                   # raw model output
            'parsed_json': dict | None,    # parsed if parse_json=True
            'model_used': str,             # which model actually responded
            'task_key': str,
            'attempts': int,
        }
    """
    if config.DRY_RUN:
        log.debug("DRY_RUN: skipping real model call for task=%s", task)
        mock = {
            'subject_lines': [
                'Quick question about your product direction',
                'Your recent launch + a thought from me',
                'Built something inspired by what you shipped — 5 min?',
            ],
            'body': (
                'Hi [Name],\n\n'
                'Saw [Company] just shipped [recent feature] — '
                'it solves a problem I ran into building similar systems.\n\n'
                "I'm an AI/ML engineer with 4 years shipping production systems "
                '(Harvard Labs, Microsoft). I rebuilt a lightweight version of your '
                '[core feature] in a weekend — happy to walk you through it.\n\n'
                'Worth a 15-min call this week?\n\nBest,\nKrishi'
            ),
            'ps_line': 'P.S. Live demo: https://demo.krishipatel.dev/[company]-feature',
            'follow_up_day3': 'Hi [Name], sharing a quick resource on [topic] that might be relevant to what you\'re building.',
            'follow_up_day7': 'Hi [Name], just a quick bump — happy to adjust scope or timing.',
            'tone': 'direct',
            'word_count': 95,
        }
        mock_text = json.dumps(mock)
        return {
            'text': mock_text,
            'parsed_json': mock,
            'model_used': 'dry_run',
            'task_key': 'dry_run',
            'attempts': 1,
        }

    routing = classify_task(task, contact_count, is_vip)
    fallback_chain = routing['fallback_chain']
    log.info("generate: task=%r → primary=%s chain=%s", task, routing['model'], fallback_chain)

    last_error = None
    for attempt, model in enumerate(fallback_chain, 1):
        try:
            text = _call_model(model, system_prompt, user_prompt, max_tokens)
            parsed = _parse_json_response(text) if parse_json else None

            log.info("generate: SUCCESS model=%s attempt=%d task=%s", model, attempt, routing['task_key'])
            return {
                'text': text,
                'parsed_json': parsed,
                'model_used': model,
                'task_key': routing['task_key'],
                'attempts': attempt,
            }

        except RuntimeError as e:
            # Missing key / not installed — no point retrying with same model
            last_error = e
            log.warning("generate: model=%s hard error=%s — trying next", model, e)
            continue

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            is_rate_limit = '429' in err_str or 'quota' in err_str or 'exhausted' in err_str
            is_unavailable = '503' in err_str or '502' in err_str or 'unavailable' in err_str

            if is_rate_limit or is_unavailable:
                log.warning("generate: model=%s rate/avail error — trying next. Error: %s", model, e)
                if is_rate_limit:
                    time.sleep(2)  # brief pause before trying next model
                continue
            else:
                # Unexpected error — log and try next
                log.error("generate: model=%s unexpected error: %s", model, e)
                continue

    # All models failed
    log.error("generate: ALL models failed for task=%s. Last error: %s", task, last_error)
    return {
        'text': '',
        'parsed_json': None,
        'model_used': 'none',
        'task_key': routing['task_key'],
        'attempts': len(fallback_chain),
        'error': str(last_error),
    }