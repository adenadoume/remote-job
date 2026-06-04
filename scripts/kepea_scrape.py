#!/usr/bin/env python3
"""
Scrape Greek job boards for KEPEA listings and store in Supabase.

Scraping strategy:
  1. Fetch each list page → parse 2-col table (deadline | title+link)
  2. For each NEW job (not already in DB) → scrape individual job page
     for full details: description, dates, contract type, location, PDF link
  3. Upsert to kepea_listings

Run daily: 15 08 * * 1-6 cd /opt/jobs/scripts && python3 kepea_scrape.py
"""

import os
import re
import sys
import json
import time
import requests as http
from datetime import datetime, timezone
from urllib.parse import urljoin
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

supabase: Client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
FIRECRAWL_KEY = os.environ['FIRECRAWL_API_KEY']


# ── Firecrawl HTTP wrapper ────────────────────────────────────────────────────

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
        print(f'  [firecrawl] ERROR {url[:60]}: {e}', file=sys.stderr)
        return '', ''


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


def _clean(s: str) -> str:
    """Remove markdown escape characters and strip."""
    return re.sub(r'\\([-\[\]|])', r'\1', s).strip()


def _source_name(url: str) -> str:
    if 'duth' in url:
        return 'duth'
    if 'culture' in url:
        return 'culture'
    if 'certh' in url:
        return 'certh'
    return re.sub(r'^www\.', '', url.split('/')[2]).split('.')[0]


def _contract_type_from_title(title: str) -> str:
    t = title.lower()
    if 'ορισμένου χρόνου' in t or 'σοχ' in t:
        return 'Ορισμένου Χρόνου'
    if 'μίσθωσης έργου' in t or 'σμε' in t:
        return 'Μίσθωσης Έργου'
    if 'αορίστου χρόνου' in t:
        return 'Αορίστου Χρόνου'
    if 'μετατάξ' in t:
        return 'Μετάταξη'
    return ''


def _positions_from_title(title: str) -> str:
    m = re.match(r'^(\d+)\s+', title.strip())
    return m.group(1) if m else '1'


def _employer_from_title(title: str) -> str:
    """Extract employer from Greek title patterns like 'Θέση στο/στην Δήμο X'."""
    m = re.search(r'\bστ[οα-ωά-ώ]*\s+(.+?)(?:\s*$)', title, re.IGNORECASE)
    if m:
        return _clean(m.group(1))
    return ''


# ── List page parser ──────────────────────────────────────────────────────────

def parse_duth_list(content: str, source_url: str) -> list[dict]:
    """
    Parse the DUTH 2-column table:
      | Καταληκτική Ημερομηνία | Τίτλος |
      | dd/mm/yyyy              | [title](url) |
    """
    jobs = []
    # Match table rows: | date | [title](url) |
    row_pat = re.compile(
        r'\|\s*(\d{1,2}/\d{1,2}/\d{4})\s*\|\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*\|'
    )
    for m in row_pat.finditer(content):
        deadline  = m.group(1).strip()
        title     = _clean(m.group(2))
        job_url   = m.group(3).strip()

        jobs.append({
            'url':           job_url,
            'title':         title,
            'employer':      _employer_from_title(title),
            'positions':     _positions_from_title(title),
            'specialty':     '',
            'location':      '',
            'posted_at':     '',
            'deadline':      deadline,
            'contract_type': _contract_type_from_title(title),
            'requirements':  '',
            'description':   '',
            'pdf_urls':      [],
            'source':        _source_name(source_url),
        })
    return jobs


def parse_generic(content: str, html: str, source_url: str) -> list[dict]:
    """Fallback: extract job-like markdown links for non-DUTH pages."""
    jobs = []
    pdf_links = extract_pdf_links(html, source_url)

    link_pat = re.compile(r'\[([^\]]{5,120})\]\((https?://[^)]+)\)')
    for m in link_pat.finditer(content):
        text, link = m.group(1).strip(), m.group(2).strip()
        if not re.search(r'θέσ|εργασ|προκήρ|πρόσληψ|θέση|πρόσκληση', text, re.IGNORECASE):
            continue
        jobs.append({
            'url':           link,
            'title':         _clean(text),
            'employer':      '',
            'positions':     _positions_from_title(text),
            'specialty':     '',
            'location':      '',
            'posted_at':     '',
            'deadline':      '',
            'contract_type': _contract_type_from_title(text),
            'requirements':  '',
            'description':   '',
            'pdf_urls':      pdf_links[:3],
            'source':        _source_name(source_url),
        })
    return jobs


# ── Individual job page detail scraper ───────────────────────────────────────

def scrape_job_details(job_url: str) -> dict:
    """
    Scrape individual DUTH job page and extract all available fields.
    Returns a dict of fields to merge into the job record.
    """
    content, html = firecrawl_scrape(job_url)
    if not content:
        return {}

    details: dict = {}

    # Publication date: "Ημερομηνία:\n\nΜάιος 25, 2026 15:08"
    m = re.search(r'Ημερομηνία:\s*\n+([Α-Ωα-ω\w]+\s+\d{1,2},\s+\d{4})', content)
    if m:
        details['posted_at'] = m.group(1).strip()

    # Application period: "26/05/2026 - 04/06/2026"
    m = re.search(r'(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})', content)
    if m:
        details.setdefault('posted_at', m.group(1))
        details.setdefault('deadline', m.group(2))

    # Deadline (Greek long format): "Καταληκτική ημερομηνία:\n\nΠέμπτη, Ιούνιος 4, 2026"
    m = re.search(r'Καταληκτική ημερομηνία:\s*\n+[Α-Ωα-ω]+,\s+([Α-Ωα-ω]+\s+\d{1,2},\s+\d{4})', content)
    if m:
        details['deadline'] = m.group(1).strip()

    # Description: main paragraph (after author/date header lines)
    # Find the paragraph that starts with "Ο Δήμος..." or "Η..." or similar
    m = re.search(
        r'Καταληκτική ημερομηνία:.{0,200}\n\n(.+?)(?:\n\nΠερίοδος|\n\nΕπικοινωνία|\n\n\[Προκήρυξη|\Z)',
        content, re.DOTALL
    )
    if m:
        desc = m.group(1).strip()
        if len(desc) > 20:
            details['description'] = desc[:800]

    # Contract type: "Προσωπικό:\n\n[Ορισμένου Χρόνου](...)"
    m = re.search(r'Προσωπικό:\s*\n+\[([^\]]+)\]', content)
    if m:
        details['contract_type'] = m.group(1).strip()

    # Specialty (sciences field): "Επιστήμες:\n\n[Ανθρωπιστικές](...)"
    m = re.search(r'Επιστήμες:\s*\n+\[([^\]]+)\]', content)
    if m:
        details['specialty'] = m.group(1).strip()

    # Education level: "Επίπεδο Εκπαίδευσης:\n\n[Πανεπιστημιακής (ΠΕ)](...)"
    m = re.search(r'Επίπεδο Εκπαίδευσης:\s*\n+\[([^\]]+)\]', content)
    if m:
        details['requirements'] = m.group(1).strip()

    # Location: "Γεωγραφική Περιοχή:\n\n[Αττική](...)"
    m = re.search(r'Γεωγραφική Περιοχή:\s*\n+\[([^\]]+)\]', content)
    if m:
        details['location'] = m.group(1).strip()

    # Number of positions from description: "πρόσληψη 3" or "1 ΠΕ"
    m_pos = re.search(r'πρόσληψη[ν]?\s+(\d+)\s+', content)
    if m_pos:
        details['positions'] = m_pos.group(1)

    # Announcement / PDF link: "[Προκήρυξη](url)"
    m = re.search(r'\[Προκήρυξη\]\((https?://[^)]+)\)', content)
    if m:
        proc_url = m.group(1).strip()
        details['pdf_urls'] = [proc_url]

    # Fallback: any PDF links in html
    if not details.get('pdf_urls'):
        pdfs = extract_pdf_links(html, job_url)
        if pdfs:
            details['pdf_urls'] = pdfs[:3]

    return details


# ── Upsert ────────────────────────────────────────────────────────────────────

def url_in_db(url: str) -> bool:
    res = supabase.table('kepea_listings').select('id').eq('url', url).limit(1).execute()
    return bool(res.data)


def upsert(job: dict) -> bool:
    url = (job.get('url') or '').strip()
    if not url:
        return False
    if url_in_db(url):
        return False
    job['scraped_at'] = datetime.now(timezone.utc).isoformat()
    job['status']     = 'new'
    supabase.table('kepea_listings').insert(job).execute()
    return True


# ── Main scrape flow ──────────────────────────────────────────────────────────

def scrape_source(source_url: str) -> list[dict]:
    print(f'\n  List: {source_url[:70]}')
    content, html = firecrawl_scrape(source_url)
    if not content:
        print('  → no content')
        return []

    jobs = parse_duth_list(content, source_url)
    if not jobs:
        jobs = parse_generic(content, html, source_url)

    print(f'  → {len(jobs)} jobs on list page')

    # Only fetch detail pages for jobs not already in DB
    new_jobs = [j for j in jobs if not url_in_db(j['url'])]
    print(f'  → {len(new_jobs)} new (will scrape detail pages)')

    for i, job in enumerate(new_jobs, 1):
        print(f'     [{i}/{len(new_jobs)}] {job["url"][-30:]}', end=' ')
        details = scrape_job_details(job['url'])
        if details:
            for k, v in details.items():
                if v:  # only overwrite if detail page returned a value
                    job[k] = v
            print('✓')
        else:
            print('(no details)')
        time.sleep(0.5)  # be polite to Firecrawl

    return new_jobs


def main():
    result = supabase.table('kepea_sources').select('url, label').eq('enabled', True).execute()
    sources = result.data or []

    if not sources:
        print('No enabled sources in kepea_sources table.')
        print(json.dumps({'scraped': 0, 'inserted': 0}))
        return

    total_scraped  = 0
    total_inserted = 0

    for src in sources:
        new_jobs = scrape_source(src['url'])
        inserted = sum(1 for j in new_jobs if upsert(j))
        total_scraped  += len(new_jobs)
        total_inserted += inserted
        print(f'  → inserted {inserted}')

    summary = {'scraped': total_scraped, 'inserted': total_inserted}
    print(f'\nDone: {total_scraped} new scraped, {total_inserted} inserted')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
