#!/usr/bin/env python3
"""
Scrape remote job boards and insert new listings into Supabase.
Run daily: 00 08 * * 1-6 python3 /opt/jobs/scrape.py
"""

import os
import re
import sys
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_SERVICE_ROLE_KEY']
FIRECRAWL_KEY = os.environ.get('FIRECRAWL_API_KEY', '')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Source config ─────────────────────────────────────────────────────────
# enabled: False  → skipped entirely
# cost:    None   → free  |  '$X/mo' → paid subscription required
SOURCES = {
    'remoteok':  {'enabled': True,  'cost': '$17.95/mo'},
    'remotive':  {'enabled': True,  'cost': None},
    'himalayas': {'enabled': True,  'cost': None},
    'wwr':       {'enabled': True,  'cost': None},
    'wellfound': {'enabled': True,  'cost': None,      'needs_firecrawl': True},
    'ycjobs':    {'enabled': True,  'cost': None,      'needs_firecrawl': True},
    'arc':       {'enabled': True,  'cost': None,      'needs_firecrawl': True},
}

# Specific tech keywords — title OR tags must contain at least one
TECH_KEYWORDS = [
    'python', 'fastapi', 'backend', 'llm', 'mlops', 'ml engineer',
    'data engineer', 'analytics engineer', 'agent', 'integration engineer',
    'software engineer', 'backend engineer', 'ai engineer', 'ml ops',
    'machine learning', 'data pipeline', 'devops', 'platform engineer',
]
# Broad keywords only valid in title, not loose context
BROAD_KEYWORDS = ['developer', 'engineer', 'architect']

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; JobCrawler/1.0)'}


def title_matches(title: str) -> bool:
    """Title must contain a specific tech keyword or broad + tech-adjacent word."""
    t = title.lower()
    if any(k in t for k in TECH_KEYWORDS):
        return True
    # broad keyword + tech-adjacent
    if any(k in t for k in BROAD_KEYWORDS):
        return any(w in t for w in ['python', 'data', 'ai', 'ml', 'backend', 'api', 'llm', 'cloud', 'platform'])
    return False


def matches(text: str) -> bool:
    """Used for tags/description — requires specific keyword."""
    t = text.lower()
    return any(k in t for k in TECH_KEYWORDS)


def extract_tags(text: str) -> list[str]:
    t = text.lower()
    all_kw = TECH_KEYWORDS + ['api', 'ai', 'ml', 'docker', 'postgresql', 'react', 'typescript', 'go', 'rust', 'kubernetes']
    return [k for k in all_kw if k in t]


def extract_salary(text: str) -> tuple[int | None, int | None]:
    """Parse salary from free text. Returns (min, max) in USD/year or (None, None)."""
    if not text:
        return None, None
    # Normalise: remove commas, collapse whitespace
    t = re.sub(r',', '', text)
    t = re.sub(r'\s+', ' ', t)

    def to_annual(val: int) -> int:
        """Treat values < 1000 as k-shorthand, < 500 as hourly → annual."""
        if val < 500:   return val * 2080   # hourly → annual
        if val < 1000:  return val * 1000   # e.g. 120 → 120 000
        return val

    # Range patterns: $80k–$120k / $80000–$120000 / 80k-120k / USD 80k
    range_pat = re.compile(
        r'\$?(\d{1,3}(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?(\d{1,3}(?:\.\d+)?)\s*[kK]?'
        r'(?:\s*/?\s*(?:yr|year|annual|pa))?',
        re.IGNORECASE,
    )
    m = range_pat.search(t)
    if m:
        lo = float(m.group(1)); hi = float(m.group(2))
        # detect k suffix in the original match
        snippet = m.group(0).lower()
        if 'k' in snippet:
            if lo < 1000: lo *= 1000
            if hi < 1000: hi *= 1000
        lo, hi = int(to_annual(int(lo))), int(to_annual(int(hi)))
        if 20_000 < lo < 1_000_000:
            return min(lo, hi), max(lo, hi)

    # Single value: $120k / $120,000 / USD 120k
    single_pat = re.compile(
        r'(?:USD|US\$|\$)\s*(\d{1,3}(?:\.\d+)?)\s*[kK]?'
        r'(?:\s*/?\s*(?:yr|year|annual|pa))?',
        re.IGNORECASE,
    )
    m = single_pat.search(t)
    if m:
        val = float(m.group(1))
        snippet = m.group(0).lower()
        if 'k' in snippet and val < 1000:
            val *= 1000
        val = int(to_annual(int(val)))
        if 20_000 < val < 1_000_000:
            return val, None

    return None, None


def is_truly_remote(context: str) -> bool:
    """Return False if context explicitly says 'In office' or 'On-site'."""
    t = context.lower()
    if re.search(r'\bin[\s-]?office\b', t):
        return False
    if re.search(r'\bon[\s-]?site\b', t):
        return False
    if re.search(r'\bno remote\b', t):
        return False
    return True


def upsert(job: dict) -> bool:
    """Insert only if URL not already present. Returns True if new row added."""
    url = (job.get('url') or '').strip()
    if not url:
        return False
    existing = supabase.table('job_listings').select('id').eq('url', url).execute()
    if existing.data:
        return False
    job['scraped_at'] = datetime.now(timezone.utc).isoformat()
    job.setdefault('status', 'new')
    supabase.table('job_listings').insert(job).execute()
    return True


# ── RemoteOK ────────────────────────────────────────────────────────────
def scrape_remoteok() -> list[dict]:
    results = []
    try:
        r = requests.get('https://remoteok.com/api', headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        for item in data[1:]:  # first item is legal metadata
            text = ' '.join([
                item.get('position', ''),
                item.get('title', ''),
                item.get('description', ''),
                *item.get('tags', []),
            ])
            if not matches(text):
                continue
            sal_min = item.get('salary_min')
            sal_max = item.get('salary_max')
            # Fall back to description parsing if no structured salary
            if not sal_min:
                desc = item.get('description', '')
                sal_min, sal_max = extract_salary(desc)
            if sal_min and int(sal_min) < 60_000:
                continue
            results.append({
                'url':        item.get('url') or f"https://remoteok.com/l/{item.get('id')}",
                'title':      item.get('position') or item.get('title') or 'Unknown',
                'company':    item.get('company', 'Unknown'),
                'source':     'remoteok',
                'salary_min': int(sal_min) if sal_min else None,
                'salary_max': int(sal_max) if sal_max else None,
                'tags':       item.get('tags', []),
                'posted_at':  item.get('date'),
            })
    except Exception as e:
        print(f'  [remoteok] ERROR: {e}', file=sys.stderr)
    return results


# ── We Work Remotely (RSS) ───────────────────────────────────────────────
def scrape_wwr() -> list[dict]:
    results = []
    url = 'https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall('.//item'):
            get = lambda tag: (item.find(tag) or type('', (), {'text': ''})()).text or ''
            title   = get('title').strip()
            link    = get('link').strip()
            desc    = get('description')
            pub     = get('pubDate')
            text    = f'{title} {desc}'
            if not matches(text):
                continue
            # WWR title format: "Company: Job Title" or just "Job Title"
            if ': ' in title:
                company, job_title = title.split(': ', 1)
            else:
                company, job_title = 'Unknown', title
            sal_min, sal_max = extract_salary(desc)
            results.append({
                'url':        link,
                'title':      job_title.strip(),
                'company':    company.strip(),
                'source':     'wwr',
                'salary_min': sal_min,
                'salary_max': sal_max,
                'tags':       extract_tags(text),
                'posted_at':  pub or None,
            })
    except Exception as e:
        print(f'  [wwr] ERROR: {e}', file=sys.stderr)
    return results


# ── Firecrawl helper ─────────────────────────────────────────────────────
def firecrawl_get(page_url: str) -> str:
    if not FIRECRAWL_KEY:
        return ''
    try:
        r = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers={'Authorization': f'Bearer {FIRECRAWL_KEY}', 'Content-Type': 'application/json'},
            json={'url': page_url, 'formats': ['markdown']},
            timeout=45,
        )
        r.raise_for_status()
        return r.json().get('data', {}).get('markdown', '')
    except Exception as e:
        print(f'  [firecrawl] ERROR ({page_url}): {e}', file=sys.stderr)
    return ''


# ── Wellfound ────────────────────────────────────────────────────────────
def scrape_wellfound() -> list[dict]:
    results = []
    md = firecrawl_get('https://wellfound.com/jobs?role=backend-engineer&remote=true')
    if not md:
        return results
    pattern = re.compile(r'\[([^\]]+)\]\((https://wellfound\.com/jobs/[^)]+)\)')
    for m in pattern.finditer(md):
        title, link = m.group(1).strip(), m.group(2).strip()
        ctx = md[m.start(): m.start() + 600]  # wider window for salary + remote policy
        if not title_matches(title):
            continue
        if not is_truly_remote(ctx):
            continue
        lines = ctx.split('\n')
        company = next(
            (re.sub(r'[*_#\[\]]', '', l).strip() for l in lines[1:4]
             if l.strip() and len(l.strip()) < 60), 'Unknown'
        )
        sal_min, sal_max = extract_salary(ctx)
        results.append({
            'url': link, 'title': title, 'company': company,
            'source': 'wellfound',
            'salary_min': sal_min, 'salary_max': sal_max,
            'tags': extract_tags(f'{title} {ctx}'),
            'posted_at': None,
        })
    return results


# ── YC Jobs ──────────────────────────────────────────────────────────────
def scrape_ycjobs() -> list[dict]:
    results = []
    md = firecrawl_get('https://www.ycombinator.com/jobs')
    if not md:
        return results
    pattern = re.compile(r'\[([^\]]+)\]\((/companies/[^)]+)\)')
    lines = md.split('\n')
    for i, line in enumerate(lines):
        m = pattern.search(line)
        if not m:
            continue
        title = m.group(1).strip()
        path  = m.group(2)
        ctx   = '\n'.join(lines[max(0, i-2): i+4])
        if not title_matches(title):
            continue
        company = lines[i - 1].lstrip('#').strip() if i > 0 else 'YC Company'
        company = re.sub(r'[*_\[\]]', '', company).strip() or 'YC Company'
        results.append({
            'url': f'https://www.ycombinator.com{path}',
            'title': title, 'company': company,
            'source': 'ycjobs',
            'salary_min': None, 'salary_max': None,
            'tags': extract_tags(f'{title} {ctx}'),
            'posted_at': None,
        })
    return results


# ── Arc.dev ──────────────────────────────────────────────────────────────
def scrape_arc() -> list[dict]:
    results = []
    md = firecrawl_get('https://arc.dev/remote-jobs/fastapi')
    if not md:
        return results
    pattern = re.compile(r'##\s+\[([^\]]+)\]\(([^)]+)\)')
    for m in pattern.finditer(md):
        title, link = m.group(1).strip(), m.group(2).strip()
        ctx = md[m.start(): m.start() + 250]
        if not title_matches(title):
            continue
        ctx_lines = ctx.split('\n')
        company = next(
            (re.sub(r'[*_#\[\]]', '', l).strip() for l in ctx_lines[1:4]
             if l.strip() and len(l.strip()) < 60), 'Unknown'
        )
        results.append({
            'url': link if link.startswith('http') else f'https://arc.dev{link}',
            'title': title, 'company': company,
            'source': 'arc',
            'salary_min': None, 'salary_max': None,
            'tags': extract_tags(f'{title} {ctx}'),
            'posted_at': None,
        })
    return results


# ── Remotive ─────────────────────────────────────────────────────────────
def scrape_remotive() -> list[dict]:
    results = []
    try:
        r = requests.get(
            'https://remotive.com/api/remote-jobs',
            params={'category': 'software-dev', 'limit': 100},
            headers=HEADERS, timeout=15
        )
        r.raise_for_status()
        for job in r.json().get('jobs', []):
            title = job.get('title', '')
            if not title_matches(title):
                continue
            sal_str = job.get('salary', '') or ''
            desc    = job.get('description', '') or ''
            sal_min, sal_max = extract_salary(sal_str) if sal_str else (None, None)
            if sal_min is None:
                sal_min, sal_max = extract_salary(desc)
            if sal_min and sal_min < 60_000:
                continue
            tags = [t.lower() for t in job.get('tags', [])]
            results.append({
                'url':        job.get('url', ''),
                'title':      title,
                'company':    job.get('company_name', 'Unknown'),
                'source':     'remotive',
                'salary_min': sal_min,
                'salary_max': sal_max,
                'tags':       tags or extract_tags(title),
                'posted_at':  job.get('publication_date'),
            })
    except Exception as e:
        print(f'  [remotive] ERROR: {e}', file=sys.stderr)
    return results


# ── Himalayas ─────────────────────────────────────────────────────────────
def scrape_himalayas() -> list[dict]:
    results = []
    try:
        r = requests.get(
            'https://himalayas.app/jobs/api',
            params={'q': 'python backend', 'remote': 'true', 'limit': 50},
            headers=HEADERS, timeout=15
        )
        r.raise_for_status()
        for job in r.json().get('jobs', []):
            title = job.get('title', '')
            if not title_matches(title):
                continue
            results.append({
                'url':        job.get('applicationLink') or job.get('url', ''),
                'title':      title,
                'company':    job.get('companyName', 'Unknown'),
                'source':     'himalayas',
                'salary_min': job.get('salaryMin'),
                'salary_max': job.get('salaryMax'),
                'tags':       extract_tags(title + ' ' + ' '.join(job.get('tags', []))),
                'posted_at':  job.get('createdAt'),
            })
    except Exception as e:
        print(f'  [himalayas] ERROR: {e}', file=sys.stderr)
    return results


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    all_scrapers = [
        ('remoteok',  'RemoteOK',  scrape_remoteok),
        ('remotive',  'Remotive',  scrape_remotive),
        ('himalayas', 'Himalayas', scrape_himalayas),
        ('wwr',       'WWR',       scrape_wwr),
        ('wellfound', 'Wellfound', scrape_wellfound),
        ('ycjobs',    'YC Jobs',   scrape_ycjobs),
        ('arc',       'Arc.dev',   scrape_arc),
    ]

    if not FIRECRAWL_KEY:
        print('FIRECRAWL_API_KEY not set — Wellfound, YC, Arc skipped\n')

    total_scraped = 0
    total_inserted = 0

    for key, name, fn in all_scrapers:
        cfg = SOURCES.get(key, {})
        if not cfg.get('enabled', True):
            cost = cfg.get('cost', '')
            note = cfg.get('note', 'disabled')
            print(f'Skipping {name} — {note}' + (f' ({cost})' if cost else ''))
            continue
        if cfg.get('needs_firecrawl') and not FIRECRAWL_KEY:
            continue
        print(f'Scraping {name}…', end=' ', flush=True)
        jobs = fn()
        inserted = sum(1 for j in jobs if upsert(j))
        total_scraped  += len(jobs)
        total_inserted += inserted
        print(f'{len(jobs)} found, {inserted} new')

    print(f'\nDone: {total_scraped} scraped, {total_inserted} new rows inserted')


if __name__ == '__main__':
    main()
