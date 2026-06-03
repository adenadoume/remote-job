import type { JobFilters } from '../types'

const STATUSES = ['all', 'new', 'saved', 'applied', 'dismissed']
const SOURCES  = ['remoteok', 'wwr', 'wellfound', 'ycjobs', 'arc', 'builtin']

interface Props {
  filters: JobFilters
  onChange: (f: JobFilters) => void
}

export default function FilterBar({ filters, onChange }: Props) {
  const set = <K extends keyof JobFilters>(key: K, val: JobFilters[K]) =>
    onChange({ ...filters, [key]: val })

  return (
    <div className="filter-bar">
      <div className="filter-row">
        {STATUSES.map(s => (
          <button
            key={s}
            className={`tab-btn${filters.status === s ? ' active' : ''}`}
            onClick={() => set('status', s)}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}

        <select value={filters.source} onChange={e => set('source', e.target.value)}>
          <option value="">All Sources</option>
          {SOURCES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <label>
          Score ≥ {filters.min_score}
          <input
            type="range"
            className="score-slider"
            min={0} max={10} step={1}
            value={filters.min_score}
            onChange={e => set('min_score', +e.target.value)}
          />
        </label>
      </div>

      <div className="filter-row">
        <input
          className="search-input"
          type="text"
          placeholder="Search title or company…"
          value={filters.search}
          onChange={e => set('search', e.target.value)}
        />
      </div>
    </div>
  )
}
