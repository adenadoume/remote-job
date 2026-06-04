import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import type { KepeasSource } from '../types'

export default function KepeasSources({ onClose }: { onClose: () => void }) {
  const [sources, setSources]     = useState<KepeasSource[]>([])
  const [newUrl, setNewUrl]       = useState('')
  const [newLabel, setNewLabel]   = useState('')
  const [saving, setSaving]       = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editUrl, setEditUrl]     = useState('')

  useEffect(() => {
    supabase.from('kepea_sources').select('*').order('added_at').then(({ data }) => {
      if (data) setSources(data as KepeasSource[])
    })
  }, [])

  async function toggleEnabled(id: string, enabled: boolean) {
    await supabase.from('kepea_sources').update({ enabled }).eq('id', id)
    setSources(prev => prev.map(s => s.id === id ? { ...s, enabled } : s))
  }

  async function addSource() {
    if (!newUrl.trim() || !newLabel.trim()) return
    setSaving(true)
    const { data, error } = await supabase
      .from('kepea_sources')
      .insert({ url: newUrl.trim(), label: newLabel.trim(), enabled: true })
      .select()
      .single()
    if (!error && data) {
      setSources(prev => [...prev, data as KepeasSource])
      setNewUrl('')
      setNewLabel('')
    }
    setSaving(false)
  }

  function startEdit(src: KepeasSource) {
    setEditingId(src.id)
    setEditLabel(src.label)
    setEditUrl(src.url)
  }

  async function saveEdit(id: string) {
    if (!editLabel.trim() || !editUrl.trim()) return
    await supabase.from('kepea_sources').update({ label: editLabel.trim(), url: editUrl.trim() }).eq('id', id)
    setSources(prev => prev.map(s => s.id === id ? { ...s, label: editLabel.trim(), url: editUrl.trim() } : s))
    setEditingId(null)
  }

  async function deleteSource(id: string) {
    if (!confirm('Διαγραφή πηγής;')) return
    await supabase.from('kepea_sources').delete().eq('id', id)
    setSources(prev => prev.filter(s => s.id !== id))
  }

  return (
    <div className="kepea-sources">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div className="kepea-sources-title">⚙ Διαχείριση Πηγών</div>
        <button className="btn-icon" onClick={onClose}>✕</button>
      </div>

      <div className="kepea-sources-list">
        {sources.map(src => (
          <div key={src.id} className="kepea-source-row">
            {editingId === src.id ? (
              <>
                <input
                  type="text"
                  className="kepea-edit-input"
                  value={editLabel}
                  onChange={e => setEditLabel(e.target.value)}
                  style={{ width: 140 }}
                />
                <input
                  type="url"
                  className="kepea-edit-input"
                  value={editUrl}
                  onChange={e => setEditUrl(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button className="btn-icon" title="Αποθήκευση" onClick={() => saveEdit(src.id)}>✓</button>
                <button className="btn-icon" title="Ακύρωση" onClick={() => setEditingId(null)}>✕</button>
              </>
            ) : (
              <>
                <input
                  type="checkbox"
                  id={src.id}
                  checked={src.enabled}
                  onChange={e => toggleEnabled(src.id, e.target.checked)}
                />
                <label htmlFor={src.id} title={src.url} style={{ flex: 1 }}>{src.label}</label>
                <button className="btn-icon" title="Επεξεργασία" onClick={() => startEdit(src)}>✏</button>
                <button className="btn-icon" title="Διαγραφή" onClick={() => deleteSource(src.id)}>🗑</button>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="kepea-add-source">
        <input
          type="text"
          placeholder="Όνομα πηγής (π.χ. ΑΣΕΠ)"
          value={newLabel}
          onChange={e => setNewLabel(e.target.value)}
          style={{ width: 160 }}
        />
        <input
          type="url"
          placeholder="URL"
          value={newUrl}
          onChange={e => setNewUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addSource()}
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" onClick={addSource} disabled={saving || !newUrl || !newLabel}>
          {saving ? <span className="spinner" /> : '+ Προσθήκη'}
        </button>
      </div>
    </div>
  )
}
