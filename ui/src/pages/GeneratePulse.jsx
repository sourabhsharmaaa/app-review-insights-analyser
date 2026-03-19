import { useState, useRef } from 'react'
import ProgressTracker from '../components/ProgressTracker'
import PulsePreview from '../components/PulsePreview'
import BASE from '../api'

export default function GeneratePulse() {
  const [weeksBack, setWeeksBack]         = useState(12)
  const [maxReviews, setMaxReviews]       = useState(100)
  const [forceRun, setForceRun]           = useState(false)
  const [running, setRunning]             = useState(false)
  const [steps, setSteps]                 = useState([])
  const [pct, setPct]                     = useState(0)
  const [pulse, setPulse]                 = useState(null)
  const [error, setError]                 = useState(null)
  const [publishing, setPublishing]       = useState(false)
  const [publishResult, setPublishResult] = useState(null)
  const sourceRef = useRef(null)

  // ── Generate pipeline ──────────────────────────────────────────────────────

  function handleRun() {
    if (running) return
    setPulse(null)
    setError(null)
    setPublishResult(null)
    setSteps([])
    setPct(0)
    setRunning(true)

    const url = `${BASE}/api/run?weeks_back=${weeksBack}&force=${forceRun}&max_reviews=${maxReviews}`
    const es  = new EventSource(url, { withCredentials: false })
    sourceRef.current = es

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setSteps(prev => [...prev, data.step])
      setPct(data.pct)
    })

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      setPct(100)
      setPulse(data.pulse)
      setRunning(false)
      es.close()
    })

    es.addEventListener('error', (e) => {
      let msg = 'Pipeline failed. Check server logs.'
      try { msg = JSON.parse(e.data).message } catch {}
      setError(msg)
      setRunning(false)
      es.close()
    })

    es.onerror = () => {
      if (running) {
        setError('Cannot connect to backend — make sure the API server is running on port 8000.')
        setRunning(false)
        es.close()
      }
    }
  }

  // ── Publish (Append to Google Doc + Create Gmail Draft) ───────────────────

  async function handlePublish() {
    if (!pulse || publishing) return
    setPublishing(true)
    setPublishResult(null)

    try {
      const res  = await fetch(`${BASE}/api/publish/${pulse.week_label}`, { method: 'POST' })
      const data = await res.json()

      if (res.ok) {
        setPublishResult({ ok: true, gdoc_url: data.gdoc_url, draft_url: data.draft_url })
      } else {
        setPublishResult({ ok: false, msg: data.detail || 'Publish failed' })
      }
    } catch {
      setPublishResult({ ok: false, msg: 'Network error — backend not reachable' })
    } finally {
      setPublishing(false)
    }
  }

  // ── Download .txt ──────────────────────────────────────────────────────────

  function handleDownload() {
    if (!pulse) return

    const fmt = (val, d = 1) => { const n = Number(val); return isNaN(n) ? '—' : n.toFixed(d) }
    const themes  = Array.isArray(pulse.top_themes)          ? pulse.top_themes          : []
    const quotes  = Array.isArray(pulse.user_quotes)         ? pulse.user_quotes         : []
    const actions = Array.isArray(pulse.action_ideas)        ? pulse.action_ideas        : []
    const bullets = Array.isArray(pulse.explanation_bullets) ? pulse.explanation_bullets : []
    const sources = Array.isArray(pulse.source_links)        ? pulse.source_links        : []

    const lines = [
      '═'.repeat(55),
      `GROWW Weekly Pulse | ${pulse.week_label}`,
      `${pulse.total_reviews_analysed} reviews | Avg ${fmt(pulse.avg_rating)}★`,
      '═'.repeat(55),
      '',
      'TOP THEMES',
      '─'.repeat(40),
      ...themes.map((t, i) =>
        `${i + 1}. ${t.label} — ${t.review_count} reviews | ${fmt(t.avg_rating)}★ | ${fmt(t.pct_of_total, 0)}%\n   "${t.one_line_summary}"`
      ),
      '',
      'WHAT USERS ARE SAYING',
      '─'.repeat(40),
      ...quotes.map(q => `  "${q}"`),
      '',
      'ACTION IDEAS',
      '─'.repeat(40),
      ...actions.map((a, i) => `  ${i + 1}. ${a}`),
    ]

    // Fee explanation section (if available)
    if (bullets.length > 0) {
      lines.push('')
      lines.push('─'.repeat(55))
      lines.push(`FEE EXPLANATION: ${pulse.fee_scenario || ''}`)
      lines.push('─'.repeat(40))
      bullets.forEach(b => lines.push(`  • ${b}`))
      if (sources.length > 0) {
        lines.push('')
        lines.push('Sources:')
        sources.forEach(s => lines.push(`  ${s}`))
      }
      if (pulse.last_checked) lines.push(`Last checked: ${pulse.last_checked}`)
    }

    lines.push('')
    lines.push('═'.repeat(55))
    lines.push(`Generated: ${pulse.generated_at ? new Date(pulse.generated_at).toUTCString() : '—'}`)

    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `groww_pulse_${pulse.week_label}.txt`
    a.click()
  }

  return (
    <div className="page">

      {/* ── Configuration ── */}
      <section className="card">
        <h2 className="section-title">Configuration</h2>
        <div className="config-row">
          <label>
            Weeks to analyse: <strong>{weeksBack}</strong>
            <input
              type="range" min={1} max={12} value={weeksBack}
              onChange={e => setWeeksBack(Number(e.target.value))}
              className="slider"
              disabled={running}
            />
          </label>
          <label>
            Max reviews: <strong>{maxReviews}</strong>
            <span style={{ fontSize: '0.72rem', color: '#888', marginLeft: '8px' }}>
              {maxReviews <= 100 ? '~1–2 min' : maxReviews <= 200 ? '~3–4 min' : '~8 min'}
            </span>
            <input
              type="range" min={50} max={500} step={50} value={maxReviews}
              onChange={e => setMaxReviews(Number(e.target.value))}
              className="slider"
              disabled={running}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox" checked={forceRun}
              onChange={e => setForceRun(e.target.checked)}
              disabled={running}
            />
            Force re-run (skip cache)
          </label>
        </div>
        <button className="btn-primary" onClick={handleRun} disabled={running}>
          {running ? '⏳ Running…' : '▶  Generate Pulse'}
        </button>
      </section>

      {/* ── Progress ── */}
      {(running || steps.length > 0) && (
        <section className="card">
          <h2 className="section-title">Pipeline Progress</h2>
          <ProgressTracker steps={steps} pct={pct} running={running} />
          {error && <p className="error-msg">❌ {error}</p>}
        </section>
      )}

      {/* ── Pulse Preview + Publish (only after pipeline done) ── */}
      {pulse && (
        <section className="card">
          <h2 className="section-title">Pulse Preview</h2>
          <PulsePreview pulse={pulse} />

          {/* Action buttons */}
          <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'center' }}>
            <button
              className="btn-primary"
              onClick={handlePublish}
              disabled={publishing}
              title="Appends to Google Doc + sends email"
              style={{ minWidth: '160px' }}
            >
              {publishing ? '⏳ Publishing…' : 'Publish'}
            </button>
          </div>

          {/* Publish result — show View Google Doc only after successful publish */}
          {publishResult && (
            <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
              {publishResult.ok ? (
                <>
                  <p className="success-msg" style={{ margin: 0 }}>✅ Published successfully</p>
                  {publishResult.gdoc_url && import.meta.env.VITE_GDOC_DOC_ID && (
                    <a
                      href={publishResult.gdoc_url}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-secondary"
                      style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                    >
                      📄 View Google Doc
                    </a>
                  )}
                </>
              ) : (
                <p className="error-msg">❌ {publishResult.msg}</p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
