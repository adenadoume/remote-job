#!/usr/bin/env python3
"""One-time script: normalise deadline and posted_at for all existing kepea_listings rows."""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from supabase import create_client
from kepea_scrape import normalize_date

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

res = sb.table('kepea_listings').select('id,deadline,posted_at').execute()
rows = res.data or []
print(f'Found {len(rows)} rows to fix')

fixed = 0
for row in rows:
    new_dl  = normalize_date(row.get('deadline')  or '')
    new_pa  = normalize_date(row.get('posted_at') or '')
    if new_dl != (row.get('deadline') or '') or new_pa != (row.get('posted_at') or ''):
        sb.table('kepea_listings').update({'deadline': new_dl, 'posted_at': new_pa}).eq('id', row['id']).execute()
        print(f'  {row["id"][:8]}  deadline: {row["deadline"]!r} → {new_dl!r}  posted_at: {row["posted_at"]!r} → {new_pa!r}')
        fixed += 1

print(f'\nFixed {fixed} rows.')
