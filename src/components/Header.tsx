import { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'https://agop-os.agop.pro'

interface Props {
  onRefresh: () => void
  loading: boolean
  lastFetched: Date | null
  total: number
  collapsed: boolean
  onToggleCollapse: () => void
}

export default function Header({ onRefresh, loading, lastFetched, total, collapsed, onToggleCollapse }: Props) {
  const [scraping, setScraping]   = useState(false)
  const [scoring, setScoring]     = useState(false)
  const [adding, setAdding]       = useState(false)
  const [addUrl, setAddUrl]       = useState('')
  const [feedback, setFeedback]   = useState<string | null>(null)

  const busy = loading || scraping || scoring || adding

  async function trigger(endpoint: string, setLoading: (b: boolean) => void, body?: Record<string, string>) {
    setLoading(true)
    setFeedback(null)
    try {
      const params = body ? '?' + new URLSearchParams(body).toString() : ''
      const res = await fetch(`${API_BASE}/api/jobs/${endpoint}${params}`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        // add-url returns JSON in output; scrape/score return plain text
        let msg = data.output?.split('\n').pop()?.trim() ?? 'Done'
        try {
          const parsed = JSON.parse(data.output ?? '')
          if (parsed.inserted != null) msg = `✓ ${parsed.inserted} new from ${parsed.source}`
        } catch { /* plain text output — use last line as-is */ }
        setFeedback(`✓ ${msg}`)
        onRefresh()
      } else {
        setFeedback(data.error ?? data.errors?.split('\n').pop() ?? 'Failed')
      }
    } catch {
      setFeedback('Network error')
    } finally {
      setLoading(false)
    }
  }

  async function handleAddUrl() {
    const url = addUrl.trim()
    if (!url.startsWith('http')) { setFeedback('Enter a valid URL'); return }
    await trigger('add-url', setAdding, { url })
    setAddUrl('')
  }

  return (
    <header style={{ flexWrap: 'wrap', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <button
          className="btn-icon"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expand' : 'Collapse'}
          style={{ fontSize: 16, color: 'var(--text-label)', flexShrink: 0 }}
        >
          {collapsed ? '▼' : '▲'}
        </button>
        <div style={{ minWidth: 0 }}>
          <h1>Remote Jobs</h1>
          {!collapsed && (
            <div className="sub">
              {lastFetched
                ? `${total} listings · ${lastFetched.toLocaleTimeString()}`
                : 'Scored by DeepSeek · runs Mon–Sat 08:00 UTC'}
            </div>
          )}
          {feedback && (
            <div className="sub" style={{ color: feedback.startsWith('✓') ? '#4ade80' : '#f87171' }}>
              {feedback}
            </div>
          )}
        </div>
      </div>

      {/* Add URL row */}
      <div className="header-add-url">
        <input
          className="search-input"
          type="url"
          placeholder="Paste job board URL to scrape…"
          value={addUrl}
          onChange={e => setAddUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !busy && handleAddUrl()}
          style={{ minWidth: 240, flex: 1 }}
          disabled={busy}
        />
        <button className="btn btn-primary" onClick={handleAddUrl} disabled={busy || !addUrl.trim()}>
          {adding ? <span className="spinner" /> : '+'}
          <span className="btn-label">Add</span>
        </button>
      </div>

      <div className="header-actions">
        <button className="btn" onClick={onRefresh} disabled={busy}>
          {loading ? <span className="spinner" /> : '↻'}
          <span className="btn-label">Refresh</span>
        </button>
        <button className="btn" onClick={() => trigger('scrape', setScraping)} disabled={busy}>
          {scraping ? <span className="spinner" /> : '⬇'}
          <span className="btn-label">Scrape</span>
        </button>
        <button className="btn" onClick={() => trigger('score', setScoring)} disabled={busy}>
          {scoring ? <span className="spinner" /> : '★'}
          <span className="btn-label">Score</span>
        </button>
      </div>
    </header>
  )
}
