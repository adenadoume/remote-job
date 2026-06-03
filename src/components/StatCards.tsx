import type { Stats } from '../types'

export default function StatCards({ stats }: { stats: Stats }) {
  return (
    <>
      <div className="card blue">
        <div className="val">{stats.total}</div>
        <div className="lbl">Total</div>
      </div>
      <div className="card amber">
        <div className="val">{stats.newCount}</div>
        <div className="lbl">New</div>
      </div>
      <div className="card green">
        <div className="val">{stats.saved}</div>
        <div className="lbl">Saved</div>
      </div>
      <div className="card purple">
        <div className="val">{stats.applied}</div>
        <div className="lbl">Applied</div>
      </div>
      <div className="card teal">
        <div className="val">
          {stats.avgScore}
          <span style={{ fontSize: 13, color: '#7FA8C9', fontWeight: 400 }}> / 10</span>
        </div>
        <div className="lbl">Avg Score</div>
      </div>
    </>
  )
}
