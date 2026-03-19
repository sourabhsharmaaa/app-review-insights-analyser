export default function PulsePreview({ pulse }) {
  if (!pulse) return null

  const ts      = pulse.generated_at ? new Date(pulse.generated_at).toUTCString() : '—'
  const themes  = Array.isArray(pulse.top_themes)          ? pulse.top_themes          : []
  const quotes  = Array.isArray(pulse.user_quotes)         ? pulse.user_quotes         : []
  const actions = Array.isArray(pulse.action_ideas)        ? pulse.action_ideas        : []
  const bullets = Array.isArray(pulse.explanation_bullets) ? pulse.explanation_bullets : []
  const sources = Array.isArray(pulse.source_links)        ? pulse.source_links        : []

  function ratingColor(r) {
    const n = Number(r) || 0
    if (n >= 4) return '#16a34a'
    if (n >= 3) return '#d97706'
    return '#dc2626'
  }

  function fmt(val, decimals = 1) {
    const n = Number(val)
    return isNaN(n) ? '—' : n.toFixed(decimals)
  }

  return (
    <div className="pulse-preview">

      {/* ── Metrics ── */}
      <div className="metrics-row">
        <div className="metric">
          <span className="metric-value">{pulse.week_label || '—'}</span>
          <span className="metric-label">Week</span>
        </div>
        <div className="metric">
          <span className="metric-value">{pulse.total_reviews_analysed ?? '—'}</span>
          <span className="metric-label">Reviews Analysed</span>
        </div>
        <div className="metric">
          <span className="metric-value" style={{ color: ratingColor(pulse.avg_rating) }}>
            {fmt(pulse.avg_rating)} ★
          </span>
          <span className="metric-label">Avg Rating</span>
        </div>
      </div>

      <hr className="divider" />

      {/* ── Top Themes ── */}
      <h3 className="subsection-title">Top Themes</h3>
      {themes.length === 0 && <p style={{ color: '#888' }}>No themes available.</p>}
      {themes.map((theme, i) => (
        <div key={i} className="theme-card">
          <div className="theme-header">
            <span className="theme-name">{i + 1}. {theme.label}</span>
            <span className="theme-meta">
              {theme.review_count} reviews &nbsp;·&nbsp;
              <span style={{ color: ratingColor(theme.avg_rating) }}>
                {fmt(theme.avg_rating)}★
              </span>
              &nbsp;·&nbsp; {fmt(theme.pct_of_total, 0)}%
            </span>
          </div>
          <div className="progress-bar-bg">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.min(Number(theme.pct_of_total) || 0, 100)}%` }}
            />
          </div>
          <p className="theme-summary">"{theme.one_line_summary}"</p>
        </div>
      ))}

      <hr className="divider" />

      {/* ── User Quotes ── */}
      <h3 className="subsection-title">What Users Are Saying</h3>
      {quotes.length === 0 && <p style={{ color: '#888' }}>No quotes available.</p>}
      {quotes.map((q, i) => (
        <div key={i} className="quote-card">❝ {q} ❞</div>
      ))}

      <hr className="divider" />

      {/* ── Action Ideas ── */}
      <h3 className="subsection-title">Action Ideas</h3>
      {actions.length === 0 && <p style={{ color: '#888' }}>No action ideas available.</p>}
      <ol className="action-list">
        {actions.map((idea, i) => <li key={i}>{idea}</li>)}
      </ol>

      {/* ── Fee Explanation (shown if available) ── */}
      {bullets.length > 0 && (
        <>
          <hr className="divider" />
          <h3 className="subsection-title">
            💰 Fee Explanation{pulse.fee_scenario ? `: ${pulse.fee_scenario}` : ''}
          </h3>
          <ul className="action-list">
            {bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
          {sources.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: '#888' }}>Sources: </span>
              {sources.map((s, i) => (
                <a key={i} href={s} target="_blank" rel="noreferrer"
                  style={{ fontSize: '0.75rem', color: '#1a7a4a', marginRight: '1rem' }}>
                  {s}
                </a>
              ))}
            </div>
          )}
          {pulse.last_checked && (
            <p style={{ fontSize: '0.75rem', color: '#888', marginTop: '0.25rem' }}>
              Last checked: {pulse.last_checked}
            </p>
          )}
        </>
      )}

      <p className="generated-at">Generated: {ts}</p>
    </div>
  )
}
