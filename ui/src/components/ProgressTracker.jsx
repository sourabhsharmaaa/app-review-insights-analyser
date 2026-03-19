export default function ProgressTracker({ steps, pct, running }) {
  const isWaiting = running && pct === 0

  return (
    <div className="progress-tracker">
      <div className="progress-bar-bg" style={{ marginBottom: '16px' }}>
        {isWaiting ? (
          <div className="progress-bar-shimmer" />
        ) : (
          <div className="progress-bar-fill" style={{ width: `${pct}%`, transition: 'width 0.4s ease' }} />
        )}
      </div>

      {isWaiting ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div className="pulse-dots">
            <div className="pulse-dot" />
            <div className="pulse-dot" />
            <div className="pulse-dot" />
          </div>
          <span style={{ fontSize: 13, color: '#6b7280' }}>Starting pipeline…</span>
        </div>
      ) : (
        <p className="progress-pct">{pct}%</p>
      )}

      <ul className="step-list">
        {steps.map((step, i) => {
          const isDone = step.includes('✅')
          const icon = isDone ? '✅' : (i === steps.length - 1 && running ? '⏳' : '✅')
          const label = step.replace(/✅/g, '').trim()
          return (
            <li key={i} className="step-item">
              <span className="step-icon">{icon}</span>
              <span>{label}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
