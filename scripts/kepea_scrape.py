#!/usr/bin/env python3
"""
Scrape Greek job boards for KEPEA listings and store in Supabase.
Sources are read from kepea_sources table so they can be managed from the UI.
Run daily: 15 08 * * 1-6 cd /opt/jobs/scripts && python3 kepea_scrape.py
"""

import os
import re
import sys
import json
import requests as http
from datetime import datetime, timezone
from urllib.parse import urljoin
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

supabase: Client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
FIRECRAWL_KEY = os.environ['FIRECRAWL_API_KEY']


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_pdf_links(html: str, base_url: str) -> list[str]:
    pdfs = []
    for pat in [
        r'href=["\'](.*?\.pdf[^"\']*)["\']',
        r'src=["\'](.*?\.pdf[^"\']*)["\']',
        r'(https?://[^\s<>"\']+\.pdf)',
    ]:
        for m in re.finditer(pat, html, re.IGNORECASE):
            link = m.group(1)
            if not link.startswith('http'):
                link = urljoin(base_url, link)
            if link not in pdfs:
                pdfs.append(link)
    return pdfs


def extract_dates(content: str) -> dict[str, str]:
    dates: dict[str, str] = {}
    for pat in [
        r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'Ημερομηνία:\s*([Α-Ωα-ω]+\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2})',
    ]:
        matches = re.findall(pat, content)
        if matches:
            if not dates.get('posted_at'):
                dates['posted_at'] = matches[0] if isinstance(matches[0], str) else matches[0][0]
            if len(matches) > 1 and not dates.get('deadline'):
                dates['deadline'] = matches[-1] if isinstance(matches[-1], str) else matches[-1][0]
    return dates


def parse_tables(content: str, html: str, source_url: str, pdf_links: list[str], dates: dict) -> list[dict]:
    """Parse job listings from Firecrawl markdown content."""
    jobs = []

    # DUTH-style: sections with education level and job tables
    section_pat = re.compile(
        r'\*\*([^(]+)\((\d+)\s+θέσεις\)\*\*\s+((?:\|[^\n]+\|\s*\n)+)',
        re.MULTILINE
    )
    for sec in section_pat.finditer(content):
        edu    = sec.group(1).strip()
        table  = sec.group(3)
        row_pat = re.compile(
            r'\|\s*\d+\s*\|\s*([^|]+)\s*\|\s*\n\s*\|\s*---\s*\|\s*---\s*\|\s*\n\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        )
        for row in row_pat.finditer(table):
            title   = re.sub(r'\\[-\[\]]', '', row.group(1)).strip()
            employer = re.sub(r'\\[-\[\]]', '', row.group(2)).strip()
            location = re.sub(r'\\[-\[\]]', '', row.group(3)).strip()
            jobs.append({
                'url':          source_url,
                'title':        title,
                'employer':     employer,
                'positions':    '1',
                'specialty':    edu,
                'location':     location,
                'posted_at':    dates.get('posted_at', datetime.now().strftime('%d/%m/%Y')),
                'deadline':     dates.get('deadline', ''),
                'contract_type':'',
                'requirements': edu,
                'description':  f'{title} – {employer}, {location}',
                'pdf_urls':     pdf_links[:5],
                'source':       _source_name(source_url),
            })

    # Generic: if no DUTH tables found try to extract any job links from markdown
    if not jobs:
        link_pat = re.compile(r'\[([^\]]{5,80})\]\((https?://[^)]+)\)')
        for m in link_pat.finditer(content):
            text, link = m.group(1).strip(), m.group(2).strip()
            # Filter: must look like a job listing (Greek keywords)
            if not re.search(r'θέσ|εργασ|προκήρ|πρόσληψ|θέση', text, re.IGNORECASE):
                continue
            jobs.append({
                'url':          link,
                'title':        text,
                'employer':     '',
                'positions':    '',
                'specialty':    '',
                'location':     '',
                'posted_at':    dates.get('posted_at', ''),
                'deadline':     dates.get('deadline', ''),
                'contract_type':'',
                'requirements': '',
                'description':  '',
                'pdf_urls':     pdf_links[:5],
                'source':       _source_name(source_url),
            })

    return jobs


def _source_name(url: str) -> str:
    if 'duth' in url:
        return 'duth'
    if 'culture' in url:
        return 'culture'
    if 'certh' in url:
        return 'certh'
    return re.sub(r'^www\.', '', url.split('/')[2]).split('.')[0]


def firecrawl_scrape(url: str) -> tuple[str, str]:
    """Returns (markdown, html) or ('', '') on error."""
    try:
        r = http.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers={'Authorization': f'Bearer {FIRECRAWL_KEY}', 'Content-Type': 'application/json'},
            json={'url': url, 'formats': ['markdown', 'html']},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json().get('data', {})
        return data.get('markdown', ''), data.get('html', '')
    except Exception as e:
        print(f'  [firecrawl] ERROR: {e}', file=sys.stderr)
        return '', ''


def scrape_source(source_url: str) -> list[dict]:
    print(f'  Scraping {source_url[:60]}…', end=' ', flush=True)
    content, html = firecrawl_scrape(source_url)
    if not content:
        print('no content')
        return []
    pdf_links = extract_pdf_links(html, source_url)
    dates     = extract_dates(content)
    jobs      = parse_tables(content, html, source_url, pdf_links, dates)
    print(f'{len(jobs)} jobs')
    return jobs


def upsert(job: dict) -> bool:
    url = (job.get('url') or '').strip()
    if not url:
        return False
    existing = supabase.table('kepea_listings').select('id, status').eq('url', url).execute()
    if existing.data:
        # Don't reset status of already-uploaded listings
        if existing.data[0]['status'] == 'uploaded':
            return False
        return False  # already in DB, skip
    job['scraped_at'] = datetime.now(timezone.utc).isoformat()
    job['status']     = 'new'
    supabase.table('kepea_listings').insert(job).execute()
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Load enabled sources from Supabase
    result = supabase.table('kepea_sources').select('url, label').eq('enabled', True).execute()
    sources = result.data or []

    if not sources:
        print('No enabled sources found in kepea_sources table.')
        print(json.dumps({'scraped': 0, 'inserted': 0}))
        return

    total_scraped  = 0
    total_inserted = 0

    for src in sources:
        jobs = scrape_source(src['url'])
        inserted = sum(1 for j in jobs if upsert(j))
        total_scraped  += len(jobs)
        total_inserted += inserted

    summary = {'scraped': total_scraped, 'inserted': total_inserted}
    print(f'\nDone: {total_scraped} scraped, {total_inserted} new inserted')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
