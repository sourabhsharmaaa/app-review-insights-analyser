import { useEffect, useState } from 'react'
import PulsePreview from '../components/PulsePreview'

export default function History() {
  const [weeks, setWeeks] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [pulse, setPulse] = useState(null)
  const [loadingPulse, setLoadingPulse] = useState(false)

  useEffect(() => {
    fetch('/api/weeks')
      .then(r => r.json())
      .then(data => { setWeeks(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  async function handleView(weekLabel) {
    setSelected(weekLabel)
    setPulse(null)
    setLoadingPulse(true)
    const res = await fetch(`/api/pulse/${weekLabel}`)
    const data = await res.json()
    setPulse(data)
    setLoadingPulse(false)
  }

  function handleDownload(p) {
    const fmt = (val, d = 1) => { const n = Number(val); return isNaN(n) ? '—' : n.toFixed(d) }
    const themes  = Array.isArray(p.top_themes)          ? p.top_themes          : []
    const quotes  = Array.isArray(p.user_quotes)         ? p.user_quotes         : []
    const actions = Array.isArray(p.action_ideas)        ? p.action_ideas        : []
    const bullets = Array.isArray(p.explanation_bullets) ? p.explanation_bullets : []
    const sources = Array.isArray(p.source_links)        ? p.source_links        : []

    const lines = [
      '═'.repeat(55),
      `GROWW Weekly Pulse | ${p.week_label}`,
      `${p.total_reviews_analysed} reviews | Avg ${fmt(p.avg_rating)}★`,
      '═'.repeat(55), '',
      'TOP THEMES', '─'.repeat(40),
      ...themes.map((t, i) =>
        `${i + 1}. ${t.label} — ${t.review_count} reviews | ${fmt(t.avg_rating)}★ | ${fmt(t.pct_of_total, 0)}%\n   "${t.one_line_summary}"`
      ),
      '', 'WHAT USERS ARE SAYING', '─'.repeat(40),
      ...quotes.map(q => `  "${q}"`),
      '', 'ACTION IDEAS', '─'.repeat(40),
      ...actions.map((a, i) => `  ${i + 1}. ${a}`),
    ]
    if (bullets.length > 0) {
      lines.push('', '─'.repeat(55), `FEE EXPLANATION: ${p.fee_scenario || ''}`, '─'.repeat(40))
      bullets.forEach(b => lines.push(`  • ${b}`))
      if (sources.length > 0) { lines.push('', 'Sources:'); sources.forEach(s => lines.push(`  ${s}`)) }
      if (p.last_checked) lines.push(`Last checked: ${p.last_checked}`)
    }
    lines.push('', '═'.repeat(55))

    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `groww_pulse_${p.week_label}.txt`
    a.click()
  }

  function starColor(rating) {
    if (rating >= 4) return '#16a34a'
    if (rating >= 3) return '#d97706'
    return '#dc2626'
  }

  return (
    <div className="page">
      <section className="card">
        <h2 className="section-title">Pulse History</h2>

        {loading && <p className="muted">Loading…</p>}
        {!loading && weeks.length === 0 && (
          <p className="muted">No cached pulses found. Run the pipeline first.</p>
        )}

        {weeks.length > 0 && (
          <table className="history-table">
            <thead>
              <tr>
                <th>Week</th>
                <th>Reviews</th>
                <th>Avg ★</th>
                <th>Top Theme</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {weeks.map(w => (
                <tr key={w.week_label} className={selected === w.week_label ? 'row-selected' : ''}>
                  <td><strong>{w.week_label}</strong></td>
                  <td>{w.total_reviews}</td>
                  <td style={{ color: starColor(w.avg_rating), fontWeight: 600 }}>
                    {w.avg_rating.toFixed(1)} ★
                  </td>
                  <td>{w.top_theme}</td>
                  <td>
                    <button
                      className="btn-view"
                      onClick={() => handleView(w.week_label)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* ── Selected Pulse ── */}
      {selected && (
        <section className="card">
          {loadingPulse && <p className="muted">Loading pulse…</p>}
          {pulse && (
            <>
              <PulsePreview pulse={pulse} />
              <div className="action-row">
                <button className="btn-secondary" onClick={() => handleDownload(pulse)}>
                  ⬇ Download .txt
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
