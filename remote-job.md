# Remote Job Crawler App — Handoff to Claude Code

## Goal

Build a **remote job crawler dashboard** that scrapes startup job boards daily, stores results in Supabase, scores each listing against a target CV profile using the Claude API, and displays them in a filterable React dashboard. Deploy on Vercel.

---

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | Vite + React + TypeScript |
| Styling | Plain CSS (globals.css) — match internal app family (see Visual Style section) |
| Backend / API routes | Vercel Functions (Node.js) |
| Cron | Vercel Cron Jobs (daily 08:00 UTC) |
| Database | Supabase (PostgreSQL) |
| Scraping | Playwright (headless, inside Vercel serverless) OR fetch + cheerio for lightweight boards |
| AI scoring | Anthropic Claude API (`claude-sonnet-4-20250514`) |
| Auth | Supabase Auth — single user (owner only) |
| Deploy | Vercel + GitHub |

---

## Visual style — implement exactly

Apply the internal app design language. Full spec is in `HANDOFF_STYLING_FOR_AI.md`. Key rules for this app:

### Palette

```css
--bg-page:      #09090B;
--bg-panel:     #18181B;
--bg-elevated:  #1f2937;
--text-primary: #FAFAFA;
--text-muted:   #9ca3af;
--text-label:   #7FA8C9;
--blue:         #3b82f6;
--blue-light:   #60a5fa;
--border:       rgba(255,255,255,0.05);
--border-hover: rgba(255,255,255,0.1);
```

### Fonts

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
body { font-family: 'Inter', system-ui, sans-serif; }
.metric, .code { font-family: 'JetBrains Mono', monospace; }
```

### Animations

```css
@keyframes fade-in  { from { opacity:0; transform:translateY(-10px);} to { opacity:1; transform:translateY(0);} }
@keyframes slide-up { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0);} }
.animate-fade-in  { animation: fade-in  0.5s ease-out forwards; }
.animate-slide-up { animation: slide-up 0.6s ease-out forwards; }
```

### Header strip

```css
header {
  background: linear-gradient(135deg, #09090B 0%, #111115 100%);
  padding: 12px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
header h1 { color: #E8F4FF; font-weight: 700; letter-spacing: 0.5px; }
header .sub { color: #7FA8C9; font-size: 12px; }
```

### Stat cards (use for summary counts at top of dashboard)

```css
.card {
  background: #18181B;
  border: 1px solid rgba(255,255,255,0.05);
  border-top: 3px solid #3F3F46;
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 120px;
  flex: 1;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5), 0 2px 4px -1px rgba(0,0,0,0.4);
}
.card:hover { background:#27272A; transform:translateY(-4px); border-color:rgba(255,255,255,0.1); box-shadow:0 10px 25px -5px rgba(0,0,0,0.8); }
.card.blue   { border-top-color: #3B82F6; }
.card.green  { border-top-color: #22C55E; }
.card.amber  { border-top-color: #F59E0B; }
.card.purple { border-top-color: #A855F7; }
.card .val { font-size: 20px; font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #fff; }
.card .lbl { font-size: 11px; color: #7FA8C9; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }
```

### Tab/filter buttons (ocean blue)

```css
.tab-btn {
  background: #1B2A3B; border: 1px solid #2A5C8A; color: #A8C8E8;
  padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer;
  transition: background .15s ease, border-color .15s ease, color .15s ease, transform .15s ease, box-shadow .15s ease;
}
.tab-btn:hover, .tab-btn.active {
  background: #2A5C8A; color: #fff; border-color: #5B9BD5;
  transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
```

### Table rows

```css
tbody tr:hover td {
  box-shadow: inset 0 0 0 9999px rgba(0,0,0,0.5);
  cursor: pointer;
  filter: contrast(1.15);
}
```

### Scrollbars

```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0D1B2A; }
::-webkit-scrollbar-thumb { background: #2A5C8A; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #3A7CAA; }
```

---

## Supabase schema

Run this SQL in Supabase SQL editor:

```sql
create table job_listings (
  id           uuid primary key default gen_random_uuid(),
  url          text unique not null,
  url_hash     text generated always as (md5(url)) stored,
  title        text not null,
  company      text not null,
  source       text not null,           -- 'wellfound' | 'remoteok' | 'ycjobs' | 'arc' | 'builtin' | 'wwr'
  salary_min   int,                     -- USD/year, null if not shown
  salary_max   int,
  tags         text[],                  -- ['python','fastapi','remote','ai']
  posted_at    timestamptz,
  scraped_at   timestamptz default now(),
  match_score  int,                     -- 0–10, set by Claude API scoring
  match_reason text,                    -- short Claude explanation
  status       text default 'new',      -- 'new' | 'saved' | 'applied' | 'dismissed'
  notes        text
);

create index on job_listings (scraped_at desc);
create index on job_listings (match_score desc);
create index on job_listings (status);
create index on job_listings (source);
```

---

## Vercel project structure

```
remote-job-app/
├── api/
│   ├── scrape.ts          # POST /api/scrape — scrapes all boards, upserts to Supabase
│   ├── score.ts           # POST /api/score — scores unscored listings via Claude API
│   └── jobs.ts            # GET  /api/jobs  — returns listings with filters
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── Header.tsx
│   │   ├── StatCards.tsx
│   │   ├── FilterBar.tsx
│   │   ├── JobTable.tsx
│   │   └── JobDrawer.tsx  # slide-out detail panel when row clicked
│   ├── lib/
│   │   └── supabase.ts    # supabase client
│   ├── styles/
│   │   └── globals.css
│   └── main.tsx
├── vercel.json
├── vite.config.ts
└── package.json
```

### `vercel.json` — cron config

```json
{
  "crons": [
    { "path": "/api/scrape", "schedule": "0 8 * * 1-6" },
    { "path": "/api/score",  "schedule": "30 8 * * 1-6" }
  ]
}
```

Scrape runs at 08:00 UTC Mon–Sat, score runs 30 min later.

---

## API routes

### `GET /api/jobs`

Query params: `status`, `source`, `min_score`, `limit` (default 50), `offset`.

Returns array of `job_listings` rows ordered by `match_score DESC, scraped_at DESC`.

### `POST /api/scrape`

Scrapes the boards listed below. For each listing:
1. Check if `url_hash` already exists in Supabase → skip if yes.
2. Insert new row with `match_score = null` (scoring happens separately).

Boards to scrape:

| Board | URL | Method |
|-------|-----|--------|
| RemoteOK | `https://remoteok.com/api` | JSON API — free, no auth |
| We Work Remotely | `https://weworkremotely.com/categories/remote-back-end-programming-jobs.json` | JSON feed |
| Wellfound | `https://wellfound.com/jobs` | Playwright (JS-rendered) |
| YC Jobs | `https://www.ycombinator.com/jobs` | fetch + cheerio |
| Arc.dev | `https://arc.dev/remote-jobs/fastapi` | fetch + cheerio |

Filter criteria applied during scrape (discard listings that don't match):
- Must contain at least one of: `python`, `fastapi`, `backend`, `api`, `ai`, `ml`, `llm`, `data engineer`, `analytics engineer`, `mlops`, `llm`, `agent`, `integration engineer`
- Must be marked remote
- Salary min (if shown) >= $60,000

### `POST /api/score`

Fetches all rows where `match_score IS NULL`, limit 20 per run.

For each listing, calls Claude API:

```typescript
const prompt = `
You are evaluating a remote job listing for this candidate:

CANDIDATE PROFILE:
- 15+ years experience: supply chain IT, backend engineering, hospitality ops
- Skills: Python, FastAPI, PostgreSQL, Supabase, React, Docker, Linux
- AI tools: Claude Code, MCP, AI Agents, Anthropic API
- ERP: SoftOne, EpsilonNet
- Self-taught, currently transitioning to full backend / AI engineering roles
- Currently enrolled in MSc in Data Management (DAMA) at Hellenic Open University — modules: DAMA501 (statistics, linear algebra, ML foundations) and DAMA503 (Python for data, SQL, Jupyter). Starting October.
- Target: remote, $80k+, startup or AI-focused company
- Strong: system architecture, ERP integrations, workflow automation, full lifecycle ownership
- Actively targeting: AI systems, agent orchestration, production ML, data engineering, AI integration engineering

SCORING GUIDANCE:
- Give a +1 bonus (up to 10 max) if the role involves data engineering, analytics engineering, ML ops, or data pipelines — aligns with active MSc study
- Give a +1 bonus if the role title includes: AI Engineer, Data Engineer, ML Engineer, Agent, LLM, or Integration Engineer
- Standard 10 = Python/FastAPI/AI, remote, $80k+, startup, growth opportunity
- 0 = no match

JOB LISTING:
Title: ${job.title}
Company: ${job.company}
Source: ${job.source}
Salary: ${job.salary_min ? '$'+job.salary_min+'-$'+job.salary_max : 'not shown'}
Tags: ${job.tags?.join(', ')}
URL: ${job.url}

Score this listing 0–10 for fit with this candidate.

Respond ONLY with valid JSON, no markdown:
{"score": <0-10>, "reason": "<one sentence max 20 words>"}
`;
```

Parse response, update row `match_score` and `match_reason`.

---

## Frontend — dashboard layout

```
┌──────────────────────────────────────────────────────────┐
│  HEADER  🔵 Remote Jobs                [Run Scrape] [▼]  │
├──────────────────────────────────────────────────────────┤
│  STAT CARDS (row)                                        │
│  [Total] [New] [Saved] [Applied] [Avg Score]             │
├──────────────────────────────────────────────────────────┤
│  FILTER BAR                                              │
│  [All] [New] [Saved] [Applied]  Source▼  Score≥[   ]     │
│  Search: [___________________________]                   │
├──────────────────────────────────────────────────────────┤
│  JOB TABLE                                               │
│  Score | Title | Company | Source | Salary | Posted | ↗  │
│  ──────────────────────────────────────────────────────  │
│  9/10  | Sr Backend Eng | Acme | wellfound | $120k | 2d  │
│  8/10  | FastAPI Dev    | YCo  | ycjobs    | $100k | 1d  │
│  ...                                                     │
└──────────────────────────────────────────────────────────┘
```

### Stat cards

- Total listings (blue)
- New / unreviewed (amber)
- Saved (green)
- Applied (purple)
- Avg match score — show as `X.X / 10` in JetBrains Mono

### Filter bar

- Status tabs: All / New / Saved / Applied / Dismissed — use `.tab-btn` style
- Source dropdown: All Sources / wellfound / remoteok / ycjobs / arc / builtin / wwr
- Min score slider: 0–10
- Text search: filters title + company client-side

### Job table columns

| Column | Notes |
|--------|-------|
| Score | Color coded: ≥8 green, 5–7 amber, <5 red. JetBrains Mono. |
| Title | Truncate at 40 chars |
| Company | Plain text |
| Source | Badge pill (color per source) |
| Salary | `$120k–$150k` or `—` if null. JetBrains Mono. |
| Posted | Relative: `2d`, `1w` |
| Actions | `↗` open URL, `★` save, `✓` mark applied, `✕` dismiss |

### Job drawer (click row → slide in from right)

Show full detail: title, company, source badge, salary, tags, match score + reason, notes textarea, status buttons (Save / Applied / Dismiss), direct link button.

---

## Environment variables

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
CRON_SECRET=          # shared secret to protect cron endpoints from public calls
```

In `vercel.json` cron routes, pass `Authorization: Bearer ${CRON_SECRET}` header check at the start of each handler.

---

## `package.json` key deps

```json
{
  "dependencies": {
    "@supabase/supabase-js": "^2",
    "@anthropic-ai/sdk": "^0.20",
    "cheerio": "^1.0",
    "playwright": "^1.40"
  },
  "devDependencies": {
    "vite": "^5",
    "react": "^18",
    "typescript": "^5"
  }
}
```

---

## Acceptance checklist

- [ ] `GET /api/jobs` returns paginated listings from Supabase
- [ ] `POST /api/scrape` fetches RemoteOK JSON API (simplest board) successfully and inserts new rows
- [ ] `POST /api/score` calls Claude API and writes `match_score` + `match_reason` to rows
- [ ] Vercel cron triggers both routes Mon–Sat at 08:00 / 08:30 UTC
- [ ] Dashboard loads and shows stat cards + table
- [ ] Filter bar filters by status, source, min score, and text search
- [ ] Score column color-coded green/amber/red
- [ ] Clicking a row opens the job drawer
- [ ] Actions (save / applied / dismiss) update row status via Supabase
- [ ] Page bg `#09090B`, panels `#18181B`, ocean-blue tab buttons, Inter + JetBrains Mono fonts
- [ ] No Tailwind, no Ant Design — plain CSS only
