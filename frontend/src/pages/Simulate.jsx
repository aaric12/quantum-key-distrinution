import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { api, wsUrl } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import ApiKeyInput from '../components/ApiKeyInput.jsx'
import SiteNav from '../components/SiteNav.jsx'
import { APP_LINKS } from '../components/navLinks.js'
import './Simulate.css'

const HW_MIN_QUBITS = 20
const HW_MAX_QUBITS = 50

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
  bb84: {
    alice_encode: '1 · Alice encodes (4 states)',
    channel: '2 · Quantum channel',
    bob_measure: '3 · Bob measures',
    sifting: '4 · Sifting (basis match)',
    qber_check: '5 · QBER check',
    abort_decision: '6 · Abort decision',
    error_correction: '7 · Error correction',
    privacy_amplification: '8 · Privacy amplification',
  },
  b92: {
    alice_encode: '1 · Alice encodes (2 non-orthogonal states)',
    channel: '2 · Quantum channel',
    bob_measure: '3 · Bob measures (random bases)',
    sifting: '4 · Sifting (conclusive outcomes)',
    qber_check: '5 · QBER check',
    abort_decision: '6 · Abort decision',
    error_correction: '7 · Error correction',
    privacy_amplification: '8 · Privacy amplification',
  },
}

const QBER_THRESHOLD = 0.11

/**
 * Lightweight inline SVG line chart of QBER per run. Y axis fixed at 0-35%
 * so consecutive runs stay comparable; the threshold line sits at 11%.
 * No chart library: one <polyline> over scaled points, aborts in red.
 */
function QberChart({ data }) {
  if (data.length === 0) {
    return <p className="history-empty">run a simulation to plot QBER.</p>
  }
  const W = 320
  const H = 120
  const PAD = 4
  const Y_MAX = 0.35
  const x = (i) =>
    PAD + (i / Math.max(1, data.length - 1)) * (W - 2 * PAD)
  const y = (q) => H - PAD - (Math.min(q, Y_MAX) / Y_MAX) * (H - 2 * PAD)
  const points = data.map((d, i) => `${x(i)},${y(d.qber)}`).join(' ')
  const thresholdY = y(QBER_THRESHOLD)
  return (
    <svg
      className="qber-chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="QBER per run line chart"
    >
      <line
        x1={PAD}
        x2={W - PAD}
        y1={thresholdY}
        y2={thresholdY}
        className="qber-chart__threshold"
      />
      <text x={W - PAD} y={thresholdY - 3} textAnchor="end" className="qber-chart__label">
        11%
      </text>
      <polyline points={points} className="qber-chart__line" />
      {data.map((d, i) => (
        <circle
          key={d.runId ?? i}
          cx={x(i)}
          cy={y(d.qber)}
          r={2.5}
          className={d.aborted ? 'qber-chart__pt qber-chart__pt--abort' : 'qber-chart__pt'}
        >
          <title>{`run #${d.runId ?? '?'}: ${(d.qber * 100).toFixed(1)}%${d.aborted ? ' (abort)' : ''}`}</title>
        </circle>
      ))}
    </svg>
  )
}

/**
 * Build the eight timeline rows in pipeline order. Known stages carry their
 * streamed summary; not-yet-received ones sit in the pending state.
 */
function buildRows(stageMap, labels) {
  return STAGE_ORDER.map((name) => {
    const msg = stageMap.get(name)
    return {
      name,
      label: labels[name],
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
  const [protocol, setProtocol] = useState('bb84')
  const [attackType, setAttackType] = useState('none')
  const [attackIntensity, setAttackIntensity] = useState(50) // slider 0-100
  const [qberHistory, setQberHistory] = useState([]) // {runId, qber, aborted}
  const [pnsStats, setPnsStats] = useState(null)
  const [aiSummary, setAiSummary] = useState(null) // {text, source}
  // Share: {creating, uuid, url, error} for the public report of the last run.
  const [share, setShare] = useState(null)

  // ---- Real-hardware mode ----
  // mode: 'simulator' (default pipeline) | 'hardware' (real IBM backend).
  const [mode, setMode] = useState('simulator')
  // ibmToken lives ONLY here, in transient React state. It is never written
  // to localStorage/sessionStorage/cookies anywhere in this app, never
  // pre-filled, and cleared immediately after the request consumes it.
  const [ibmToken, setIbmToken] = useState('')
  const [hwStatus, setHwStatus] = useState(null) // queued | running | done | failed
  const [hwResult, setHwResult] = useState(null)
  const [hwError, setHwError] = useState(null)
  const [hwBackend, setHwBackend] = useState(null)
  const hwWsRef = useRef(null)

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
      if (hwWsRef.current) {
        hwWsRef.current.close()
        hwWsRef.current = null
      }
      // Unmount: the token existed only for an in-flight request — drop it.
      setIbmToken('')
    }
  }, [loadHistory])

  const applyStageMessage = useCallback((msg) => {
    setStageMap((prev) => {
      const next = new Map(prev)
      next.set(msg.stage_name, { summary: msg.summary, status: 'done' })
      return next
    })
    if (msg.stage_name === 'channel' && msg.data?.pns) {
      setPnsStats(msg.data.pns)
    }
  }, [])

  const handleDone = useCallback(
    (data, runId, transport) => {
      setSummary({ ...data, runId })
      setRunInfo({ runId, transport })
      setRunning(false)
      setQberHistory((prev) => [
        ...prev,
        { runId, qber: data.qber ?? 0, aborted: Boolean(data.aborted) },
      ])
      loadHistory()
    },
    [loadHistory],
  )

  /** Live path: stream each stage over the WebSocket as it completes. */
  const runOverWebSocket = useCallback(() => {
    setStageMap(new Map())
    setSummary(null)
    setShare(null)
    setPnsStats(null)
    setRunInfo({ runId: null, transport: 'ws' })
    setAiSummary(null)
    setError(null)
    setRunning(true)

    const ws = new WebSocket(wsUrl(`/ws/simulate/${protocol}`))
    wsRef.current = ws
    aliveRef.current = true

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: 'run',
          n_qubits: Number(nQubits) || 256,
          attack_type: attackType === 'none' ? null : attackType,
          attack_intensity: attackIntensity / 100,
        }),
      )
    }
    ws.onmessage = (event) => {
      if (!aliveRef.current) return // stale socket from a previous mount
      const msg = JSON.parse(event.data)
      if (msg.type === 'stage') {
        applyStageMessage(msg)
      } else if (msg.type === 'done') {
        if (msg.data?.ai_summary) {
          setAiSummary({ text: msg.data.ai_summary, source: msg.data.summary_source })
        }
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
  }, [protocol, nQubits, attackType, attackIntensity, applyStageMessage, handleDone])

  /** Fallback path: one POST, then replay the returned stage list. */
  const runOverRest = useCallback(async () => {
    setStageMap(new Map())
    setSummary(null)
    setShare(null)
    setPnsStats(null)
    setAiSummary(null)
    setRunInfo({ runId: null, transport: 'rest' })
    setError(null)
    setRunning(true)

    const { ok, status, data } = await api(`/simulate/${protocol}`, {
      method: 'POST',
      body: {
        n_qubits: Number(nQubits) || 256,
        attack_type: attackType === 'none' ? null : attackType,
        attack_intensity: attackIntensity / 100,
      },
    })
    if (data?.ai_summary) {
      setAiSummary({ text: data.ai_summary, source: data.summary_source })
    }
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
  }, [protocol, nQubits, attackType, attackIntensity, applyStageMessage, handleDone])

  const onRun = () => {
    if (running) return
    runOverWebSocket() // falls back? no — a dedicated button covers REST
  }

  /**
   * Real-hardware path. The token is sent once in the POST body and wiped
   * from state immediately after the fetch call is made. Progress arrives
   * over /ws/hardware/{job_id}; the token is never part of that exchange.
   */
  const runOnHardware = useCallback(async () => {
    if (running || !ibmToken) return
    setStageMap(new Map())
    setSummary(null)
    setShare(null)
    setAiSummary(null)
    setPnsStats(null)
    setRunInfo({ runId: null, transport: 'hw' })
    setError(null)
    setHwError(null)
    setHwStatus('submitting')
    setHwResult(null)
    setHwBackend(null)
    setRunning(true)

    const n = Number(nQubits) || HW_MIN_QUBITS
    const { ok, status, data } = await api('/simulate/hardware', {
      method: 'POST',
      body: {
        protocol,
        n_qubits: Math.min(HW_MAX_QUBITS, Math.max(HW_MIN_QUBITS, n)),
        shots: 1024,
        ibm_token: ibmToken,
      },
    })
    // The request has consumed the token — its memory lifetime ends here.
    setIbmToken('')
    if (!aliveRef.current) return
    if (!ok) {
      setHwStatus(null)
      setHwError(data?.detail ? String(data.detail) : `HTTP ${status}`)
      setRunning(false)
      return
    }
    setHwBackend(data.backend)
    setHwStatus(data.status || 'queued')

    const ws = new WebSocket(wsUrl(`/ws/hardware/${data.job_id}`))
    hwWsRef.current = ws
    ws.onmessage = (event) => {
      if (!aliveRef.current || ws !== hwWsRef.current) return
      const msg = JSON.parse(event.data)
      setHwStatus(msg.status)
      if (msg.backend) setHwBackend(msg.backend)
      if (msg.result) setHwResult(msg.result)
      if (msg.error) setHwError(msg.error)
      if (msg.status === 'done' || msg.status === 'failed') {
        setRunning(false)
        ws.close()
      }
    }
    ws.onerror = () => {
      if (!aliveRef.current || ws !== hwWsRef.current) return
      setHwError('hardware status socket failed — check the API server')
      setRunning(false)
    }
  }, [running, ibmToken, nQubits, protocol])

  /** Create the public, UUID-keyed report for the last completed run. */
  const shareReport = useCallback(async () => {
    if (!runInfo?.runId) return
    setShare((s) => ({ ...(s || {}), creating: true, error: null }))
    const { ok, status, data } = await api(`/reports/${runInfo.runId}`, {
      method: 'POST',
    })
    if (!ok) {
      setShare({ error: data?.detail ? String(data.detail) : `HTTP ${status}` })
      return
    }
    // The frontend route renders the public ReportView for this uuid.
    setShare({ uuid: data.uuid, url: `${window.location.origin}/reports/${data.uuid}` })
  }, [runInfo])

  const qberPct = formatQber(summary?.qber)
  const aborted = Boolean(summary?.aborted)
  const rows = buildRows(stageMap, STAGE_LABELS[protocol])

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
        <SiteNav links={APP_LINKS} />
      </header>

      <main className="sim-grid">
        <section className={`card ${aborted ? 'card--abort' : running ? 'card--live' : ''}`}>
          <div className="card__head">
            <h2>BB84 run</h2>
            <span className="tag">
              {mode === 'hardware'
                ? 'ibm quantum'
                : runInfo?.transport === 'ws'
                  ? 'websocket'
                  : runInfo?.transport === 'rest'
                    ? 'rest'
                    : 'idle'}
            </span>
          </div>

          <div className="sim-controls">
            <div className="field">
              <label className="field__label" htmlFor="mode">
                Target
              </label>
              <div className="controls" style={{ marginTop: 0 }}>
                <button
                  type="button"
                  className={`btn ${mode === 'simulator' ? 'btn--primary' : 'btn--secondary'}`}
                  onClick={() => setMode('simulator')}
                  disabled={running}
                >
                  Simulator
                </button>
                <button
                  type="button"
                  className={`btn ${mode === 'hardware' ? 'btn--primary' : 'btn--secondary'}`}
                  onClick={() => setMode('hardware')}
                  disabled={running}
                >
                  Real IBM hardware
                </button>
              </div>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="protocol">
                Protocol
              </label>
              <div className="controls" style={{ marginTop: 0 }}>
                {Object.keys(STAGE_LABELS).map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={`btn ${protocol === p ? 'btn--primary' : 'btn--secondary'}`}
                    onClick={() => setProtocol(p)}
                    disabled={running}
                  >
                    {p.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="nqubits">
                Qubits
                {mode === 'hardware' ? ` (${HW_MIN_QUBITS}–${HW_MAX_QUBITS} on hardware)` : ''}
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
            {mode === 'hardware' ? (
              <ApiKeyInput
                label="IBM Quantum API token"
                hint={`Memory only — never stored, never sent anywhere except this run's request. Hardware accepts ${HW_MIN_QUBITS}–${HW_MAX_QUBITS} qubits.`}
                value={ibmToken}
                onChange={setIbmToken}
                onEnter={runOnHardware}
                disabled={running}
              />
            ) : null}
            {mode === 'simulator' ? (
              <>
                <button type="button" className="btn btn--primary" onClick={onRun} disabled={running}>
                  {running ? 'Running…' : 'Run BB84'}
                </button>
                <div className="field">
                  <label className="field__label" htmlFor="attack">
                    Attack
                  </label>
                  <select
                    id="attack"
                    className="input"
                    value={attackType}
                    onChange={(e) => setAttackType(e.target.value)}
                    disabled={running}
                  >
                    <option value="none">none (ideal channel)</option>
                    <option value="intercept_resend">intercept-resend</option>
                    <option value="pns">PNS (decoy states)</option>
                    <option value="trojan">trojan-horse (model)</option>
                  </select>
                </div>
                <div className="field field--wide">
                  <label className="field__label" htmlFor="intensity">
                    Intensity <span className="data">{attackIntensity}%</span>
                  </label>
                  <input
                    id="intensity"
                    className="range"
                    type="range"
                    min="0"
                    max="100"
                    value={attackIntensity}
                    onChange={(e) => setAttackIntensity(Number(e.target.value))}
                    disabled={running}
                  />
                </div>
                <button type="button" className="btn btn--secondary" onClick={runOverRest} disabled={running}>
                  Run via REST
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn--primary"
                onClick={runOnHardware}
                disabled={running || !ibmToken}
              >
                {running ? 'On hardware…' : 'Run on IBM hardware'}
              </button>
            )}
          </div>

          {mode === 'simulator' ? (
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
          ) : (
            <div className="hw-strip" style={{ marginTop: 'var(--space-4)' }}>
              <p className="hw-strip__line">
                <span
                  className={`led ${hwStatus === 'failed' ? 'led--abort' : hwStatus === 'done' ? 'led--live' : ''}`}
                />
                <span className="data">{hwStatus ?? 'idle'}</span>
                {hwBackend ? <span className="muted"> · backend {hwBackend}</span> : null}
                {mode === 'hardware' ? (
                  <span className="muted">
                    {' '}· qubit limit {HW_MIN_QUBITS}–{HW_MAX_QUBITS}
                  </span>
                ) : null}
              </p>
              {hwResult ? (
                <dl className="readout-list hw-readouts">
                  <div className="readout">
                    <dt>shots</dt>
                    <dd className="data">{hwResult.total_shots}</dd>
                  </div>
                  <div className="readout">
                    <dt>shots with key</dt>
                    <dd className="data">{hwResult.shots_with_key}</dd>
                  </div>
                  <div className="readout">
                    <dt>avg sifted length</dt>
                    <dd className="data">{hwResult.avg_sifted_length}</dd>
                  </div>
                  <div className="readout">
                    <dt>expected sifted</dt>
                    <dd className="data">
                      {(hwResult.expected_sifted_fraction * 100).toFixed(0)}%
                    </dd>
                  </div>
                </dl>
              ) : null}
              {hwError ? <p className="sim-error">{hwError}</p> : null}
            </div>
          )}

          {aiSummary ? (
            <div className="ai-note">
              <p>{aiSummary.text}</p>
              <span className="tag">
                {aiSummary.source === 'llm' ? 'AI summary' : 'auto summary'}
              </span>
            </div>
          ) : null}

          {runInfo?.runId && !running && mode === 'simulator' ? (
            <div className="share-panel">
              {share?.url ? (
                <>
                  <input
                    className="input input--mono"
                    readOnly
                    value={share.url}
                    onFocus={(e) => e.target.select()}
                    aria-label="Public report link"
                  />
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={() => navigator.clipboard?.writeText(share.url)}
                  >
                    Copy link
                  </button>
                  <a className="btn btn--secondary" href={share.url} target="_blank" rel="noreferrer">
                    Open
                  </a>
                </>
              ) : (
                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={shareReport}
                  disabled={share?.creating}
                >
                  {share?.creating ? 'Creating…' : 'Share'}
                </button>
              )}
              {share?.error ? <p className="sim-error">{share.error}</p> : null}
            </div>
          ) : null}

          {pnsStats ? (
            <div className="pns-panel">
              <p className="timeline__summary">
                PNS decoy loss rates — spread {pnsStats.observed_spread?.toFixed(3)} vs noise
                floor {pnsStats.noise_floor?.toFixed(3)} →{' '}
                <span className={pnsStats.flagged ? 'data data--abort' : 'data data--live'}>
                  {pnsStats.anomaly_z?.toFixed(1)}σ {pnsStats.flagged ? 'FLAGGED' : 'clean'}
                </span>
              </p>
              <ul className="pns-levels">
                {pnsStats.levels?.map((lvl) => (
                  <li key={lvl.mu}>
                    <span className="data">μ={lvl.mu.toFixed(4)}</span>
                    <span className="data">
                      loss {(lvl.loss_rate * 100).toFixed(1)}% ({lvl.lost}/{lvl.sent})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

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
                <dt>attack</dt>
                <dd className={`data ${aborted ? 'data--abort' : ''}`}>
                  {attackType === 'none' ? '—' : `${attackType} @ ${attackIntensity}%`}
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
          </section>

          <section className="card">
            <div className="card__head">
              <h2>QBER across runs</h2>
              <span className="tag">{qberHistory.length} pt{qberHistory.length === 1 ? '' : 's'}</span>
            </div>
            <QberChart data={qberHistory} />
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
