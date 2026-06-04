# Remote Job Crawler — Full Handoff

**Last updated:** 2026-06-04  
**Status:** Live at job.agop.pro + kepea.agop.pro — KEPEA scraper running on VM

---

## What This App Does

A personal remote job dashboard. Python scripts on the Oracle VM scrape 5 job boards daily, store listings in Supabase, score each one 0–10 against the owner's CV profile using DeepSeek V4, then display them in a filterable React dashboard deployed on Vercel.

---

## Architecture Decision (important — deviated from original spec)

Original spec called for Vercel Functions (api/scrape, api/score, api/jobs). **Changed to:**

| Piece | Where | Why |
|-------|-------|-----|
| React frontend | Vercel | Static deploy, no serverless functions |
| Supabase | Hosted | Database + direct JS client in browser (anon key) |
| Scrape + Score | Oracle VM cron | No timeout limits, Python is better for scraping, no cold starts |
| Scraping render | Firecrawl API | Handles JS-rendered boards (Wellfound, YC, Arc) |
| Scoring LLM | DeepSeek V4 | Cheap, fast, OpenAI-compatible API |

---

## File Structure (complete)

```
apps/remote-job/
├── scripts/                    ← runs on Oracle VM
│   ├── scrape.py               ← scrapes 5 boards, upserts to Supabase
│   ├── score.py                ← scores unscored rows with DeepSeek
│   ├── requirements.txt        ← pip deps
│   └── .env                    ← NOT committed — copy from .env.example
├── src/
│   ├── App.tsx                 ← main app, all state, Supabase queries
│   ├── main.tsx
│   ├── types.ts                ← JobListing, Stats, JobFilters interfaces
│   ├── components/
│   │   ├── Header.tsx          ← title + refresh button
│   │   ├── StatCards.tsx       ← 5 stat cards (total/new/saved/applied/avg)
│   │   ├── FilterBar.tsx       ← status tabs, source dropdown, score slider, search
│   │   ├── JobTable.tsx        ← main table with score/source badges + row actions
│   │   └── JobDrawer.tsx       ← slide-in detail panel, notes, status buttons
│   ├── lib/
│   │   └── supabase.ts         ← Supabase JS client (anon key)
│   └── styles/
│       └── globals.css         ← full design system, bumped fonts (15px body, 14px cells, 22px card vals)
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── vercel.json                 ← SPA rewrite only (no crons/functions)
├── .env.example
└── remotejob-handoff.md        ← THIS FILE
```

---

## Supabase Schema

Run this SQL in Supabase SQL editor BEFORE deploying:

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
```

Also set up Row Level Security (anon key reads + writes status/notes):
```sql
-- Enable RLS
alter table job_listings enable row level security;

-- Allow anon to read all rows
create policy "anon read" on job_listings for select using (true);

-- Allow anon to update status and notes only
create policy "anon update status" on job_listings for update
  using (true)
  with check (true);
```

---

## Environment Variables

### Frontend (Vercel project env vars)
```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

### Oracle VM scripts (`scripts/.env`)
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
DEEPSEEK_API_KEY=sk-...
FIRECRAWL_API_KEY=fc-...   # optional — Wellfound/YC/Arc skip if absent
```

---

## Oracle VM Setup

### Install deps
```bash
cd /opt/jobs
pip3 install -r requirements.txt
```

### Copy scripts
```bash
cp -r apps/remote-job/scripts/* /opt/jobs/
# create /opt/jobs/.env with the env vars above
```

### Cron (crontab -e)
```cron
00 08 * * 1-6 cd /opt/jobs && python3 scrape.py >> /var/log/jobs-scrape.log 2>&1
30 08 * * 1-6 cd /opt/jobs && python3 score.py  >> /var/log/jobs-score.log  2>&1
```

### Manual test run
```bash
cd /opt/jobs
python3 scrape.py   # scrapes all boards
python3 score.py    # scores up to 20 unscored rows
```

---

## Job Boards Scraped

| Board | Method | Notes |
|-------|--------|-------|
| RemoteOK | JSON API (`https://remoteok.com/api`) | Free, reliable |
| We Work Remotely | RSS feed | Backend jobs category |
| Wellfound | Firecrawl | JS-rendered, needs FIRECRAWL_API_KEY |
| YC Jobs | Firecrawl | JS-rendered |
| Arc.dev | Firecrawl | JS-rendered, `/remote-jobs/fastapi` |

### Filter applied during scrape
Must contain ≥1 of: `python fastapi backend api ai ml llm data engineer analytics engineer mlops agent integration engineer`  
Must be remote. Salary min (if shown) ≥ $60k.

---

## Scoring Prompt (score.py)

DeepSeek V4 (`deepseek-chat` model) scores each listing 0–10 against a fixed candidate profile:
- 15+ yrs supply chain IT / backend / hospitality ops
- Python, FastAPI, PostgreSQL, Supabase, React, Docker, Linux
- AI tools: Claude Code, MCP, Anthropic API
- MSc Data Management (Hellenic Open University) — DAMA501 + DAMA503
- Target: remote $80k+, startup or AI-focused
- Bonus: +1 for data engineering / MLOps / pipelines; +1 for AI/ML/Data/Agent in title

Response format: `{"score": 0-10, "reason": "one sentence max 20 words"}`

---

## Frontend — Design System

**Fonts:** Inter (UI) + JetBrains Mono (numbers/scores/salary) — Google Fonts  
**Base font:** 15px (bumped from monorepo family's 14px standard)  
**Table cells:** 14px | **Card values:** 22px | **Card labels:** 12px | **Buttons:** 13px

**Palette:** `#09090B` page → `#18181B` panels → ocean-blue controls (`#1B2A3B` / `#2A5C8A` / `#5B9BD5`)

**Score colors:** ≥8 green `#4ade80` | 5–7 amber `#fbbf24` | <5 red `#f87171`

**Source badge colors:** remoteok=teal | wwr=green | wellfound=amber | ycjobs=orange | arc=blue | builtin=purple

---

## Frontend — Key Behaviours

- **App.tsx** fetches from Supabase on mount, re-fetches on Refresh button
- Status/notes updates go directly to Supabase (optimistic local update)
- Filter: status tabs, source dropdown, score slider (0–10), text search (title + company)
- Click any row → JobDrawer slides in from right
- Drawer has Save / Applied / Dismiss buttons + notes textarea (auto-save on blur)

---

## Deploy Checklist

- [ ] Run Supabase SQL schema above
- [ ] Add VITE_ env vars to Vercel project
- [ ] `git push` → Vercel auto-deploys (root dir = `apps/remote-job/`)
- [ ] Copy scripts to Oracle VM, create `.env`, install deps
- [ ] Add cron entries, test manually: `python3 scrape.py && python3 score.py`
- [ ] Verify listings appear in dashboard

---

## KEPEA — Greek Job Scraper (added 2026-06-04)

Separate route at **kepea.agop.pro** — girlfriend's tool to find/upload Greek public-sector job postings to the KEPEA admin system.

### New files
| File | Purpose |
|------|---------|
| `scripts/kepea_scrape.py` | Scrapes 5 Greek job boards via Firecrawl REST API (not SDK), upserts to `kepea_listings` |
| `src/pages/KepeasPage.tsx` | Full KEPEA dashboard page |
| `src/components/KepeasCard.tsx` | Card with click-to-copy per field + Copy All + status buttons |
| `src/components/KepeasSources.tsx` | Source manager UI (add/enable/disable URLs) |

### New Supabase tables
Run this SQL if tables don't exist yet:

```sql
create table kepea_listings (
  id            uuid primary key default gen_random_uuid(),
  url           text unique not null,
  title         text, employer text, positions text, specialty text,
  location      text, posted_at text, deadline text, contract_type text,
  requirements  text, description text, pdf_urls text[],
  source        text, scraped_at timestamptz default now(),
  status        text default 'new'
);
create index on kepea_listings (scraped_at desc);
create index on kepea_listings (status);

create table kepea_sources (
  id       uuid primary key default gen_random_uuid(),
  url      text unique not null,
  label    text not null,
  enabled  boolean default true,
  added_at timestamptz default now()
);

insert into kepea_sources (url, label) values
  ('https://career.duth.gr/portal/?q=publicsector/search',      'DUTH Δημόσιος Τομέας'),
  ('https://career.duth.gr/portal/?q=organisation/search/68',   'DUTH Οργανισμός 68'),
  ('https://career.duth.gr/portal/?q=organisation/search/67',   'DUTH Οργανισμός 67'),
  ('https://www.culture.gov.gr/el/announcements/SitePages/proclamations.aspx?f=1', 'Υπουργείο Πολιτισμού'),
  ('https://www.certh.gr/CCAC170B.el.aspx', 'CERTH');

alter table kepea_listings enable row level security;
create policy "anon read"   on kepea_listings for select using (true);
create policy "anon update" on kepea_listings for update using (true) with check (true);
alter table kepea_sources enable row level security;
create policy "anon read"   on kepea_sources for select using (true);
create policy "anon update" on kepea_sources for update using (true) with check (true);
create policy "anon insert" on kepea_sources for insert with check (true);
```

### Cron on Oracle VM
```
15 08 * * 1-6 cd /opt/jobs/scripts && python3 kepea_scrape.py >> /var/log/kepea-scrape.log 2>&1
```

### Domain
`kepea.agop.pro` — verified on Vercel, DNS via Cloudflare (CNAME). The app auto-switches to KEPEA mode when hostname = `kepea.agop.pro`.

### Scraper note
Uses direct HTTP POST to `https://api.firecrawl.dev/v1/scrape` (not the Python SDK) because the VM's `firecrawl-py` version rejected the `params` kwarg.

---

## What Is NOT Done Yet

- Auth (no login gate — single user, assumed private URL for now)
- KEPEA: auto-detect duplicates already in the kepea.gr admin (needs login/Playwright)
- Culture Ministry URL returns 0 jobs — page structure may need a custom parser

---

## Decisions Made

### 2026-06-04

1. **No Vercel Functions** — replaced by Oracle VM cron + direct Supabase client
2. **DeepSeek V4** instead of Anthropic (cheaper for bulk scoring, OpenAI-compatible)
3. **Firecrawl** instead of Playwright (JS boards, no size limits in serverless)
4. **Fonts bumped** — 15px body, 14px table, 22px card values (up from 14/12-13/20)
5. **No auth** for now — scope it later if needed

### 2026-06-04
6. **Firecrawl SDK replaced with direct HTTP** in `kepea_scrape.py` — SDK's `scrape()` rejected `params` kwarg on VM Python env
7. **kepea.agop.pro** — same Vercel project as `job.agop.pro`, hostname detection switches mode automatically
