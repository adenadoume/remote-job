#!/usr/bin/env python3
"""
Scrape Greek job boards for KEPEA listings and store in Supabase.

Scraping strategy:
  DUTH  (career.duth.gr)  — plain HTML → requests + BS4 (free)
  CERTH (certh.gr)        — plain HTML → requests + BS4 tile parser (free)
  Other / new sources     → requests + BS4 (or Firecrawl for JS) → DeepSeek AI extraction

  DeepSeek flow for unknown sources:
    1. Fetch list page text
    2. DeepSeek extracts all job dicts + needs_subpage flag
    3. For new jobs with needs_subpage=True, fetch subpage → DeepSeek extracts full fields
    4. Upsert to kepea_listings

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
FIRECRAWL_KEY  = os.environ.get('FIRECRAWL_API_KEY', '')
DEEPSEEK_KEY   = os.environ.get('DEEPSEEK_API_KEY', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept-Language': 'el-GR,el;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml',
}

DUTH_BASE  = 'https://career.duth.gr'
CERTH_BASE = 'https://www.certh.gr'


# ── Source routing ────────────────────────────────────────────────────────────

def is_duth(url: str) -> bool:
    return 'career.duth.gr' in url

def is_certh(url: str) -> bool:
    return 'certh.gr' in url


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


# ── Direct HTTP + BeautifulSoup (CERTH — tile-based plain HTML) ──────────────

def parse_certh_list_bs4(source_url: str) -> list[dict]:
    """
    Parse CERTH listing page: divs with class="tile_details"
      tile_title > a[href]  → job URL + title (in <strong>) + employer + date
      tile_description      → deadline in <strong>
    """
    from bs4 import NavigableString
    soup, _ = fetch_soup(source_url)
    if not soup:
        return []

    jobs = []
    for tile in soup.find_all('div', class_='tile_details'):
        title_div = tile.find('div', class_='tile_title')
        if not title_div:
            continue
        a_tag = title_div.find('a', href=True)
        if not a_tag or not a_tag['href'].endswith('.el.aspx'):
            continue

        job_url = CERTH_BASE + '/' + a_tag['href']

        strong = a_tag.find('strong')
        title  = strong.get_text(separator=' ', strip=True) if strong else a_tag.get_text(strip=True)

        employer = ''
        for node in a_tag.contents:
            if isinstance(node, NavigableString) and '@' in str(node):
                employer = str(node).strip().lstrip('@').strip()
                break

        date_span = a_tag.find('span')
        posted_at = date_span.get_text(strip=True) if date_span else ''

        desc_div = tile.find('div', class_='tile_description')
        deadline = ''
        if desc_div:
            strong_dl = desc_div.find('strong')
            if strong_dl:
                deadline = strong_dl.get_text(strip=True)

        jobs.append({
            'url':           job_url,
            'title':         title,
            'employer':      employer,
            'positions':     _positions_from_certh_title(title),
            'specialty':     '',
            'location':      'Θεσσαλονίκη',
            'posted_at':     posted_at,
            'deadline':      deadline,
            'contract_type': _contract_type_from_title(title),
            'requirements':  '',
            'description':   '',
            'pdf_urls':      [],
            'source':        'certh',
        })
    return jobs


def scrape_certh_job_bs4(job_url: str) -> dict:
    """Scrape individual CERTH job subpage for PDF attachments and full employer name.

    PDFs live in a separate <table class="ipanel"> outside InnerPageMainContent,
    so we search the whole page.
    """
    soup, _ = fetch_soup(job_url)
    if not soup:
        return {}

    details: dict = {}

    # PDF links are in ipanel tables — search whole page
    pdf_urls = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.pdf' in href.lower() or href.startswith('dat/'):
            full = (CERTH_BASE + '/' + href) if not href.startswith('http') else href
            if full not in pdf_urls:
                pdf_urls.append(full)
    if pdf_urls:
        details['pdf_urls'] = pdf_urls

    # Full employer from InnerPageMainContent
    content_div = soup.find('div', class_='InnerPageMainContent') or soup
    for tag in content_div.find_all(['p', 'div', 'h1', 'h2', 'h3']):
        txt = tag.get_text(strip=True)
        if 'Ινστιτούτο' in txt and len(txt) < 150:
            details['employer'] = txt
            break

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
    if 'ανάθεσης έργου' in t:
        return 'Ανάθεση Έργου'
    if 'μίσθωσης έργου' in t:
        return 'Μίσθωσης Έργου'
    if 'αορίστου χρόνου' in t:
        return 'Αορίστου Χρόνου'
    if 'μετατάξ' in t:
        return 'Μετάταξη'
    if 'υποτροφί' in t:
        return 'Υποτροφία'
    return ''


def _positions_from_title(title: str) -> str:
    m = re.match(r'^(\d+)\s+', title.strip())
    return m.group(1) if m else '1'


def _positions_from_certh_title(title: str) -> str:
    """Extract position count from CERTH title: 'για μία (1) θέση' → '1'."""
    m = re.search(r'\((\d+)\)', title)
    return m.group(1) if m else '1'


def _employer_from_title(title: str) -> str:
    m = re.search(r'\bστ[οα-ωά-ώ]*\s+(.+?)$', title, re.IGNORECASE)
    return _clean(m.group(1)) if m else ''


# ── DeepSeek AI extraction (unknown / new sources) ───────────────────────────

_DS_LIST_SYSTEM = """\
You are a Greek public-sector job board parser.
Given page text, extract ALL job postings and return ONLY a valid JSON array — no markdown, no explanation.

Each element must have these exact keys:
  title         – full Greek job title (string)
  employer      – organisation/institute name (string, "" if unknown)
  positions     – number of open positions (string, default "1")
  deadline      – application deadline (string, "" if not found)
  contract_type – one of: Ορισμένου Χρόνου | Αορίστου Χρόνου | Ανάθεση Έργου | Μίσθωσης Έργου | Υποτροφία | ""
  specialty     – required discipline / field (string, "" if unknown)
  location      – city or region (string, "" if unknown)
  url           – absolute URL of this job's own detail page (string, "" if no subpage)
  needs_subpage – true if url is a separate detail page worth visiting, false otherwise
  pdf_urls      – list of absolute PDF attachment URLs found on this listing ([] if none)

Include ONLY actual job postings, NOT navigation links, menus, or unrelated content.\
"""

_DS_DETAIL_SYSTEM = """\
Extract job details from this Greek public-sector job posting page.
Return ONLY a JSON object (no markdown, no explanation) with these keys:
  title, employer, positions, deadline, contract_type, specialty,
  location, requirements, description
Use empty string "" for any field not found. Keep description under 300 chars.\
"""


def _call_deepseek(system: str, user: str, max_tokens: int = 2000) -> str:
    """Call DeepSeek chat API; returns raw text or '' on failure."""
    if not DEEPSEEK_KEY:
        return ''
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_KEY, base_url='https://api.deepseek.com')
        resp = client.chat.completions.create(
            model='deepseek-chat',
            temperature=0.0,
            max_tokens=max_tokens,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user',   'content': user},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        return re.sub(r'^```(?:json)?\n?', '', raw).rstrip('`').strip()
    except Exception as e:
        print(f'  [deepseek] API error: {e}', file=sys.stderr)
        return ''


def scrape_with_deepseek(source_url: str) -> list[dict]:
    """
    Fetch source_url (BS4 first, Firecrawl fallback) then use DeepSeek to
    extract all job listings.  Returns list of job dicts with a temporary
    '_needs_subpage' key that is popped before upsert.
    """
    # Fetch page text — try plain HTTP first (free), then Firecrawl
    soup, html = fetch_soup(source_url)
    if soup:
        page_text = soup.get_text(separator='\n', strip=True)
    else:
        page_text, html = firecrawl_scrape(source_url)
        if not page_text:
            print('  → no content (neither requests nor Firecrawl)', file=sys.stderr)
            return []

    user_msg = f'Source URL: {source_url}\n\n{page_text[:8000]}'
    raw = _call_deepseek(_DS_LIST_SYSTEM, user_msg, max_tokens=2500)
    if not raw:
        return []

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f'  [deepseek] JSON parse error: {e}\nRaw: {raw[:200]}', file=sys.stderr)
        return []

    source = _source_name(source_url)
    jobs   = []
    for item in items:
        url = (item.get('url') or '').strip()
        if url and not url.startswith('http'):
            url = urljoin(source_url, url)
        if not url:
            url = source_url   # fallback — same page (no subpage)
        jobs.append({
            'url':            url,
            'title':          (item.get('title') or '').strip(),
            'employer':       (item.get('employer') or '').strip(),
            'positions':      str(item.get('positions') or '1'),
            'specialty':      (item.get('specialty') or '').strip(),
            'location':       (item.get('location') or '').strip(),
            'posted_at':      '',
            'deadline':       (item.get('deadline') or '').strip(),
            'contract_type':  (item.get('contract_type') or '').strip(),
            'requirements':   '',
            'description':    '',
            'pdf_urls':       [u for u in (item.get('pdf_urls') or []) if u],
            'source':         source,
            '_needs_subpage': bool(item.get('needs_subpage')),
        })

    print(f'  [deepseek] extracted {len(jobs)} jobs')
    return jobs


def deepseek_job_details(job_url: str) -> dict:
    """
    Fetch a job's detail page and use DeepSeek to extract full fields.
    Falls back to BS4 text → Firecrawl if needed.
    """
    soup, html = fetch_soup(job_url)
    if soup:
        page_text  = soup.get_text(separator='\n', strip=True)[:6000]
        html_source = html
    else:
        page_text, html_source = firecrawl_scrape(job_url)
        page_text = page_text[:6000]
        if not page_text:
            return {}

    raw = _call_deepseek(_DS_DETAIL_SYSTEM, page_text, max_tokens=800)
    if not raw:
        return {}

    try:
        details = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    # Supplement with PDF links found in raw HTML
    if html_source and not details.get('pdf_urls'):
        pdfs = extract_pdf_links(html_source, job_url)
        if pdfs:
            details['pdf_urls'] = pdfs[:3]

    return {k: v for k, v in details.items() if v}


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
    elif is_certh(source_url):
        jobs = parse_certh_list_bs4(source_url)
    else:
        jobs = scrape_with_deepseek(source_url)

    print(f'  → {len(jobs)} jobs on list page')

    new_jobs = [j for j in jobs if not url_in_db(j['url'])]
    print(f'  → {len(new_jobs)} new (fetching detail pages)')

    for i, job in enumerate(new_jobs, 1):
        needs_sub = job.pop('_needs_subpage', True)
        print(f'     [{i}/{len(new_jobs)}] {job["url"][-40:]}', end=' ', flush=True)
        if is_duth(job['url']):
            details = scrape_duth_job_bs4(job['url'])
        elif is_certh(job['url']):
            details = scrape_certh_job_bs4(job['url'])
        elif needs_sub:
            details = deepseek_job_details(job['url'])
        else:
            details = {}
        if details:
            for k, v in details.items():
                if v:
                    job[k] = v
            print('✓')
        else:
            print('(inline)')
        time.sleep(0.4)

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
