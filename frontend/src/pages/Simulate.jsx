import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, wsUrl } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import './Simulate.css'

const STAGE_ORDER = [
  'alice_encode',
  'channel',
  'bob_measure',
  'sifting',
  'qber_check',
  'abort_decision',
  'error_correction',
  'privacy_amplification',
]

const STAGE_LABELS = {
  alice_encode: '1 · Alice encodes',
  channel: '2 · Quantum channel',
  bob_measure: '3 · Bob measures',
  sifting: '4 · Sifting',
  qber_check: '5 · QBER check',
  abort_decision: '6 · Abort decision',
  error_correction: '7 · Error correction',
  privacy_amplification: '8 · Privacy amplification',
}

const QBER_THRESHOLD = 0.11

/**
 * Build the eight timeline rows in pipeline order. Known stages carry their
 * streamed summary; not-yet-received ones sit in the pending state.
 */
function buildRows(stageMap) {
  return STAGE_ORDER.map((name) => {
    const msg = stageMap.get(name)
    return {
      name,
      label: STAGE_LABELS[name],
      summary: msg ? msg.summary : null,
      status: msg ? (msg.status || 'done') : 'pending',
    }
  })
}

/**
 * Normalize a QBER fraction (0..1) into a display string in percent.
 * Returns null when no measurement exists yet.
 */
function formatQber(qber) {
  if (qber === null || qber === undefined) return null
  return (qber * 100).toFixed(1)
}

export default function Simulate() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [stageMap, setStageMap] = useState(new Map())
  const [running, setRunning] = useState(false)
  const [runInfo, setRunInfo] = useState(null) // { runId, transport }
  const [summary, setSummary] = useState(null) // done-frame data / POST summary
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [nQubits, setNQubits] = useState('256')

  // wsRef holds the live WebSocket so unmount can close it; aliveRef marks
  // whether the current connection should still drive state (StrictMode
  // mounts effects twice in dev — stale sockets must be ignored).
  const wsRef = useRef(null)
  const aliveRef = useRef(false)

  const loadHistory = useCallback(() => {
    api('/simulate/runs').then(({ ok, data }) => {
      if (ok) setHistory(data)
    })
  }, [])

  useEffect(() => {
    loadHistory()
    return () => {
      aliveRef.current = false
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [loadHistory])

  const applyStageMessage = useCallback((msg) => {
    setStageMap((prev) => {
      const next = new Map(prev)
      next.set(msg.stage_name, { summary: msg.summary, status: 'done' })
      return next
    })
  }, [])

  const handleDone = useCallback(
    (data, runId, transport) => {
      setSummary({ ...data, runId })
      setRunInfo({ runId, transport })
      setRunning(false)
      loadHistory()
    },
    [loadHistory],
  )

  /** Live path: stream each stage over the WebSocket as it completes. */
  const runOverWebSocket = useCallback(() => {
    setStageMap(new Map())
    setSummary(null)
    setRunInfo({ runId: null, transport: 'ws' })
    setError(null)
    setRunning(true)

    const ws = new WebSocket(wsUrl('/ws/simulate/bb84'))
    wsRef.current = ws
    aliveRef.current = true

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'run', n_qubits: Number(nQubits) || 256 }))
    }
    ws.onmessage = (event) => {
      if (!aliveRef.current) return // stale socket from a previous mount
      const msg = JSON.parse(event.data)
      if (msg.type === 'stage') {
        applyStageMessage(msg)
      } else if (msg.type === 'done') {
        handleDone(msg.data, msg.run_id, 'ws')
      } else if (msg.type === 'error') {
        setError(msg.summary || 'simulation failed')
        setRunning(false)
      }
    }
    ws.onerror = () => {
      if (!aliveRef.current) return
      setError('WebSocket connection failed — is the API running?')
      setRunning(false)
    }
    ws.onclose = () => {
      if (aliveRef.current && wsRef.current === ws) {
        setRunning((isRunning) => {
          // A done/error handler already settled the run; only surface an
          // abrupt-close error when the socket died mid-run.
          if (isRunning) {
            setError('connection closed before the run finished')
            return false
          }
          return isRunning
        })
      }
      if (wsRef.current === ws) wsRef.current = null
    }
  }, [nQubits, applyStageMessage, handleDone])

  /** Fallback path: one POST, then replay the returned stage list. */
  const runOverRest = useCallback(async () => {
    setStageMap(new Map())
    setSummary(null)
    setRunInfo({ runId: null, transport: 'rest' })
    setError(null)
    setRunning(true)

    const { ok, status, data } = await api('/simulate/bb84', {
      method: 'POST',
      body: { n_qubits: Number(nQubits) || 256 },
    })
    if (!aliveRef.current) return
    if (!ok) {
      setError(data?.detail ? String(data.detail) : `HTTP ${status}`)
      setRunning(false)
      return
    }
    for (const msg of data.stages || []) {
      // eslint-disable-next-line no-await-in-loop -- replay stage by stage
      await new Promise((r) => setTimeout(r, 120))
      applyStageMessage(msg)
    }
    handleDone(
      {
        aborted: data.aborted,
        abort_reason: data.abort_reason,
        sifted_count: data.sifted_count,
        final_key_length: data.final_key_length,
        qber: data.qber,
      },
      data.id,
      'rest',
    )
  }, [nQubits, applyStageMessage, handleDone])

  const onRun = () => {
    if (running) return
    runOverWebSocket() // falls back? no — a dedicated button covers REST
  }

  const qberPct = formatQber(summary?.qber)
  const aborted = Boolean(summary?.aborted)
  const rows = buildRows(stageMap)

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Simulate</h1>
          <p className="app-header__sub">
            BB84 pipeline · signed in as <span className="data">{user?.email}</span>
          </p>
        </div>
        <nav className="console-nav">
          <a href="/">Console</a>
          <a href="/simulate" className="active">
            Simulate
          </a>
          <button type="button" className="btn btn--secondary" onClick={onLogout}>
            Log out
          </button>
        </nav>
      </header>

      <main className="sim-grid">
        <section className={`card ${aborted ? 'card--abort' : running ? 'card--live' : ''}`}>
          <div className="card__head">
            <h2>BB84 run</h2>
            <span className="tag">
              {runInfo?.transport === 'ws' ? 'websocket' : runInfo?.transport === 'rest' ? 'rest' : 'idle'}
            </span>
          </div>

          <div className="sim-controls">
            <div className="field">
              <label className="field__label" htmlFor="nqubits">
                Qubits
              </label>
              <input
                id="nqubits"
                className="input"
                inputMode="numeric"
                value={nQubits}
                onChange={(e) => setNQubits(e.target.value.replace(/[^0-9]/g, ''))}
                disabled={running}
              />
            </div>
            <button type="button" className="btn btn--primary" onClick={onRun} disabled={running}>
              {running ? 'Running…' : 'Run BB84'}
            </button>
            <button type="button" className="btn btn--secondary" onClick={runOverRest} disabled={running}>
              Run via REST
            </button>
          </div>

          <ol className="timeline" style={{ marginTop: 'var(--space-4)' }}>
            {rows.map((row) => (
              <li key={row.name} className={`timeline__row timeline__row--${row.status}`}>
                <span className="timeline__marker">
                  <span className="timeline__node" />
                </span>
                <span>
                  <span className="timeline__stage-name">{row.label}</span>
                  <p className="timeline__summary">
                    {row.summary ??
                      (row.status === 'pending'
                        ? 'waiting…'
                        : 'completed')}
                  </p>
                </span>
              </li>
            ))}
          </ol>

          {error ? <p className="sim-error">{error}</p> : null}
        </section>

        <div>
          <section className={`card ${aborted ? 'card--abort' : summary ? 'card--live' : ''}`}>
            <div className="card__head">
              <h2>Readouts</h2>
              {runInfo?.runId ? <span className="tag">run #{runInfo.runId}</span> : null}
            </div>

            <dl className="readout-list">
              <div className="readout">
                <dt>QBER</dt>
                <dd className={`data ${aborted ? 'data--abort' : qberPct ? 'data--live' : ''}`}>
                  {qberPct ? `${qberPct}%` : '—'}
                </dd>
              </div>
              <div className="readout">
                <dt>threshold</dt>
                <dd className="data">
                  {(QBER_THRESHOLD * 100).toFixed(0)}
                  <span className="unit"> %</span>
                </dd>
              </div>
              <div className="readout">
                <dt>sifted keys</dt>
                <dd className="data">{summary ? summary.sifted_count : '—'}</dd>
              </div>
              <div className="readout">
                <dt>final key</dt>
                <dd className="data">
                  {summary ? `${summary.final_key_length} bit` : '—'}
                </dd>
              </div>
            </dl>

            <div className="gauge" role="img" aria-label={`QBER gauge: ${qberPct ?? 'no data'} percent`}>
              <span
                className={`gauge__fill ${aborted ? 'gauge__fill--abort' : ''}`}
                style={{ width: `${Math.min(100, (Number(qberPct) / 25) * 100)}%` }}
              />
              <span className="gauge__threshold" style={{ left: `${(QBER_THRESHOLD / 0.25) * 100}%` }} />
            </div>

            {aborted ? <p className="abort-note">{summary?.abort_reason}</p> : null}
          </section>

          <section className="card">
            <div className="card__head">
              <h2>Run history</h2>
              <span className="tag">persisted</span>
            </div>
            {history.length === 0 ? (
              <p className="history-empty">no runs yet — press “Run BB84”.</p>
            ) : (
              <ul className="history-list">
                {history.map((h) => (
                  <li key={h.id}>
                    <span>
                      #{h.id} · n={h.n_qubits}
                    </span>
                    <span className={h.aborted ? 'data data--abort' : 'data'}>
                      QBER {h.qber !== null ? `${(h.qber * 100).toFixed(1)}%` : '—'}
                    </span>
                    <span className="muted">{h.aborted ? 'abort' : `${h.final_key_length} bits`}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
