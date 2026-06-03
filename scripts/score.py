#!/usr/bin/env python3
"""
Score unscored job listings using DeepSeek V4 API.
Run 30 min after scrape: 30 08 * * 1-6 python3 /opt/jobs/score.py
Processes up to 20 listings per run.
"""

import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_SERVICE_ROLE_KEY']
DEEPSEEK_KEY  = os.environ['DEEPSEEK_API_KEY']

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

deepseek = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url='https://api.deepseek.com',
)

PROMPT_TEMPLATE = """\
You are evaluating a remote job listing for this candidate:

CANDIDATE PROFILE:
- 15+ years experience: supply chain IT, backend engineering, hospitality ops
- Skills: Python, FastAPI, PostgreSQL, Supabase, React, Docker, Linux
- AI tools: Claude Code, MCP, AI Agents, Anthropic API
- ERP: SoftOne, EpsilonNet
- Self-taught, transitioning to full backend / AI engineering roles
- Enrolled in MSc Data Management (Hellenic Open University):
    DAMA501 — statistics, linear algebra, ML foundations
    DAMA503 — Python for data, SQL, Jupyter
- Target: remote, $80k+, startup or AI-focused company
- Strong: system architecture, ERP integrations, workflow automation, full lifecycle ownership
- Actively targeting: AI systems, agent orchestration, production ML, data engineering, AI integration

SCORING GUIDANCE:
- +1 bonus if role involves: data engineering, analytics engineering, MLOps, data pipelines (aligns with MSc)
- +1 bonus if title includes: AI Engineer, Data Engineer, ML Engineer, Agent, LLM, Integration Engineer
- 10 = Python/FastAPI/AI, remote, $80k+, startup, high growth
- 0 = no relevant match

JOB LISTING:
Title:   {title}
Company: {company}
Source:  {source}
Salary:  {salary}
Tags:    {tags}
URL:     {url}

Respond ONLY with valid JSON, no markdown fences:
{{"score": <0-10>, "reason": "<one sentence, max 20 words>"}}"""


def score_job(job: dict) -> tuple[int, str]:
    salary = (
        f"${job['salary_min']}–${job['salary_max']}"
        if job.get('salary_min') else 'not shown'
    )
    prompt = PROMPT_TEMPLATE.format(
        title=job['title'],
        company=job['company'],
        source=job['source'],
        salary=salary,
        tags=', '.join(job.get('tags') or []),
        url=job['url'],
    )
    resp = deepseek.chat.completions.create(
        model='deepseek-chat',
        max_tokens=128,
        temperature=0.1,
        messages=[{'role': 'user', 'content': prompt}],
    )
    raw = resp.choices[0].message.content.strip()
    # Strip any accidental markdown fences
    raw = raw.strip('`').strip()
    if raw.startswith('json'):
        raw = raw[4:].strip()
    data = json.loads(raw)
    return int(data['score']), str(data['reason'])


def main():
    result = (
        supabase.table('job_listings')
        .select('id, title, company, source, salary_min, salary_max, tags, url')
        .is_('match_score', 'null')
        .limit(20)
        .execute()
    )
    jobs = result.data
    if not jobs:
        print('No unscored listings found.')
        return

    print(f'Scoring {len(jobs)} listings…\n')
    scored = 0
    for job in jobs:
        try:
            score, reason = score_job(job)
            supabase.table('job_listings').update({
                'match_score':  score,
                'match_reason': reason,
            }).eq('id', job['id']).execute()
            bar = '█' * score + '░' * (10 - score)
            print(f'  {score:2}/10  [{bar}]  {job["title"][:40]:40}  {job["company"]}')
            scored += 1
        except Exception as e:
            print(f'  ERROR {job["id"]}: {e}', file=sys.stderr)

    print(f'\nDone: {scored}/{len(jobs)} scored')


if __name__ == '__main__':
    main()
