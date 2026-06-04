import { useState, useEffect, useMemo, useCallback } from 'react'
import { supabase } from './lib/supabase'
import Header from './components/Header'
import StatCards from './components/StatCards'
import FilterBar, { PAID_SOURCES } from './components/FilterBar'
import JobTable from './components/JobTable'
import JobDrawer from './components/JobDrawer'
import KepeasPage from './pages/KepeasPage'
import type { JobListing, JobFilters, Stats } from './types'

const DEFAULT_FILTERS: JobFilters = { status: 'all', source: '', min_score: 0, search: '', free_only: false }

function defaultMode(): 'jobs' | 'kepea' {
  if (typeof window !== 'undefined') {
    if (window.location.hostname === 'kepea.agop.pro') return 'kepea'
    if (window.location.hash === '#kepea') return 'kepea'
  }
  return 'jobs'
}

export default function App() {
  const [mode, setMode] = useState<'jobs' | 'kepea'>(defaultMode)

  // ── Jobs mode state ────────────────────────────────────────────────
  const [jobs, setJobs] = useState<JobListing[]>([])
  const [loading, setLoading] = useState(true)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS)
  const [selected, setSelected] = useState<JobListing | null>(null)
  const [collapsed, setCollapsed] = useState(false)

  const fetchJobs = useCallback(async () => {
    setLoading(true)
    const { data, error } = await supabase
      .from('job_listings')
      .select('*')
      .order('match_score', { ascending: false, nullsFirst: false })
      .order('scraped_at', { ascending: false })
      .limit(500)
    if (!error && data) {
      setJobs(data as JobListing[])
      setLastFetched(new Date())
    }
    setLoading(false)
  }, [])

  useEffect(() => { if (mode === 'jobs') fetchJobs() }, [fetchJobs, mode])

  const filteredJobs = useMemo(() => {
    let r = jobs
    if (filters.status !== 'all') r = r.filter(j => j.status === filters.status)
    if (filters.source)           r = r.filter(j => j.source === filters.source)
    if (filters.min_score > 0)    r = r.filter(j => (j.match_score ?? 0) >= filters.min_score)
    if (filters.search) {
      const q = filters.search.toLowerCase()
      r = r.filter(j => j.title.toLowerCase().includes(q) || j.company.toLowerCase().includes(q))
    }
    if (filters.free_only) r = r.filter(j => !PAID_SOURCES.has(j.source))
    return r
  }, [jobs, filters])

  const stats = useMemo<Stats>(() => {
    const scored = jobs.filter(j => j.match_score !== null)
    return {
      total:    jobs.length,
      newCount: jobs.filter(j => j.status === 'new').length,
      saved:    jobs.filter(j => j.status === 'saved').length,
      applied:  jobs.filter(j => j.status === 'applied').length,
      avgScore: scored.length
        ? (scored.reduce((s, j) => s + j.match_score!, 0) / scored.length).toFixed(1)
        : '—',
    }
  }, [jobs])

  const updateJob = useCallback(async (id: string, updates: Partial<JobListing>) => {
    const { error } = await supabase.from('job_listings').update(updates).eq('id', id)
    if (!error) {
      setJobs(prev => prev.map(j => j.id === id ? { ...j, ...updates } : j))
      setSelected(prev => prev?.id === id ? { ...prev, ...updates } : prev)
    }
  }, [])

  // ── Mode switcher (only show on job.agop.pro, not kepea.agop.pro) ──
  const showSwitcher = typeof window !== 'undefined' && window.location.hostname !== 'kepea.agop.pro'

  if (mode === 'kepea') {
    return <KepeasPage onSwitchMode={showSwitcher ? () => setMode('jobs') : undefined} />
  }

  return (
    <div className="app-root animate-fade-in">
      <Header
        onRefresh={fetchJobs}
        loading={loading}
        lastFetched={lastFetched}
        total={jobs.length}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(c => !c)}
        extraAction={showSwitcher
          ? <button className="btn" onClick={() => setMode('kepea')}>🇬🇷 KEPEA</button>
          : undefined}
      />
      {!collapsed && <div className="cards stagger-children"><StatCards stats={stats} /></div>}
      {!collapsed && <FilterBar filters={filters} onChange={setFilters} />}
      <JobTable
        jobs={filteredJobs}
        loading={loading}
        onRowClick={setSelected}
        onStatusUpdate={(id, status) => updateJob(id, { status: status as JobListing['status'] })}
      />
      {selected && (
        <JobDrawer
          job={selected}
          onClose={() => setSelected(null)}
          onUpdate={updates => updateJob(selected.id, updates)}
        />
      )}
    </div>
  )
}
