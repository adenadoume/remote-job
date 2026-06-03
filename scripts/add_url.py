#!/usr/bin/env python3
"""
Scrape any job board URL and extract matching listings into Supabase.
Usage: python3 add_url.py <board_url>
Works on any page: Firecrawl fetches it, DeepSeek extracts job listings as JSON.
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
from urllib.parse import urlparse

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

supabase  = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
deepseek  = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com')
FIRECRAWL = os.environ.get('FIRECRAWL_API_KEY', '')

EXTRACT_PROMPT = """\
You are parsing a job board page. Extract ALL job listings that match these criteria:
- Role is relevant to: Python, FastAPI, backend engineering, AI/ML, LLM, data engineering, \
analytics engineering, MLOps, agent systems, integration engineering, DevOps/platform
- Position is remote (fully remote or remote-first; skip "in office" or "on-site")

Return ONLY a valid JSON array, no markdown, no explanation:
[
  {{
    "title": "<exact job title>",
    "company": "<company name>",
    "url": "<direct application or job detail URL — must be absolute>",
    "salary_min": <annual USD integer or null>,
    "salary_max": <annual USD integer or null>,
    "tags": ["<lowercase skill>", ...],
    "posted_at": "<ISO date string or null>"
  }}
]

Return [] if no matching listings found.
Base URL of page: {base_url}

PAGE CONTENT:
{content}"""


def firecrawl_scrape(url: str) -> str:
    if not FIRECRAWL:
        return ''
    try:
        r = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers={'Authorization': f'Bearer {FIRECRAWL}', 'Content-Type': 'application/json'},
            json={'url': url, 'formats': ['markdown']},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get('data', {}).get('markdown', '')
    except Exception as e:
        print(f'Firecrawl error: {e}', file=sys.stderr)
    return ''


def extract_listings(content: str, base_url: str) -> list[dict]:
    prompt = EXTRACT_PROMPT.format(content=content[:8000], base_url=base_url)
    resp = deepseek.chat.completions.create(
        model='deepseek-chat',
        max_tokens=2048,
        temperature=0.1,
        messages=[{'role': 'user', 'content': prompt}],
    )
    raw = resp.choices[0].message.content.strip().strip('`')
    if raw.lower().startswith('json'):
        raw = raw[4:].strip()
    return json.loads(raw)


def source_name(url: str) -> str:
    host = urlparse(url).netloc.replace('www.', '')
    return host.split('.')[0]  # e.g. crossinghurdles.com → crossinghurdles


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'No URL provided'}))
        sys.exit(1)

    board_url = sys.argv[1].strip()
    source    = source_name(board_url)

    print(f'Scraping {board_url}…', file=sys.stderr)
    content = firecrawl_scrape(board_url)
    if not content:
        print(json.dumps({'success': False, 'error': 'Could not scrape URL — check Firecrawl key'}))
        sys.exit(1)

    print(f'Extracting listings with DeepSeek… ({len(content)} chars)', file=sys.stderr)
    try:
        listings = extract_listings(content, board_url)
    except Exception as e:
        print(json.dumps({'success': False, 'error': f'Extraction failed: {e}'}))
        sys.exit(1)

    print(f'Found {len(listings)} matching listings', file=sys.stderr)

    inserted = 0
    skipped  = 0
    for job in listings:
        url = (job.get('url') or '').strip()
        if not url or not url.startswith('http'):
            skipped += 1
            continue
        existing = supabase.table('job_listings').select('id').eq('url', url).execute()
        if existing.data:
            skipped += 1
            continue
        row = {
            'url':        url,
            'title':      job.get('title') or 'Unknown',
            'company':    job.get('company') or 'Unknown',
            'source':     source,
            'salary_min': job.get('salary_min'),
            'salary_max': job.get('salary_max'),
            'tags':       job.get('tags') or [],
            'posted_at':  job.get('posted_at'),
            'scraped_at': datetime.now(timezone.utc).isoformat(),
            'status':     'new',
        }
        try:
            supabase.table('job_listings').insert(row).execute()
            inserted += 1
            print(f'  + {row["title"]} @ {row["company"]}', file=sys.stderr)
        except Exception as e:
            print(f'  insert error: {e}', file=sys.stderr)
            skipped += 1

    print(json.dumps({
        'success': True,
        'found':    len(listings),
        'inserted': inserted,
        'skipped':  skipped,
        'source':   source,
    }))


if __name__ == '__main__':
    main()
