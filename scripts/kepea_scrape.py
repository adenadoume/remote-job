#!/usr/bin/env python3
"""
Scrape Greek job boards for KEPEA listings and store in Supabase.

Scraping strategy:
  DUTH (career.duth.gr)  — plain HTML → requests + BeautifulSoup (FREE, no API)
  Other sources          → Firecrawl REST API (for JS-rendered pages)

  Per source:
    1. Fetch list page → parse 2-col table (deadline | [title → node URL])
    2. For each NEW job (not already in DB) → fetch individual job page
       for full fields: description, dates, contract type, location, PDF link
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
from bs4 import BeautifulSoup

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

supabase: Client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
FIRECRAWL_KEY   = os.environ.get('FIRECRAWL_API_KEY', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept-Language': 'el-GR,el;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml',
}

DUTH_BASE = 'https://career.duth.gr'


# ── Source routing ────────────────────────────────────────────────────────────

def is_duth(url: str) -> bool:
    return 'career.duth.gr' in url


# ── Direct HTTP + BeautifulSoup (DUTH — plain HTML, no API cost) ─────────────

def fetch_soup(url: str) -> tuple[BeautifulSoup | None, str]:
    """GET url → (BeautifulSoup, raw_html) or (None, '')."""
    try:
        r = http.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = 'utf-8'
        return BeautifulSoup(r.text, 'lxml'), r.text
    except Exception as e:
        print(f'  [fetch] ERROR {url[:60]}: {e}', file=sys.stderr)
        return None, ''


def parse_duth_list_bs4(source_url: str) -> list[dict]:
    """
    Parse DUTH list page: 2-column HTML table
      <td>dd/mm/yyyy</td> | <td><a href="/portal/?q=node/XXXXXX">Title</a></td>
    """
    soup, _ = fetch_soup(source_url)
    if not soup:
        return []

    jobs = []
    for table in soup.find_all('table'):
        for tr in table.find_all('tr'):
            cells = tr.find_all('td')
            if len(cells) < 2:
                continue
            deadline = cells[0].get_text(strip=True)
            if not re.match(r'\d{1,2}/\d{1,2}/\d{4}', deadline):
                continue
            a = cells[1].find('a')
            if not a:
                continue
            title = a.get_text(strip=True)
            href  = a.get('href', '')
            if not href.startswith('http'):
                href = urljoin(DUTH_BASE, href)
            if not href or not title:
                continue
            jobs.append({
                'url':           href,
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


def scrape_duth_job_bs4(job_url: str) -> dict:
    """
    Scrape individual DUTH job page using exact Drupal CSS field classes.

    Drupal field class → KEPEA field:
      field-name-field-psp-deadline         → deadline
      field-name-body                        → description
      field-name-field-real-link             → pdf_urls (Προκήρυξη link)
      field-name-field-psp-personnel         → contract_type
      field-name-field-psp-sciencefields     → specialty
      field-name-field-psp-educationlevel    → requirements
      field-name-field-psp-geographicregion  → location
    """
    soup, html = fetch_soup(job_url)
    if not soup:
        return {}

    details: dict = {}

    def field_text(css_class: str) -> str:
        div = soup.find('div', class_=css_class)
        if not div:
            return ''
        items = div.find(class_='field-items') or div.find(class_='field-item')
        if items:
            a = items.find('a')
            return (a.get_text(strip=True) if a else items.get_text(strip=True))
        return div.get_text(strip=True)

    def field_link(css_class: str) -> str:
        div = soup.find('div', class_=css_class)
        if not div:
            return ''
        a = div.find('a')
        return a.get('href', '') if a else ''

    # Deadline from dedicated field
    dl = field_text('field-name-field-psp-deadline')
    if dl:
        details['deadline'] = dl

    # Description from body field
    desc = field_text('field-name-body')
    if desc and len(desc) > 20:
        details['description'] = desc[:800]

    # Announcement / Προκήρυξη link
    proc_href = field_link('field-name-field-real-link')
    if proc_href:
        if not proc_href.startswith('http'):
            proc_href = urljoin(DUTH_BASE, proc_href)
        details['pdf_urls'] = [proc_href]

    # Taxonomy fields
    contract = field_text('field-name-field-psp-personnel')
    if contract:
        details['contract_type'] = contract

    specialty = field_text('field-name-field-psp-sciencefields')
    if specialty:
        details['specialty'] = specialty

    edu = field_text('field-name-field-psp-educationlevel')
    if edu:
        details['requirements'] = edu

    loc = field_text('field-name-field-psp-geographicregion')
    if loc:
        details['location'] = loc

    # Publication date — from authored-by section (not a Drupal field div)
    text = soup.get_text(separator='\n')
    m = re.search(r'Ημερομηνία[:\s]*\n+([Α-Ωα-ω\w]+\s+\d{1,2},\s+\d{4})', text)
    if m:
        details['posted_at'] = m.group(1).strip()

    # Application period range: "26/05/2026 - 04/06/2026"
    m = re.search(r'(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})', text)
    if m:
        details.setdefault('posted_at', m.group(1))
        details.setdefault('deadline', m.group(2))

    # Positions count from description: "πρόσληψη 3 ΠΕ"
    m = re.search(r'πρόσληψη[ν]?\s+(\d+)\s+', text, re.IGNORECASE)
    if m:
        details['positions'] = m.group(1)

    # Fallback PDF links from raw HTML — skip the generic DUTH study PDFs
    if not details.get('pdf_urls'):
        pdfs = [p for p in extract_pdf_links(html, job_url)
                if 'meleti_aporofisis' not in p and 'meletes' not in p]
        if pdfs:
            details['pdf_urls'] = pdfs[:3]

    return details


# ── Firecrawl REST (non-DUTH JS-rendered pages) ───────────────────────────────

def firecrawl_scrape(url: str) -> tuple[str, str]:
    """Returns (markdown, html) or ('', '') on error."""
    if not FIRECRAWL_KEY:
        print(f'  [firecrawl] No API key — skipping {url[:60]}', file=sys.stderr)
        return '', ''
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


# ── Shared helpers ────────────────────────────────────────────────────────────

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
    if 'ορισμένου χρόνου' in t:
        return 'Ορισμένου Χρόνου'
    if 'μίσθωσης έργου' in t:
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
    m = re.search(r'\bστ[οα-ωά-ώ]*\s+(.+?)$', title, re.IGNORECASE)
    return _clean(m.group(1)) if m else ''


# ── Generic Firecrawl fallback (non-DUTH) ────────────────────────────────────

def parse_generic(content: str, html: str, source_url: str) -> list[dict]:
    """Extract job-like markdown links from Firecrawl markdown output."""
    jobs = []
    pdf_links = extract_pdf_links(html, source_url)
    link_pat = re.compile(r'\[([^\]]{5,120})\]\((https?://[^)]+)\)')
    seen = set()
    for m in link_pat.finditer(content):
        text, link = m.group(1).strip(), m.group(2).strip()
        if not re.search(r'θέσ|εργασ|προκήρ|πρόσληψ|θέση|πρόσκληση', text, re.IGNORECASE):
            continue
        if link in seen:
            continue
        seen.add(link)
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
    print(f'\n  Source: {source_url[:70]}')

    if is_duth(source_url):
        jobs = parse_duth_list_bs4(source_url)
    else:
        content, html = firecrawl_scrape(source_url)
        if not content:
            print('  → no content')
            return []
        jobs = parse_generic(content, html, source_url)

    print(f'  → {len(jobs)} jobs on list page')

    new_jobs = [j for j in jobs if not url_in_db(j['url'])]
    print(f'  → {len(new_jobs)} new (fetching detail pages)')

    for i, job in enumerate(new_jobs, 1):
        print(f'     [{i}/{len(new_jobs)}] {job["url"][-35:]}', end=' ', flush=True)
        if is_duth(job['url']):
            details = scrape_duth_job_bs4(job['url'])
        else:
            content, html = firecrawl_scrape(job['url'])
            details = {}  # extend later if needed for non-DUTH detail pages
        if details:
            for k, v in details.items():
                if v:
                    job[k] = v
            print('✓')
        else:
            print('(no details)')
        time.sleep(0.3)

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
    print(f'\nDone: {total_scraped} new, {total_inserted} inserted')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
