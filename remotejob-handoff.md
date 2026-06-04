# Remote Job + KEPEA — Full Handoff

**Last updated:** 2026-06-04  
**Status:** Both apps live. job.agop.pro (remote jobs) + kepea.agop.pro (Greek public-sector jobs)  
**Repo:** github.com:adenadoume/remote-job  
**Oracle VM alias:** oracle-softone (`/opt/jobs/scripts/`)  
**Vercel project:** remote-job (adenadoumes-projects team)

---

## 1. What the Two Apps Do

### job.agop.pro — Remote Jobs Dashboard
Personal remote job board. Oracle VM scrapes 5 job boards daily, stores in Supabase, scores each listing 0–10 with DeepSeek V4 against the owner's CV. Filterable React dashboard on Vercel.

### kepea.agop.pro — Greek Public-Sector Job Tool
Girlfriend's daily tool. Oracle VM scrapes DUTH career portal + Culture Ministry + CERTH daily, stores full job listings in Supabase, displays cards with click-to-copy per field so she can paste into KEPEA admin system. She marks each job ✓ Καταχωρήθηκε or ✕ Παράλειψη.

---

## 2. Architecture

| Piece | Location | Notes |
|-------|----------|-------|
| React frontend (both apps) | Vercel — `remote-job` project | Static SPA, no serverless functions |
| Database | Supabase (PostgreSQL) | anon key for browser reads/writes; service-role key for VM inserts |
| Scraping (remote jobs) | Oracle VM cron `scrape.py` | requests + RSS + Firecrawl for JS pages |
| Scoring | Oracle VM cron `score.py` | DeepSeek V4 via OpenAI-compat API |
| KEPEA scraping | Oracle VM cron `kepea_scrape.py` | requests HTTP → Firecrawl REST (not SDK) → individual job pages |
| FastAPI control | Oracle VM `agop-os-api` port 8002 | Triggers scrape/score from frontend buttons |

**Key decisions:**
- No Vercel serverless functions — Oracle VM cron avoids timeout limits
- Firecrawl only used where needed (JS-rendered pages or complex sites)
- DUTH is plain HTML — currently using Firecrawl but can switch to requests+BS4 (see roadmap)
- DeepSeek V4 for scoring (cheap, OpenAI-compatible, not Anthropic)
- No login/auth — single user, private URL

---

## 3. File Structure

```
apps/remote-job/
├── scripts/                       ← Oracle VM (/opt/jobs/scripts/)
│   ├── scrape.py                  ← remote jobs: 5 boards → Supabase
│   ├── score.py                   ← DeepSeek scorer for job_listings
│   ├── kepea_scrape.py            ← KEPEA: DUTH + others → kepea_listings
│   ├── requirements.txt
│   └── .env                       ← NOT in git (see env vars section)
├── src/
│   ├── App.tsx                    ← mode toggle jobs/kepea + hostname detection
│   ├── types.ts                   ← JobListing, KepeasListing, Stats, Filters
│   ├── lib/supabase.ts
│   ├── pages/
│   │   └── KepeasPage.tsx         ← full KEPEA dashboard
│   ├── components/
│   │   ├── Header.tsx
│   │   ├── StatCards.tsx
│   │   ├── FilterBar.tsx
│   │   ├── JobTable.tsx
│   │   ├── JobDrawer.tsx
│   │   ├── KepeasCard.tsx         ← click-to-copy per field + Copy All
│   │   └── KepeasSources.tsx      ← source manager (add/enable/disable URLs)
│   └── styles/globals.css
├── vercel.json                    ← SPA rewrite only
├── .env.example
└── remotejob-handoff.md           ← THIS FILE
```

---

## 4. Environment Variables

### Frontend — Vercel project env vars
```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_API_BASE_URL=https://agop-os.agop.pro    ← FastAPI on Oracle VM
```

### Oracle VM — `/opt/jobs/scripts/.env`
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
DEEPSEEK_API_KEY=sk-...
FIRECRAWL_API_KEY=fc-...
```

---

## 5. Supabase Tables

### job_listings (remote jobs)
```sql
create table job_listings (
  id           uuid primary key default gen_random_uuid(),
  url          text unique not null,
  url_hash     text generated always as (md5(url)) stored,
  title        text not null,
  company      text not null,
  source       text not null,
  salary_min   int,
  salary_max   int,
  tags         text[],
  posted_at    timestamptz,
  scraped_at   timestamptz default now(),
  match_score  int,
  match_reason text,
  status       text default 'new',
  notes        text
);
create index on job_listings (scraped_at desc);
create index on job_listings (match_score desc);
create index on job_listings (status);
create index on job_listings (source);
alter table job_listings enable row level security;
create policy "anon read"   on job_listings for select using (true);
create policy "anon update" on job_listings for update using (true) with check (true);
```

### kepea_listings (Greek jobs)
```sql
create table kepea_listings (
  id            uuid primary key default gen_random_uuid(),
  url           text unique not null,   -- individual job page URL (unique key)
  title         text,
  employer      text,
  positions     text,
  specialty     text,
  location      text,
  posted_at     text,
  deadline      text,
  contract_type text,
  requirements  text,
  description   text,
  pdf_urls      text[],               -- Προκήρυξη link (employer PDF or announcement)
  source        text,                 -- 'duth' | 'culture' | 'certh'
  scraped_at    timestamptz default now(),
  status        text default 'new'    -- 'new' | 'uploaded' | 'skipped'
);
create index on kepea_listings (scraped_at desc);
create index on kepea_listings (status);
alter table kepea_listings enable row level security;
create policy "anon read"   on kepea_listings for select using (true);
create policy "anon update" on kepea_listings for update using (true) with check (true);
```

### kepea_sources (KEPEA source manager)
```sql
create table kepea_sources (
  id         uuid primary key default gen_random_uuid(),
  url        text unique not null,
  label      text not null,
  enabled    boolean default true,
  added_at   timestamptz default now()
);
-- Default sources (run once):
insert into kepea_sources (url, label) values
  ('https://career.duth.gr/portal/?q=publicsector/search',      'DUTH Δημόσιος Τομέας'),
  ('https://career.duth.gr/portal/?q=organisation/search/68',   'DUTH Οργανισμός 68'),
  ('https://career.duth.gr/portal/?q=organisation/search/67',   'DUTH Οργανισμός 67'),
  ('https://www.culture.gov.gr/el/announcements/SitePages/proclamations.aspx?f=1', 'Υπουργείο Πολιτισμού'),
  ('https://www.certh.gr/CCAC170B.el.aspx', 'CERTH');
alter table kepea_sources enable row level security;
create policy "anon read"   on kepea_sources for select using (true);
create policy "anon update" on kepea_sources for update using (true) with check (true);
create policy "anon insert" on kepea_sources for insert with check (true);
```

---

## 6. KEPEA Scraper — How It Works

### kepea_scrape.py strategy (2-step per source)

**Step 1 — List page** (1 Firecrawl call per source):  
Parse the DUTH 2-column markdown table:
```
| Καταληκτική Ημερομηνία | Τίτλος |
| dd/mm/yyyy             | [title text](https://career.duth.gr/portal/?q=node/XXXXXX) |
```
→ Extracts: deadline, title, individual job URL  
→ Also extracts from title text: contract_type, positions count, employer (regex)

**Step 2 — Individual job pages** (1 Firecrawl call per NEW job):  
Scrapes `career.duth.gr/portal/?q=node/XXXXXX` and extracts:
- `posted_at` — "Ημερομηνία:" line
- `deadline` — "Καταληκτική ημερομηνία:" or application period range
- `description` — main announcement paragraph
- `contract_type` — "Προσωπικό:" taxonomy link
- `specialty` — "Επιστήμες:" taxonomy link
- `requirements` — "Επίπεδο Εκπαίδευσης:" taxonomy link
- `location` — "Γεωγραφική Περιοχή:" taxonomy link
- `pdf_urls` — "[Προκήρυξη](url)" link = employer's actual PDF/announcement

**Efficiency:** Only NEW jobs (not already in DB by `url` unique key) get step 2.  
First run: ~50 Firecrawl calls. Subsequent daily: only truly new jobs.

### Cron schedule
```cron
15 08 * * 1-6  cd /opt/jobs/scripts && python3 kepea_scrape.py >> /var/log/kepea-scrape.log 2>&1
```

### Known gaps
- **Culture Ministry** (culture.gov.gr) — 0 jobs extracted, different JS page structure. Needs Playwright or custom scraper.
- **CERTH** — generic fallback sometimes picks up navigation links as false positives.

---

## 7. Oracle VM Cron Schedule (full)
```cron
00 08 * * 1-6  cd /opt/jobs/scripts && python3 scrape.py       >> /var/log/jobs-scrape.log  2>&1
30 08 * * 1-6  cd /opt/jobs/scripts && python3 score.py        >> /var/log/jobs-score.log   2>&1
15 08 * * 1-6  cd /opt/jobs/scripts && python3 kepea_scrape.py >> /var/log/kepea-scrape.log 2>&1
```

---

## 8. Domains & Deploy

| Domain | Project | Mode |
|--------|---------|------|
| job.agop.pro | remote-job (Vercel) | Remote jobs dashboard |
| kepea.agop.pro | remote-job (Vercel, same project) | KEPEA mode — hostname detection in App.tsx |

DNS: Cloudflare, both are CNAMEs pointing to Vercel.  
Deploy: `git push` → Vercel auto-deploys from `apps/remote-job/` root.

---

## 9. Remote Jobs Scraper (scrape.py)

### Job Boards
| Board | Method | Notes |
|-------|--------|-------|
| RemoteOK | JSON API | Free, reliable |
| We Work Remotely | RSS feed | Backend category |
| Wellfound | Firecrawl | JS-rendered |
| YC Jobs | Firecrawl | JS-rendered |
| Arc.dev | Firecrawl | JS-rendered |

### Filter
Must contain ≥1 of: `python fastapi backend api ai ml llm data engineer analytics mlops agent`  
Must be remote. Salary ≥ $60k if shown.

### Scoring (score.py)
DeepSeek V4 (`deepseek-chat`), 0–10 against:
- 15+ yrs supply chain IT / backend / hospitality ops
- Python, FastAPI, PostgreSQL, Supabase, React, Docker, Linux, Claude/MCP
- MSc Data Management (Hellenic Open University)
- Target: remote $80k+, startup/AI-focused
- Format: `{"score": 0-10, "reason": "one sentence max 20 words"}`

---

## 10. Frontend Design System

**Fonts:** Inter (UI) + JetBrains Mono (numbers/scores)  
**Sizes:** 15px body | 14px table cells | 22px card values | 12px labels | 13px buttons  
**Palette:** `#09090B` page → `#18181B` panels → ocean-blue controls  
**Score colors:** ≥8 green | 5–7 amber | <5 red  
**All styles:** `src/styles/globals.css` only — no Tailwind, no component libraries

---

## 11. Roadmap — Planned Features (discussed 2026-06-04)

These were discussed and agreed in principle. Pick up from here.

---

### 11A. Replace Firecrawl with direct requests+BS4 for DUTH ⚡ HIGH PRIORITY

**Why:** DUTH pages are plain server-rendered HTML — no JavaScript. Using Firecrawl wastes ~50 API credits per daily run unnecessarily.

**Plan:**
- Replace `firecrawl_scrape(url)` with `requests.get(url)` + `BeautifulSoup(html, 'lxml')`
- Parse the actual HTML `<table>` directly (more reliable than markdown parsing)
- Keep Firecrawl only for JS-rendered sources (culture.gov.gr, any future JS sites)
- Result: DUTH scraping becomes free and faster (no API overhead)

**Implementation sketch:**
```python
import requests, bs4

def fetch_html(url):
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    return bs4.BeautifulSoup(r.text, 'lxml')

def parse_duth_list_bs4(url):
    soup = fetch_html(url)
    rows = []
    for tr in soup.select('table tr')[1:]:   # skip header
        cells = tr.find_all('td')
        if len(cells) >= 2:
            deadline = cells[0].get_text(strip=True)
            a = cells[1].find('a')
            if a:
                rows.append({'deadline': deadline, 'title': a.get_text(strip=True),
                             'url': a['href']})
    return rows

def scrape_job_page_bs4(url):
    soup = fetch_html(url)
    # Extract structured fields from the page's definition list / field groups
    ...
```

---

### 11B. Configurable source framework for new websites

**Why:** The girlfriend will want to add ASEP, Diavgeia, individual ministry sites, etc.

**Plan:**
- Add columns to `kepea_sources` table:
  ```sql
  alter table kepea_sources
    add column parser_type text default 'duth',  -- 'duth' | 'bs4_table' | 'link_list' | 'firecrawl'
    add column list_selector text,               -- CSS selector for list rows (optional)
    add column detail_enabled boolean default true;
  ```
- `kepea_scrape.py` checks `parser_type` per source and routes to the right parser function
- New sites added in UI → specify label, URL, parser type, CSS selectors
- Generic `bs4_table` parser works for any site with a simple `<table>` listing
- `firecrawl` type kept for JS-rendered sites

---

### 11C. HTML export with click-to-copy (daily file + download button) 📄

**Two delivery methods:**

#### Method 1 — Frontend "Download HTML" button
Add to `KepeasPage.tsx`:
```tsx
function downloadHtml() {
  const html = generateKepeasHtml(filtered)  // port of kepea_daily_FINAL.py's HTML
  const blob = new Blob([html], { type: 'text/html' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `KEPEA_${new Date().toISOString().slice(0,10)}.html`
  a.click()
}
```
The HTML uses the same design as the original `kepea_daily_FINAL.py` — purple/gradient header, card per job, click-to-copy per field, single-click PDF open.

#### Method 2 — Scraper generates HTML and emails it
At end of `kepea_scrape.py` run, generate HTML file + email it:
```python
def send_email_report(html_content: str, new_jobs: int):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'KEPEA: {new_jobs} νέες θέσεις — {datetime.now():%d/%m/%Y}'
    msg['From'] = os.environ['SMTP_FROM']
    msg['To'] = os.environ['KEPEA_EMAIL']
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(os.environ['SMTP_FROM'], os.environ['SMTP_PASSWORD'])
        s.send_message(msg)
```
New env vars needed: `SMTP_FROM`, `SMTP_PASSWORD` (Gmail App Password), `KEPEA_EMAIL`  
Only sends if new_jobs > 0.

**Recommendation:** Do both. Frontend button for ad-hoc use; email for daily automation.

---

### 11D. Playwright automation for KEPEA admin — Human-in-the-Loop 🤖

**This is the most powerful feature.** After the girlfriend reviews the job cards and clicks "Approve", a Python Playwright script auto-fills each approved job into the KEPEA admin panel.

**Architecture:**
```
kepea.agop.pro
  ↓ Girlfriend reviews cards
  ↓ Clicks "✓ Approve for auto-submit" per job (new status: 'approved')
  ↓
kepea_submit.py (runs on Oracle VM or triggered via FastAPI button)
  ↓ Playwright browser (headless)
  ↓ Login to kepea.gr admin with stored credentials
  ↓ For each 'approved' listing:
     → Navigate to "New Job" form
     → Fill all fields (title, employer, deadline, etc.)
     → Upload PDF if available (download from pdf_urls first)
     → Click Submit
     → Update status → 'uploaded' in Supabase
  ↓ Email summary report
```

**Implementation steps:**
1. Add `status = 'approved'` to `kepea_listings` (between 'new' and 'uploaded')
2. Add "Approve for Submit" button to `KepeasCard.tsx`
3. Add `/api/kepea/submit` endpoint to FastAPI
4. Write `scripts/kepea_submit.py` with Playwright
5. Store `KEPEA_ADMIN_URL`, `KEPEA_USERNAME`, `KEPEA_PASSWORD` in `.env`

**Human-in-the-loop flow:**
```
Morning:
  08:15  kepea_scrape.py runs → new jobs appear as 'new' in kepea.agop.pro
  GF opens kepea.agop.pro → reviews cards
  GF clicks "✓ Approve" on relevant jobs (status → 'approved')
  GF clicks "🤖 Submit Approved" button in header
    → calls /api/kepea/submit
    → kepea_submit.py runs Playwright
    → auto-fills all 'approved' jobs into kepea.gr admin
    → updates status → 'uploaded'
    → emails summary
```

**Prerequisites:**
- `pip install playwright && playwright install chromium` on Oracle VM
- KEPEA admin credentials (URL + username + password)
- Someone needs to map the KEPEA admin form fields first (inspect the form manually once)

---

### 11E. Culture Ministry (culture.gov.gr) — custom parser

The ministry page is JS-rendered (SharePoint). Options:
1. Use Playwright to scrape it (consistent with 11D setup)
2. Keep Firecrawl for this one URL (it returned 0 jobs — Firecrawl may need `waitFor` param)
3. Try the direct URL: `https://www.culture.gov.gr/el/announcements/SitePages/proclamations.aspx?f=1` with different approach

---

## 12. Known Issues / Bugs

| Issue | Impact | Fix |
|-------|--------|-----|
| Culture Ministry returns 0 jobs | Missing ~20 ministry job listings daily | See 11E |
| CERTH picks up nav links | 2–3 garbage rows in kepea_listings | Add URL filter: only insert if url contains a job-like path |
| DUTH org/68 picks up europa.eu links | Non-DUTH rows with no details | Filter: skip if `url_in_db` and skip if no title keyword match |
| Firecrawl ~50 calls/day for DUTH | API credit usage | Replace with requests+BS4 (see 11A) |

---

## 13. Session History

### 2026-06-04 (Session 1 — initial KEPEA build)
- Created `kepea_scrape.py`, `KepeasPage.tsx`, `KepeasCard.tsx`, `KepeasSources.tsx`
- Set up `kepea_listings` + `kepea_sources` Supabase tables
- Added `/api/kepea/scrape` FastAPI endpoint
- Added `kepea.agop.pro` domain (already was assigned to remote-job Vercel project, verified)
- Set up cron on Oracle VM: `15 08 * * 1-6`
- **Bug:** Firecrawl SDK rejected `params` kwarg → fixed by switching to direct HTTP

### 2026-06-04 (Session 2 — scraper rewrite)
- Discovered scraper was using wrong parser (looking for DUTH section headers that don't exist)
- Actual DUTH format: 2-column table `| deadline | [title](node_url) |`
- **Complete rewrite:** `parse_duth_list()` + `scrape_job_details()` for individual pages
- Individual pages provide: description, posted_at, contract_type, specialty, location, requirements, Προκήρυξη link
- Cleared 29 bad old records, re-scraped → **49 DUTH jobs with all fields correct**
- Employer/positions/contract_type also extracted from title text regex as fallback

---

## 14. What Is NOT Done Yet

- [ ] Replace Firecrawl with requests+BS4 for DUTH (see 11A)
- [ ] HTML export button in KepeasPage.tsx (see 11C)
- [ ] Email report after daily scrape (see 11C)
- [ ] Playwright auto-submit to KEPEA admin (see 11D) — needs credentials
- [ ] Culture Ministry parser (see 11E)
- [ ] Configurable source framework for new sites (see 11B)
- [ ] Auth/login gate (low priority — single user, private URL)
- [ ] Filter out CERTH navigation links + europa.eu false positives (minor)

---

## 15. Decisions Made

| Date | # | Decision |
|------|---|----------|
| 2026-06-04 | 1 | No Vercel serverless — Oracle VM cron instead |
| 2026-06-04 | 2 | DeepSeek V4 for scoring (cheap, OpenAI-compatible) |
| 2026-06-04 | 3 | Firecrawl for JS-rendered job boards |
| 2026-06-04 | 4 | Fonts bumped: 15px body, 14px table, 22px card values |
| 2026-06-04 | 5 | No auth for now — single user, private URL |
| 2026-06-04 | 6 | Firecrawl SDK → direct HTTP (SDK rejected `params` on VM) |
| 2026-06-04 | 7 | kepea.agop.pro = same Vercel project, hostname-detected mode switch |
| 2026-06-04 | 8 | DUTH scraper: 2-step (list parse → individual job pages) |
| 2026-06-04 | 9 | ROADMAP: Playwright KEPEA auto-submit planned (needs credentials) |
| 2026-06-04 | 10 | ROADMAP: Replace Firecrawl with BS4 for plain-HTML DUTH pages |
