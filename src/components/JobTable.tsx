import type { JobListing } from '../types'

function scoreClass(s: number | null) {
  if (s === null) return 'none'
  if (s >= 8) return 'high'
  if (s >= 5) return 'mid'
  return 'low'
}

function formatSalary(min: number | null, max: number | null) {
  if (!min) return '—'
  const k = (n: number) => `$${Math.round(n / 1000)}k`
  return max ? `${k(min)}–${k(max)}` : k(min)
}

function relativeTime(iso: string | null) {
  if (!iso) return '—'
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days === 0) return 'today'
  if (days < 7) return `${days}d`
  const w = Math.floor(days / 7)
  if (w < 5) return `${w}w`
  return `${Math.floor(w / 4)}mo`
}

function trunc(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

interface Props {
  jobs: JobListing[]
  loading: boolean
  onRowClick: (job: JobListing) => void
  onStatusUpdate: (id: string, status: string) => void
}

export default function JobTable({ jobs, loading, onRowClick, onStatusUpdate }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Score</th>
            <th>Title</th>
            <th>Company</th>
            <th>Source</th>
            <th>Salary</th>
            <th>Posted</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={7} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                <span className="animate-pulse-soft">Loading listings…</span>
              </td>
            </tr>
          )}
          {!loading && jobs.length === 0 && (
            <tr>
              <td colSpan={7}>
                <div className="empty-state">
                  <div className="empty-icon">🔍</div>
                  <p>No listings match your filters</p>
                </div>
              </td>
            </tr>
          )}
          {!loading && jobs.map(job => (
            <tr key={job.id} onClick={() => onRowClick(job)}>
              <td>
                <span className={`score ${scoreClass(job.match_score)}`}>
                  {job.match_score !== null ? `${job.match_score}/10` : '—'}
                </span>
              </td>
              <td title={job.title}>{trunc(job.title, 45)}</td>
              <td style={{ color: 'var(--text-muted)' }}>{job.company}</td>
              <td>
                <span className={`source-badge source-${job.source}`}>{job.source}</span>
              </td>
              <td className="mono">{formatSalary(job.salary_min, job.salary_max)}</td>
              <td className="mono" style={{ color: 'var(--text-muted)' }}>
                {relativeTime(job.posted_at ?? job.scraped_at)}
              </td>
              <td onClick={e => e.stopPropagation()}>
                <div className="actions-cell">
                  <button className="btn-icon open-link" title="Open"
                    onClick={() => window.open(job.url, '_blank', 'noopener')}>↗</button>
                  <button className="btn-icon save" title="Save"
                    onClick={() => onStatusUpdate(job.id, 'saved')}>★</button>
                  <button className="btn-icon apply" title="Applied"
                    onClick={() => onStatusUpdate(job.id, 'applied')}>✓</button>
                  <button className="btn-icon dismiss" title="Dismiss"
                    onClick={() => onStatusUpdate(job.id, 'dismissed')}>✕</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
