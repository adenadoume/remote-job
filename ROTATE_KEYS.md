# Key Rotation — do this before next session

Exposed via accidental commit of `api-deepseek.md`. File removed from git history.
No business data at risk. DeepSeek balance ~$1.50. Firecrawl on free plan (no card).

---

## 1. Supabase — project `hgqigqmzgdrmkerxkwaa`

**URL:** https://supabase.com/dashboard/project/hgqigqmzgdrmkerxkwaa/settings/api

- [ ] Regenerate **service_role** key
- [ ] Regenerate **anon** key
- [ ] Update on Oracle VM: `nano /opt/jobs/scripts/.env` → replace `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Update on Oracle VM: `nano /home/ubuntu/agop-os-api/.env` → replace `SUPABASE_SERVICE_KEY` and `FOOD_COST_SUPABASE_ANON_KEY`
- [ ] Update Vercel env vars for remote-job: `VITE_SUPABASE_ANON_KEY`
- [ ] Update Vercel env vars for food-cost-app: `VITE_SUPABASE_ANON_KEY`
- [ ] Update local `.env` files:
  - `apps/remote-job/.env`
  - `apps/food-cost-app/.env` (or wherever it lives)

---

## 2. DeepSeek — ~$1.50 at risk

**URL:** https://platform.deepseek.com/api_keys

- [ ] Delete key `sk-15e338f021aa436c9c6ba95d2a14854c`
- [ ] Create new key
- [ ] Update on Oracle VM: `nano /opt/jobs/scripts/.env` → replace `DEEPSEEK_API_KEY`

---

## 3. Firecrawl — free plan, no card, low risk

**URL:** https://www.firecrawl.dev/app/api-keys

- [ ] Regenerate key `fc-a9abb55387f848e7b4b726ccbe887e27`
- [ ] Update on Oracle VM: `nano /opt/jobs/scripts/.env` → replace `FIRECRAWL_API_KEY`

---

## After rotating all keys — restart the service

```bash
ssh oracle-softone "sudo systemctl restart agop-os-api"
```

Then test that scraping still works:

```bash
ssh oracle-softone "cd /opt/jobs/scripts && python3 scrape.py"
```

---

## Why this happened

The file `api-deepseek.md` was in the project root (used as a notes file)
and got accidentally staged and committed. It's been purged from git history.

`.gitignore` now blocks: `*.env`, `api-deepseek.md`, `*-keys.md`, `*-secrets.md`
