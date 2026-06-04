import { useState, useEffect, useCallback } from 'react'
import { supabase } from '../lib/supabase'
import KepeasCard from '../components/KepeasCard'
import KepeasSources from '../components/KepeasSources'
import type { KepeasListing, KepeasFilters } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'https://agop-os.agop.pro'
const STATUSES = ['all', 'new', 'uploaded', 'skipped']

interface Props {
  onSwitchMode?: () => void
}

export default function KepeasPage({ onSwitchMode }: Props) {
  const [listings, setListings] = useState<KepeasListing[]>([])
  const [loading, setLoading]   = useState(true)
  const [scraping, setScraping] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [lastFetched, setLastFetched] = useState<Date | null>(null)
  const [filters, setFilters]   = useState<KepeasFilters>({ status: 'new', search: '' })
  const [showSources, setShowSources] = useState(false)

  const fetchListings = useCallback(async () => {
    setLoading(true)
    const { data, error } = await supabase
      .from('kepea_listings')
      .select('*')
      .order('scraped_at', { ascending: false })
      .limit(300)
    if (!error && data) {
      setListings(data as KepeasListing[])
      setLastFetched(new Date())
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchListings() }, [fetchListings])

  async function triggerScrape() {
    setScraping(true)
    setFeedback(null)
    try {
      const res  = await fetch(`${API_BASE}/api/kepea/scrape`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        const out = data.output?.split('\n').pop()?.trim() ?? 'Done'
        setFeedback(`✓ ${out}`)
        await fetchListings()
      } else {
        setFeedback(data.errors?.split('\n').pop() ?? 'Scrape failed')
      }
    } catch {
      setFeedback('Network error')
    } finally {
      setScraping(false)
    }
  }

  function updateStatus(id: string, status: KepeasListing['status']) {
    setListings(prev => prev.map(l => l.id === id ? { ...l, status } : l))
  }

  const filtered = listings.filter(l => {
    if (filters.status !== 'all' && l.status !== filters.status) return false
    if (filters.search) {
      const q = filters.search.toLowerCase()
      return (
        (l.title ?? '').toLowerCase().includes(q) ||
        (l.employer ?? '').toLowerCase().includes(q) ||
        (l.specialty ?? '').toLowerCase().includes(q)
      )
    }
    return true
  })

  const counts = {
    all:      listings.length,
    new:      listings.filter(l => l.status === 'new').length,
    uploaded: listings.filter(l => l.status === 'uploaded').length,
    skipped:  listings.filter(l => l.status === 'skipped').length,
  }

  return (
    <div className="kepea-page animate-fade-in">
      {/* Header */}
      <div className="kepea-header">
        <div>
          <h1>🇬🇷 KEPEA — Θέσεις Εργασίας</h1>
          <div className="sub">
            {lastFetched
              ? `${listings.length} θέσεις · ${lastFetched.toLocaleTimeString()}`
              : 'Ελληνικές αγγελίες εργασίας'}
          </div>
          {feedback && (
            <div className="sub" style={{ color: feedback.startsWith('✓') ? '#4ade80' : '#f87171' }}>
              {feedback}
            </div>
          )}
        </div>
        <div className="header-actions">
          <button className="btn" onClick={() => setShowSources(s => !s)}>
            ⚙ Πηγές
          </button>
          <button className="btn" onClick={fetchListings} disabled={loading || scraping}>
            {loading ? <span className="spinner" /> : '↻'}
            <span className="btn-label">Refresh</span>
          </button>
          <button className="btn btn-primary" onClick={triggerScrape} disabled={scraping || loading}>
            {scraping ? <span className="spinner" /> : '⬇'}
            <span className="btn-label">Scrape</span>
          </button>
          {onSwitchMode && (
            <button className="btn" onClick={onSwitchMode}>💼 Remote Jobs</button>
          )}
        </div>
      </div>

      {/* Sources manager */}
      {showSources && <KepeasSources onClose={() => setShowSources(false)} />}

      {/* Filter bar */}
      <div className="kepea-filter-bar">
        {STATUSES.map(s => (
          <button
            key={s}
            className={`tab-btn${filters.status === s ? ' active' : ''}`}
            onClick={() => setFilters(f => ({ ...f, status: s }))}
          >
            {s === 'all' ? 'Όλα' : s === 'new' ? 'Νέα' : s === 'uploaded' ? 'Καταχωρήθηκαν' : 'Παραλείφθηκαν'}
            <span style={{ marginLeft: 5, opacity: 0.7, fontSize: 11 }}>
              {counts[s as keyof typeof counts]}
            </span>
          </button>
        ))}
        <input
          className="search-input"
          type="text"
          placeholder="Αναζήτηση…"
          value={filters.search}
          onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
          style={{ maxWidth: 220 }}
        />
      </div>

      {/* Cards grid */}
      <div className="kepea-scroll">
        {loading && (
          <div className="empty-state"><p className="animate-pulse-soft">Φόρτωση…</p></div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">🔍</div>
            <p>Δεν βρέθηκαν θέσεις εργασίας</p>
          </div>
        )}
        {!loading && filtered.length > 0 && (
          <div className="kepea-grid">
            {filtered.map(l => (
              <KepeasCard key={l.id} listing={l} onStatusChange={updateStatus} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
