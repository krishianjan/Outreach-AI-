"""
email_lookup/fallback_scraper.py
Phase 1 — Full rewrite of 3-tier scraping stack

Tier 1: ScrapingGraph AI  — NL query → structured JSON (JS-rendered pages, handles Cloudflare)
Tier 2: httpx + BeautifulSoup — real browser headers, Gaussian delays
Tier 3: Google Cache URL  — last resort for blocked sites

Results normalised to consistent contact dict format. Never raises to caller.

Usage:
    from email_lookup.fallback_scraper import scrape_contacts, scrape_domain_intel
    contacts = scrape_contacts('stripe.com')
"""

import re
import time
import random
from typing import Optional

from utils.logger import get_logger
from utils.retry import retry

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(
    r'(?<![=\'\"\w])([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})(?![.\w])',
    re.IGNORECASE,
)

GENERIC_LOCALS = {
    'hello', 'info', 'contact', 'support', 'team', 'press',
    'media', 'jobs', 'careers', 'admin', 'noreply', 'no-reply',
    'hr', 'sales', 'help', 'marketing', 'legal', 'billing',
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
]

CONTACT_PATHS = [
    '/contact', '/contact-us', '/team', '/about', '/about/team',
    '/people', '/leadership', '/founders', '/company', '/hello',
]

# In-memory intel cache (per session)
_intel_cache: dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'DNT': '1',
    }


def _delay():
    d = max(1.5, min(4.5, random.gauss(3.0, 0.8)))
    time.sleep(d)


@retry(max_attempts=3, base_delay=2.0, max_delay=15.0)
def _fetch_url(url: str) -> Optional[str]:
    try:
        import httpx
    except ImportError:
        log.warning("httpx not installed — run: pip install httpx")
        return None
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=_get_headers()) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.text
            log.debug("Scraper: %s → HTTP %d", url, resp.status_code)
            return None
    except Exception as e:
        log.debug("Scraper: fetch error %s: %s", url, e)
        raise


def _extract_emails_from_html(html: str, domain: str) -> list:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

    found = set()

    # mailto: links
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        if href.lower().startswith('mailto:'):
            email = href[7:].split('?')[0].strip().lower()
            if '@' in email:
                found.add(email)

    # Regex across text
    for match in EMAIL_RE.finditer(soup.get_text(separator=' ')):
        found.add(match.group(0).lower())

    domain_base = domain.split('.')[0].lower()
    contacts = []
    seen = set()

    for email in found:
        if email in seen:
            continue
        seen.add(email)
        parts = email.split('@')
        if len(parts) != 2:
            continue
        local, email_domain = parts
        if len(local) < 2 or len(local) > 64:
            continue
        if local in GENERIC_LOCALS:
            continue
        is_target = domain_base in email_domain
        name_parts = re.split(r'[._\-]', local)
        first = name_parts[0].title() if name_parts else ''
        last  = name_parts[1].title() if len(name_parts) > 1 else ''
        contacts.append({
            'value': email,
            'first_name': first,
            'last_name': last,
            'position': '',
            'type': 'personal' if is_target else 'generic',
            'confidence': 60 if is_target else 30,
            'source': 'scraper',
        })

    contacts.sort(key=lambda c: (0 if c['type'] == 'personal' else 1, len(c['value'])))
    return contacts[:10]


def _extract_domain_intel(html: str, domain: str) -> dict:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        return {}

    title_tag = soup.find('title')
    title = title_tag.get_text(strip=True) if title_tag else ''

    meta_desc = ''
    for meta in soup.find_all('meta'):
        if meta.get('name', '').lower() == 'description' or meta.get('property', '').lower() == 'og:description':
            meta_desc = meta.get('content', '')
            break

    social = {}
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').lower()
        if 'linkedin.com/company' in href:
            social['linkedin'] = a['href']
        elif ('twitter.com/' in href or 'x.com/' in href) and 'intent' not in href:
            social['twitter'] = a['href']
        elif 'github.com/' in href:
            social['github'] = a['href']

    tech_hints = []
    for script in soup.find_all('script', src=True):
        src = script.get('src', '').lower()
        if '_next' in src: tech_hints.append('Next.js')
        elif 'react' in src: tech_hints.append('React')
        elif 'vue' in src: tech_hints.append('Vue.js')
        if 'stripe' in src: tech_hints.append('Stripe')
        if 'segment' in src: tech_hints.append('Segment')
        if 'intercom' in src: tech_hints.append('Intercom')

    headlines = [
        t.get_text(strip=True)
        for t in soup.find_all(['h1', 'h2'])[:4]
        if t.get_text(strip=True) and len(t.get_text(strip=True)) > 5
    ]

    return {
        'title': title,
        'description': meta_desc,
        'headlines': headlines[:3],
        'social': social,
        'tech_hints': list(set(tech_hints)),
    }


# ---------------------------------------------------------------------------
# Tier 1: ScrapingGraph AI
# ---------------------------------------------------------------------------

def _scrape_tier1(domain: str) -> tuple:
    try:
        import config
        if not config.SCRAPEGRAPH_API_KEY:
            return [], {}
        from scrapegraphai.graphs import SmartScraperGraph  # type: ignore

        graph_config = {
            'llm': {'api_key': config.SCRAPEGRAPH_API_KEY, 'model': 'scrapegraph/smart-scraper'},
            'verbose': False,
            'headless': True,
        }
        scraper = SmartScraperGraph(
            prompt=(
                "Find all contact info: email addresses, names, job titles. "
                "Also company description and social links (LinkedIn, GitHub, Twitter). "
                "Return JSON: {contacts:[{name,email,title}], company_description, social_links}"
            ),
            source=f'https://{domain}',
            config=graph_config,
        )
        result = scraper.run()
        if not result or not isinstance(result, dict):
            return [], {}

        contacts = []
        for person in result.get('contacts', []):
            email = person.get('email', '').strip().lower()
            if not email or '@' not in email:
                continue
            name = person.get('name', '')
            name_parts = name.split() if name else []
            contacts.append({
                'value': email,
                'first_name': name_parts[0] if name_parts else '',
                'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                'position': person.get('title', ''),
                'type': 'personal',
                'confidence': 75,
                'source': 'scrapegraph',
            })

        intel = {
            'description': result.get('company_description', ''),
            'social': result.get('social_links', {}),
            'title': '', 'headlines': [], 'tech_hints': [],
        }
        log.info("Tier1 ScrapingGraph: %s → %d contacts", domain, len(contacts))
        return contacts, intel

    except ImportError:
        log.debug("scrapegraphai not installed — skipping tier 1")
        return [], {}
    except Exception as e:
        log.warning("Tier1 ScrapingGraph failed for %s: %s", domain, e)
        return [], {}


# ---------------------------------------------------------------------------
# Tier 2: httpx + BeautifulSoup
# ---------------------------------------------------------------------------

def _scrape_tier2(domain: str) -> tuple:
    contacts = []
    intel = {}

    html = _fetch_url(f'https://{domain}')
    if html:
        intel = _extract_domain_intel(html, domain)
        contacts.extend(_extract_emails_from_html(html, domain))

    if len(contacts) < 3:
        for path in CONTACT_PATHS:
            _delay()
            html = _fetch_url(f'https://{domain}{path}')
            if html:
                for c in _extract_emails_from_html(html, domain):
                    if c['value'] not in {x['value'] for x in contacts}:
                        contacts.append(c)
            if len(contacts) >= 5:
                break

    log.info("Tier2 scraper: %s → %d contacts", domain, len(contacts))
    return contacts, intel


# ---------------------------------------------------------------------------
# Tier 3: Google Cache
# ---------------------------------------------------------------------------

def _scrape_tier3_cache(domain: str) -> tuple:
    url = f'https://webcache.googleusercontent.com/search?q=cache:{domain}'
    html = _fetch_url(url)
    if html:
        contacts = _extract_emails_from_html(html, domain)
        log.info("Tier3 Google cache: %s → %d contacts", domain, len(contacts))
        return contacts, {}
    return [], {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_contacts(domain: str) -> list:
    """
    3-tier scrape. Returns list of contact dicts. Never raises.
    Each dict: {value, first_name, last_name, position, type, confidence, source}
    """
    domain = domain.lower().strip().rstrip('/')
    log.info("scrape_contacts: %s", domain)

    contacts, intel = _scrape_tier1(domain)
    if contacts:
        _intel_cache[domain] = intel
        return contacts

    _delay()
    contacts, intel = _scrape_tier2(domain)
    if contacts:
        _intel_cache[domain] = intel
        return contacts

    _delay()
    contacts, intel = _scrape_tier3_cache(domain)
    if intel:
        _intel_cache[domain] = intel

    if not contacts:
        log.warning("scrape_contacts: all tiers failed for %s", domain)

    return contacts


def scrape_domain_intel(domain: str) -> dict:
    """Fetch company intelligence for email generation context. Cached per session."""
    domain = domain.lower().strip()
    if domain in _intel_cache:
        return _intel_cache[domain]
    html = _fetch_url(f'https://{domain}')
    intel = _extract_domain_intel(html, domain) if html else {}
    _intel_cache[domain] = intel
    return intel