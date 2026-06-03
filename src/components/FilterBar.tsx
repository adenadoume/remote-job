import type { JobFilters } from '../types'

const STATUSES = ['all', 'new', 'saved', 'applied', 'dismissed']

// source → subscription cost required to APPLY (null = free to apply)
export const SOURCE_COST: Record<string, string | null> = {
  remoteok:  '$299/mo',
  remotive:  null,
  himalayas: null,
  wwr:       null,
  wellfound: null,
  ycjobs:    null,
  arc:       null,
  builtin:   null,
  manual:    null,
}

export const PAID_SOURCES = new Set(Object.entries(SOURCE_COST).filter(([, v]) => v !== null).map(([k]) => k))

const SOURCES = Object.keys(SOURCE_COST)

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
          {SOURCES.map(s => (
            <option key={s} value={s}>
              {s}{SOURCE_COST[s] ? ` 💳` : ''}
            </option>
          ))}
        </select>

        {/* Free-only toggle */}
        <button
          className={`tab-btn${filters.free_only ? ' active' : ''}`}
          onClick={() => set('free_only', !filters.free_only)}
          title="Hide job boards that require a paid subscription to apply"
        >
          {filters.free_only ? '✓ Free only' : 'Free only'}
        </button>

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
