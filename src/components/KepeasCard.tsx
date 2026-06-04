import { useState } from 'react'
import { supabase } from '../lib/supabase'
import type { KepeasListing } from '../types'

interface Props {
  listing: KepeasListing
  onStatusChange: (id: string, status: KepeasListing['status']) => void
  onUpdate: (id: string, fields: Partial<KepeasListing>) => void
}

const EDITABLE_FIELDS: { key: keyof KepeasListing; label: string; multiline?: boolean }[] = [
  { key: 'title',         label: 'Τίτλος',                  multiline: true },
  { key: 'employer',      label: 'Φορέας' },
  { key: 'positions',     label: 'Αριθμός Θέσεων' },
  { key: 'specialty',     label: 'Ειδικότητα' },
  { key: 'location',      label: 'Έδρα' },
  { key: 'posted_at',     label: 'Ημερομηνία Δημοσίευσης' },
  { key: 'deadline',      label: 'Καταληκτική Ημερομηνία' },
  { key: 'contract_type', label: 'Τύπος Σύμβασης' },
  { key: 'requirements',  label: 'Απαιτούμενα Προσόντα',   multiline: true },
  { key: 'description',   label: 'Περιγραφή',               multiline: true },
]

export default function KepeasCard({ listing: job, onStatusChange, onUpdate }: Props) {
  const [copied, setCopied]     = useState<string | null>(null)
  const [allCopied, setAllCopied] = useState(false)
  const [editing, setEditing]   = useState(false)
  const [draft, setDraft]       = useState<Record<string, string>>({})
  const [saving, setSaving]     = useState(false)

  function copyField(key: string, value: string) {
    if (!value) return
    navigator.clipboard.writeText(value).then(() => {
      setCopied(key)
      setTimeout(() => setCopied(null), 900)
    })
  }

  function copyAll() {
    const lines = [
      job.title         && `Τίτλος Θέσης: ${job.title}`,
      job.employer      && `Φορέας: ${job.employer}`,
      job.positions     && `Αριθμός Θέσεων: ${job.positions}`,
      job.specialty     && `Ειδικότητα: ${job.specialty}`,
      job.location      && `Έδρα: ${job.location}`,
      job.posted_at     && `Ημερομηνία Δημοσίευσης: ${job.posted_at}`,
      job.deadline      && `Καταληκτική Ημερομηνία: ${job.deadline}`,
      job.contract_type && `Τύπος Σύμβασης: ${job.contract_type}`,
      job.requirements  && `Απαιτούμενα Προσόντα: ${job.requirements}`,
      job.description   && `Περιγραφή: ${job.description}`,
      job.url           && `Σύνδεσμος: ${job.url}`,
    ].filter(Boolean).join('\n')

    navigator.clipboard.writeText(lines).then(() => {
      setAllCopied(true)
      setTimeout(() => setAllCopied(false), 1200)
    })
  }

  async function setStatus(status: KepeasListing['status']) {
    await supabase.from('kepea_listings').update({ status }).eq('id', job.id)
    onStatusChange(job.id, status)
  }

  function startEdit() {
    const d: Record<string, string> = {}
    for (const { key } of EDITABLE_FIELDS) {
      d[key as string] = (job[key] as string | null) ?? ''
    }
    setDraft(d)
    setEditing(true)
  }

  async function saveEdit() {
    setSaving(true)
    const updates: Partial<KepeasListing> = {}
    for (const { key } of EDITABLE_FIELDS) {
      updates[key] = (draft[key as string] || null) as never
    }
    await supabase.from('kepea_listings').update(updates).eq('id', job.id)
    onUpdate(job.id, updates)
    setSaving(false)
    setEditing(false)
  }

  function cancelEdit() {
    setEditing(false)
    setDraft({})
  }

  if (editing) {
    return (
      <div className={`kepea-card kepea-card-editing`}>
        <div className="kepea-card-header">
          <div className="kepea-source-badge">{job.source ?? '—'}</div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>✏ Διόρθωση πεδίων</div>
        </div>
        <div className="kepea-edit-fields">
          {EDITABLE_FIELDS.map(({ key, label, multiline }) => (
            <div key={key as string} className="kepea-edit-row">
              <label className="kepea-field-label">{label}</label>
              {multiline ? (
                <textarea
                  className="kepea-edit-input"
                  rows={3}
                  value={draft[key as string] ?? ''}
                  onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
                />
              ) : (
                <input
                  className="kepea-edit-input"
                  type="text"
                  value={draft[key as string] ?? ''}
                  onChange={e => setDraft(d => ({ ...d, [key]: e.target.value }))}
                />
              )}
            </div>
          ))}
        </div>
        <div className="kepea-card-footer">
          <button className="btn btn-primary" onClick={saveEdit} disabled={saving}>
            {saving ? <span className="spinner" /> : '✓ Αποθήκευση'}
          </button>
          <button className="btn" onClick={cancelEdit} disabled={saving}>✕ Ακύρωση</button>
        </div>
      </div>
    )
  }

  function Field({ label, value, fieldKey }: { label: string; value: string | null | undefined; fieldKey: string }) {
    if (!value) return null
    const isCopied = copied === fieldKey
    return (
      <div
        className={`kepea-field${isCopied ? ' copied' : ''}`}
        onClick={() => copyField(fieldKey, value)}
        title="Click to copy"
      >
        <div className="kepea-field-label">{label}</div>
        <div className="kepea-field-value">{value}</div>
      </div>
    )
  }

  return (
    <div className={`kepea-card${job.status === 'uploaded' ? ' kepea-card-uploaded' : job.status === 'skipped' ? ' kepea-card-skipped' : ''}`}>
      <div className="kepea-card-header">
        <div className="kepea-source-badge">{job.source ?? '—'}</div>
        {job.deadline && (
          <div className="kepea-deadline">⏰ {job.deadline}</div>
        )}
        <button className="btn-icon" onClick={startEdit} title="Διόρθωση πεδίων">✏</button>
      </div>

      <div className="kepea-title">{job.title ?? '—'}</div>

      <div className="kepea-fields">
        <Field label="Φορέας"                   value={job.employer}      fieldKey="employer" />
        <Field label="Αριθμός Θέσεων"           value={job.positions}     fieldKey="positions" />
        <Field label="Ειδικότητα"               value={job.specialty}     fieldKey="specialty" />
        <Field label="Έδρα"                      value={job.location}      fieldKey="location" />
        <Field label="Ημερομηνία Δημοσίευσης"   value={job.posted_at}     fieldKey="posted_at" />
        <Field label="Τύπος Σύμβασης"           value={job.contract_type} fieldKey="contract_type" />
        <Field label="Απαιτούμενα Προσόντα"     value={job.requirements}  fieldKey="requirements" />
        <Field label="Περιγραφή"                value={job.description}   fieldKey="description" />
      </div>

      {job.url && (
        <div className="kepea-link-row">
          <a href={job.url} target="_blank" rel="noopener noreferrer" className="kepea-link">
            ↗ Σύνδεσμος Προκήρυξης
          </a>
        </div>
      )}

      {job.pdf_urls && job.pdf_urls.length > 0 && (
        <div className="kepea-pdfs">
          {job.pdf_urls.map((pdf, i) => (
            <a key={i} href={pdf} target="_blank" rel="noopener noreferrer" className="kepea-pdf-link">
              📄 PDF {i + 1}
            </a>
          ))}
        </div>
      )}

      <div className="kepea-card-footer">
        <button className={`btn${allCopied ? ' btn-applied' : ''}`} onClick={copyAll}>
          {allCopied ? '✓ Αντιγράφηκε!' : '⎘ Αντιγραφή Όλων'}
        </button>
        <button className="btn btn-applied" onClick={() => setStatus('uploaded')}>✓ Καταχωρήθηκε</button>
        <button className="btn btn-dismiss" onClick={() => setStatus('skipped')}>✕ Παράλειψη</button>
        {job.status !== 'new' && (
          <button className="btn" onClick={() => setStatus('new')}>↩ Νέο</button>
        )}
      </div>
    </div>
  )
}
