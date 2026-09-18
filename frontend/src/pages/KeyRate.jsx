import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'
import './Simulate.css'
import './KeyRate.css'

const QBER_THRESHOLD = 0.11
const COLORS = {
  bb84: 'var(--live-500)',
  b92: 'var(--abort-500)',
}

/**
 * Dependency-free SVG multi-series line chart, log-ish handling via a fixed
 * cap: rates are plotted at min(rate, cap) so short-distance peaks don't
 * crush the interesting tail. Y axis is symmetric-log, cutoffs annotate.
 */
function SkrChart({ series, xMax, markerKm }) {
  if (series.length === 0) return null
  const W = 560
  const H = 240
  const PADL = 46
  const PADR = 12
  const PADT = 12
  const PADB = 26

  const yMax = Math.log10(5e6) // symmetric-log ceiling ~ peak rate scale
  const y = (v) => {
    if (v <= 0) return H - PADB // dead link sits on the axis
    return H - PADB - (Math.log10(v + 1) / yMax) * (H - PADT - PADB)
  }
  const x = (km) => PADL + (km / xMax) * (W - PADL - PADR)

  // Gridlines at powers of 10 from 1 bps up.
  const gridlines = [0, 1, 2, 3, 4, 5, 6].map((p) => 10 ** p).filter((v) => y(v) > PADT)
  const ticksX = [0, 50, 100, 150, 200, 250, 300].filter((t) => t <= xMax)

  return (
    <svg
      className="kr-chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Secret key rate versus distance"
    >
      {gridlines.map((v) => (
        <g key={v}>
          <line x1={PADL} x2={W - PADR} y1={y(v)} y2={y(v)} className="kr-chart__grid" />
          <text x={PADL - 6} y={y(v) + 3} textAnchor="end" className="kr-chart__tick">
            {v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : v}
          </text>
        </g>
      ))}
      {ticksX.map((t) => (
        <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="kr-chart__tick">
          {t}
          {t === 0 ? '' : ' km'}
        </text>
      ))}
      {series.map((s) => {
        const pts = s.curve
          .map((p) => `${x(p.distance_km)},${y(Math.max(0, p.skr_bps))}`)
          .join(' ')
        return (
          <g key={s.protocol}>
            <polyline
              points={pts}
              className={`kr-chart__line ${s.ghost ? 'ghost' : ''}`}
              style={{ stroke: s.color }}
            />
            {s.cutoff_km != null && (
              <>
                <line
                  x1={x(s.cutoff_km)}
                  x2={x(s.cutoff_km)}
                  y1={PADT}
                  y2={H - PADB}
                  className="kr-chart__cutoff"
                  style={{ stroke: s.color }}
                />
                <text
                  x={x(s.cutoff_km) - 4}
                  y={PADT + 10}
                  textAnchor="end"
                  className="kr-chart__cutoff-label"
                  style={{ fill: s.color }}
                >
                  {s.cutoff_km} km
                </text>
              </>
            )}
          </g>
        )
      })}
      {markerKm != null && (
        <line
          x1={x(markerKm)}
          x2={x(markerKm)}
          y1={PADT}
          y2={H - PADB}
          className="kr-chart__marker"
        />
      )}
    </svg>
  )
}

export default function KeyRate() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [protocol, setProtocol] = useState('bb84')
  const [distanceKm, setDistanceKm] = useState(80)
  const [attackIntensity, setAttackIntensity] = useState(0) // slider 0-100
  const [curve, setCurve] = useState(null) // { curve, cutoff_km, peak_skr_bps, ... }
  const [bb84Curve, setBb84Curve] = useState(null) // ghost comparison
  const [b92Curve, setB92Curve] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const intensity = attackIntensity / 100

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const { ok, status, data } = await api(
      `/keyrate?protocol=${protocol}&attack_intensity=${intensity}&max_distance_km=300&step_km=5&distance_km=${distanceKm}`,
    )
    if (!ok) {
      setError(data?.detail ? String(data.detail) : `HTTP ${status}`)
      setLoading(false)
      return
    }
    setCurve(data)
    setLoading(false)
  }, [protocol, intensity, distanceKm])

  // Ghost curves: fixed clean (I=0) references for both protocols, so the
  // user sees the attack's effect against a stable baseline.
  useEffect(() => {
    let stale = false
    Promise.all([
      api('/keyrate?protocol=bb84&attack_intensity=0&max_distance_km=300&step_km=5'),
      api('/keyrate?protocol=b92&attack_intensity=0&max_distance_km=300&step_km=5'),
    ]).then(([a, b]) => {
      if (stale) return
      if (a.ok) setBb84Curve(a.data)
      if (b.ok) setB92Curve(b.data)
    })
    return () => {
      stale = true
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Series: the live curve (tracks sliders) plus the two clean reference
  // curves (I=0). Same-protocol ghost vs live curve shows the attack's
  // combined effect with distance; the other protocol is context.
  const series = useMemo(() => {
    const ghosts = []
    if (bb84Curve) {
      ghosts.push({
        protocol: 'bb84',
        curve: bb84Curve.curve,
        cutoff_km: null,
        color: COLORS.bb84,
        ghost: true,
      })
    }
    if (b92Curve) {
      ghosts.push({
        protocol: 'b92',
        curve: b92Curve.curve,
        cutoff_km: null,
        color: COLORS.b92,
        ghost: true,
      })
    }
    if (!curve) return ghosts
    return [
      ...ghosts,
      {
        protocol,
        curve: curve.curve,
        cutoff_km: curve.cutoff_km,
        color: COLORS[protocol],
        ghost: false,
      },
    ]
  }, [curve, bb84Curve, b92Curve, protocol])

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const point = curve?.point
  const dead = point && point.skr_bps <= 0

  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Key rate vs distance</h1>
          <p className="app-header__sub">
            GLLP asymptotic model · signed in as <span className="data">{user?.email}</span>
          </p>
        </div>
        <nav className="console-nav">
          <a href="/">Guide</a><a href="/console">Console</a>
          <a href="/simulate">Simulate</a>
          <a href="/keyrate" className="active">
            Key rate
          </a>
          <button type="button" className="btn btn--secondary" onClick={onLogout}>
            Log out
          </button>
        </nav>
      </header>

      <main className="sim-grid">
        <section className="card">
          <div className="card__head">
            <h2>Link model</h2>
            <span className="tag">{loading ? 'updating…' : 'live'}</span>
          </div>

          <div className="sim-controls">
            <div className="field">
              <label className="field__label" htmlFor="kr-protocol">
                Protocol
              </label>
              <div className="controls" style={{ marginTop: 0 }}>
                {['bb84', 'b92'].map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={`btn ${protocol === p ? 'btn--primary' : 'btn--secondary'}`}
                    onClick={() => setProtocol(p)}
                  >
                    {p.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="field field--wide">
              <label className="field__label" htmlFor="kr-distance">
                Distance <span className="data">{distanceKm} km</span>
              </label>
              <input
                id="kr-distance"
                className="range"
                type="range"
                min="0"
                max="300"
                step="5"
                value={distanceKm}
                onChange={(e) => setDistanceKm(Number(e.target.value))}
              />
            </div>

            <div className="field field--wide">
              <label className="field__label" htmlFor="kr-intensity">
                Attack intensity (intercept-resend){' '}
                <span className="data">{attackIntensity}%</span>
              </label>
              <input
                id="kr-intensity"
                className="range"
                type="range"
                min="0"
                max="100"
                step="5"
                value={attackIntensity}
                onChange={(e) => setAttackIntensity(Number(e.target.value))}
              />
            </div>
          </div>

          <SkrChart
            series={series}
            xMax={300}
            markerKm={distanceKm}
          />
          <p className="history-empty">
            dashed clean BB84 / B92 references stay fixed; the solid curve tracks the sliders.
          </p>
        </section>

        <div>
          <section className={`card ${dead ? 'card--abort' : 'card--live'}`}>
            <div className="card__head">
              <h2>At {distanceKm} km</h2>
              <span className="tag">{protocol.toUpperCase()}</span>
            </div>
            <dl className="readout-list">
              <div className="readout">
                <dt>secret key rate</dt>
                <dd className={`data ${dead ? 'data--abort' : 'data--live'}`}>
                  {point
                    ? dead
                      ? '0 bps'
                      : point.skr_bps >= 1000
                        ? `${(point.skr_bps / 1000).toFixed(1)} kbps`
                        : `${point.skr_bps.toFixed(1)} bps`
                    : '—'}
                </dd>
              </div>
              <div className="readout">
                <dt>QBER</dt>
                <dd className={`data ${point && point.qber > QBER_THRESHOLD ? 'data--abort' : ''}`}>
                  {point ? `${(point.qber * 100).toFixed(1)}%` : '—'}
                </dd>
              </div>
              <div className="readout">
                <dt>channel transmittance</dt>
                <dd className="data">
                  {point ? `${(point.eta_channel * 100).toFixed(2)}%` : '—'}
                </dd>
              </div>
              <div className="readout">
                <dt>cutoff distance</dt>
                <dd className="data">{curve?.cutoff_km != null ? `${curve.cutoff_km} km` : '—'}</dd>
              </div>
              <div className="readout">
                <dt>peak rate</dt>
                <dd className="data">
                  {curve ? `${(curve.peak_skr_bps / 1e6).toFixed(2)} Mbps` : '—'}
                </dd>
              </div>
            </dl>
          </section>

          <section className="card">
            <div className="card__head">
              <h2>Model</h2>
              <span className="tag">GLLP</span>
            </div>
            <p className="history-empty">
              R = q · [ Q₁(1 − h₂(e₁)) − Q_μ · f · h₂(E_μ) ] over a weak coherent pulse
              link: η_det 0.6, dark counts 3×10⁻⁶/gate, misalignment 1.5%, μ 0.2,
              f 1.16, α 0.2 dB/km, 100 MHz clock. Sifting q: BB84 ½, B92 ¼.
              Intercept-resend adds I/4 (BB84) or I/3 (B92) to the QBER — the same
              scaling measured in the simulator&apos;s attack tests.
            </p>
          </section>
        </div>
      </main>
    </div>
  )
}
