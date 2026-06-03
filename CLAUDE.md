# Remote Job App — Claude Instructions

## CRITICAL: Update handoff after every session

At the end of every conversation that changes anything in this project — code, config, decisions, bugs fixed, features added — you MUST update `remotejob-handoff.md`:

1. Update the **"Last updated"** date at the top
2. Update **"Status"** to reflect current state
3. Add or update sections for anything that changed
4. Update the **"What Is NOT Done Yet"** checklist
5. Add new decisions to **"Decisions Made"** with date

This file is the primary handoff document. Another AI or Claude session may pick up this project cold — the handoff file is their only context.

## Stack

- **Frontend:** Vite + React 18 + TypeScript — plain CSS (`globals.css`), no Tailwind, no Ant Design
- **Database:** Supabase (PostgreSQL) — frontend uses anon key directly via `@supabase/supabase-js`
- **Scraping + Scoring:** Python scripts on Oracle VM (`scripts/scrape.py`, `scripts/score.py`)
- **Scraping:** requests + Firecrawl API for JS-rendered pages
- **Scoring:** DeepSeek V4 via `openai` Python package (`base_url=https://api.deepseek.com`)
- **Deploy:** Vercel (frontend only, no serverless functions)

## Design rules

- No Tailwind, no Ant Design, no component libraries
- All styles in `src/styles/globals.css` only
- Match internal app family: `#09090B` page, `#18181B` panels, ocean-blue controls
- Fonts: Inter (UI) + JetBrains Mono (numbers/scores) — Google Fonts
- Font sizes: 15px body, 14px table cells, 22px card values, 12px card labels, 13px buttons
- Animations: `fade-in`, `slide-up`, `stagger-children` from globals.css

## Key files

| File | Purpose |
|------|---------|
| `src/App.tsx` | All state + Supabase queries |
| `src/types.ts` | JobListing, Stats, JobFilters |
| `src/lib/supabase.ts` | Supabase client (anon key) |
| `src/styles/globals.css` | All styles |
| `scripts/scrape.py` | Oracle VM scraper |
| `scripts/score.py` | Oracle VM DeepSeek scorer |
| `remotejob-handoff.md` | Full project handoff (always update) |

## Env vars

Frontend (Vercel): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`  
VM scripts: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DEEPSEEK_API_KEY`, `FIRECRAWL_API_KEY`
