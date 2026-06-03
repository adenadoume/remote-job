import { useState, useEffect } from 'react'
import type { JobListing } from '../types'

function scoreClass(s: number | null) {
  if (s === null) return 'none'
  if (s >= 8) return 'high'
  if (s >= 5) return 'mid'
  return 'low'
}

function formatSalary(min: number | null, max: number | null) {
  if (!min) return 'Not shown'
  const fmt = (n: number) => `$${n.toLocaleString()}`
  return max ? `${fmt(min)} – ${fmt(max)} / yr` : `${fmt(min)} / yr`
}

interface Props {
  job: JobListing
  onClose: () => void
  onUpdate: (updates: Partial<JobListing>) => void
}

export default function JobDrawer({ job, onClose, onUpdate }: Props) {
  const [notes, setNotes] = useState(job.notes ?? '')

  useEffect(() => { setNotes(job.notes ?? '') }, [job.id])

  function saveNotes() {
    if (notes !== (job.notes ?? '')) onUpdate({ notes })
  }

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-header">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="drawer-title">{job.title}</div>
            <div className="drawer-company">{job.company}</div>
          </div>
          <button className="btn-icon" onClick={onClose}
            style={{ fontSize: 20, flexShrink: 0, marginTop: -2 }}>✕</button>
        </div>

        <div className="drawer-body">
          <div>
            <div className="drawer-field-label">Source / Status</div>
            <span className={`source-badge source-${job.source}`}>{job.source}</span>
            <span style={{ marginLeft: 10, fontSize: 13, color: 'var(--text-muted)' }}>
              {job.status}
            </span>
          </div>

          <div>
            <div className="drawer-field-label">Salary</div>
            <div className="drawer-field-value mono">
              {formatSalary(job.salary_min, job.salary_max)}
            </div>
          </div>

          <div>
            <div className="drawer-field-label">Match Score</div>
            <span className={`score ${scoreClass(job.match_score)}`}
              style={{ fontSize: 15 }}>
              {job.match_score !== null ? `${job.match_score}/10` : 'Unscored'}
            </span>
          </div>

          {job.match_reason && (
            <div>
              <div className="drawer-field-label">Score Reason</div>
              <div className="drawer-reason">{job.match_reason}</div>
            </div>
          )}

          {job.tags && job.tags.length > 0 && (
            <div>
              <div className="drawer-field-label">Tags</div>
              <div className="drawer-tags">
                {job.tags.map(t => <span key={t} className="drawer-tag">{t}</span>)}
              </div>
            </div>
          )}

          <div>
            <div className="drawer-field-label">Notes</div>
            <textarea
              className="drawer-notes"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              onBlur={saveNotes}
              placeholder="Add notes…"
            />
          </div>
        </div>

        <div className="drawer-footer">
          <button className="btn btn-save"    onClick={() => onUpdate({ status: 'saved' })}>★ Save</button>
          <button className="btn btn-applied" onClick={() => onUpdate({ status: 'applied' })}>✓ Applied</button>
          <button className="btn btn-dismiss" onClick={() => onUpdate({ status: 'dismissed' })}>✕ Dismiss</button>
          <a href={job.url} target="_blank" rel="noopener noreferrer"
            className="btn btn-link-ext">↗ Open</a>
        </div>
      </div>
    </>
  )
}
