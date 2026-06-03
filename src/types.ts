export interface JobListing {
  id: string
  url: string
  title: string
  company: string
  source: 'remoteok' | 'wwr' | 'wellfound' | 'ycjobs' | 'arc' | 'builtin' | string
  salary_min: number | null
  salary_max: number | null
  tags: string[] | null
  posted_at: string | null
  scraped_at: string
  match_score: number | null
  match_reason: string | null
  status: 'new' | 'saved' | 'applied' | 'dismissed'
  notes: string | null
}

export interface Stats {
  total: number
  newCount: number
  saved: number
  applied: number
  avgScore: string
}

export interface JobFilters {
  status: string
  source: string
  min_score: number
  search: string
}
