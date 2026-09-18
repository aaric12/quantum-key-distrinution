import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { API_BASE, api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import './Simulate.css'
import './KeyRate.css'
import './ReportView.css'

const QBER_THRESHOLD = 0.11

/** Compact static SVG chart of the two stored key-rate curves. */
function MiniKeyRate({ keyrate }) {
  if (!keyrate?.clean_curve?.length) return null
  const W = 560
  const H = 220
  const PADL = 46
  const PADR = 12
  const PADT = 12
  const PADB = 26
  const yMax = Math.log10(5e6)

  const x = (km) => PADL + (km / 300) * (W - PADL - PADR)
  const y = (v) =>
    v <= 0 ? H - PADB : H - PADB - (Math.log10(v + 1) / yMax) * (H - PADT - PADB)

  const line = (pts) =>
    pts.map((p) => `${x(p.distance_km)},${y(Math.max(0, p.skr_bps))}`).join(' ')

  const gridlines = [0, 1, 2, 3, 4, 5, 6]
    .map((p) => 10 ** p)
    .filter((v) => y(v) > PADT)

  return (
    <svg className="kr-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Key rate vs distance">
      {gridlines.map((v) => (
        <g key={v}>
          <line x1={PADL} x2={W - PADR} y1={y(v)} y2={y(v)} className="kr-chart__grid" />
          <text x={PADL - 6} y={y(v) + 3} textAnchor="end" className="kr-chart__tick">
            {v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : v}
          </text>
        </g>
      ))}
      {[0, 50, 100, 150, 200, 250, 300].map((t) => (
        <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="kr-chart__tick">
          {t === 0 ? '' : t}
          {t === 0 ? '0' : ' km'}
        </text>
      ))}
      <polyline points={line(keyrate.clean_curve)} className="kr-chart__line" style={{ stroke: 'var(--grey-400)' }} />
      <polyline points={line(keyrate.attacked_curve)} className="kr-chart__line" style={{ stroke: 'var(--abort-500)' }} />
      {[['clean_cutoff_km', 'var(--grey-400)'], ['attacked_cutoff_km', 'var(--abort-500)']].map(([k, color]) =>
        keyrate[k] != null ? (
          <line
            key={k}
            x1={x(keyrate[k])}
            x2={x(keyrate[k])}
            y1={PADT}
            y2={H - PADB}
            className="kr-chart__cutoff"
            style={{ stroke: color }}
          />
        ) : null,
      )}
    </svg>
  )
}

export default function ReportView() {
  const { uuid } = useParams()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let stale = false
    setReport(null)
    setError(null)
    api(`/reports/${uuid}`).then(({ ok, status, data }) => {
      if (stale) return
      if (!ok) {
        setError(status === 404 ? 'This report does not exist (or the link is wrong).' : `HTTP ${status}`)
        return
      }
      setReport(data)
    })
    return () => {
      stale = true
    }
  }, [uuid])

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  if (error) {
    return (
      <div className="container">
        <header className="console-topbar">
          <h1>Report</h1>
          <nav className="console-nav">
            <Link to="/console">Console</Link>
          </nav>
        </header>
        <section className="card card--abort">
          <p className="sim-error">{error}</p>
        </section>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="container">
        <p className="data">loading report…</p>
      </div>
    )
  }

  const run = report.run
  const qberPct = run.qber != null ? (run.qber * 100).toFixed(1) : null
  const aborted = Boolean(run.aborted)
  const ml = report.ml || {}
  const stages = report.stages || []

  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>{report.title}</h1>
          <p className="app-header__sub">
            public read-only report · generated {new Date(report.created_at).toLocaleString()}
            {user ? (
              <>
                {' '}
                · signed in as <span className="data">{user.email}</span>
              </>
            ) : null}
          </p>
        </div>
        <nav className="console-nav">
          {user ? (
            <>
              <a href="/console">Console</a>
              <a href="/simulate">Simulate</a>
              <a href="/keyrate">Key rate</a>
              <button type="button" className="btn btn--secondary" onClick={onLogout}>
                Log out
              </button>
            </>
          ) : (
            <>
              <a href="/register">Sign up</a>
              <a href="/login">Log in</a>
            </>
          )}
        </nav>
      </header>

      <main className="sim-grid">
        <section className="card">
          <div className="card__head">
            <h2>Run summary</h2>
            <span className="tag">{run.protocol.toUpperCase()}</span>
          </div>
          <dl className="readout-list">
            <div className="readout">
              <dt>QBER</dt>
              <dd className={`data ${aborted ? 'data--abort' : 'data--live'}`}>{qberPct ? `${qberPct}%` : '—'}</dd>
            </div>
            <div className="readout">
              <dt>attack</dt>
              <dd className={`data ${aborted ? 'data--abort' : ''}`}>
                {run.attack_type ? `${run.attack_type} @ ${Math.round((run.attack_intensity ?? 0) * 100)}%` : '—'}
              </dd>
            </div>
            <div className="readout">
              <dt>sifted</dt>
              <dd className="data">{run.sifted_count}</dd>
            </div>
            <div className="readout">
              <dt>final key</dt>
              <dd className="data">{run.final_key_length} bits</dd>
            </div>
          </dl>
          {aborted ? <p className="abort-note">{run.abort_reason}</p> : null}
          {report.attack?.description ? (
            <p className="timeline__summary">{report.attack.description}</p>
          ) : null}
        </section>

        <div>
          <section className={`card ${aborted ? 'card--abort' : 'card--live'}`}>
            <div className="card__head">
              <h2>Outcome</h2>
              <span className="tag">{aborted ? 'aborted' : 'key established'}</span>
            </div>
            {report.ai_summary ? (
              <div className="ai-note">
                <p>{report.ai_summary}</p>
                <span className="tag">
                  {report.summary_source === 'llm' ? 'AI summary' : 'auto summary'}
                </span>
              </div>
            ) : null}
            {ml.predicted_class ? (
              <div className="pns-panel">
                <p className="timeline__summary">
                  ML classifier: <span className="data data--live">{ml.predicted_class}</span>
                </p>
                <ul className="pns-levels">
                  {Object.entries(ml.probabilities || {})
                    .sort((a, b) => b[1] - a[1])
                    .map(([name, p]) => (
                      <li key={name}>
                        <span>{name}</span>
                        <span className="data">{(p * 100).toFixed(1)}%</span>
                      </li>
                    ))}
                </ul>
              </div>
            ) : null}
          </section>

          {report.keyrate ? (
            <section className="card">
              <div className="card__head">
                <h2>Key rate vs distance</h2>
                <span className="tag">model</span>
              </div>
              <MiniKeyRate keyrate={report.keyrate} />
              <p className="history-empty">
                grey: clean link ({report.keyrate.clean_cutoff_km} km cutoff) · red: with this
                run&apos;s attack ({report.keyrate.attacked_cutoff_km} km)
              </p>
            </section>
          ) : null}
        </div>
      </main>

      <section className="card" style={{ marginTop: 'var(--space-4)' }}>
        <div className="card__head">
          <h2>Stage log</h2>
          <span className="tag">{stages.length} stages</span>
        </div>
        <ol className="timeline">
          {stages.map((s) => (
            <li key={s.stage_index} className="timeline__row timeline__row--done">
              <span className="timeline__marker">
                <span className="timeline__node" />
              </span>
              <span>
                <span className="timeline__stage-name">{s.stage_name}</span>
                <p className="timeline__summary">{s.payload?.summary ?? ''}</p>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <p className="report-footer" style={{ margin: 'var(--space-4) 0' }}>
        <a href={`${API_BASE}/reports/${report.uuid}/report.pdf`} target="_blank" rel="noreferrer">
          download as PDF →
        </a>
      </p>
    </div>
  )
}
