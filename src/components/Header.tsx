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
  const [scraping, setScraping] = useState(false)
  const [scoring, setScoring] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  async function trigger(endpoint: string, setLoading: (b: boolean) => void) {
    setLoading(true)
    setFeedback(null)
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${endpoint}`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        const line = data.output?.split('\n').pop() ?? 'Done'
        setFeedback(line)
        onRefresh()
      } else {
        setFeedback(data.error ?? 'Failed')
      }
    } catch {
      setFeedback('Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <header>
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
          {feedback && <div className="sub" style={{ color: '#4ade80' }}>{feedback}</div>}
        </div>
      </div>

      <div className="header-actions">
        <button className="btn" onClick={onRefresh} disabled={loading || scraping || scoring}>
          {loading ? <span className="spinner" /> : '↻'}
          <span className="btn-label">Refresh</span>
        </button>
        <button className="btn" onClick={() => trigger('scrape', setScraping)} disabled={scraping || loading || scoring}>
          {scraping ? <span className="spinner" /> : '⬇'}
          <span className="btn-label">Scrape</span>
        </button>
        <button className="btn" onClick={() => trigger('score', setScoring)} disabled={scoring || loading || scraping}>
          {scoring ? <span className="spinner" /> : '★'}
          <span className="btn-label">Score</span>
        </button>
      </div>
    </header>
  )
}
