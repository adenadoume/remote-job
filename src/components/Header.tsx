interface Props {
  onRefresh: () => void
  loading: boolean
  lastFetched: Date | null
  total: number
}

export default function Header({ onRefresh, loading, lastFetched, total }: Props) {
  return (
    <header>
      <div>
        <h1>Remote Jobs</h1>
        <div className="sub">
          {lastFetched
            ? `${total} listings · refreshed ${lastFetched.toLocaleTimeString()}`
            : 'Remote job listings — scored by DeepSeek'}
        </div>
      </div>
      <div className="header-actions">
        <button className="btn" onClick={onRefresh} disabled={loading}>
          {loading ? <span className="spinner" /> : '↻'}
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
    </header>
  )
}
