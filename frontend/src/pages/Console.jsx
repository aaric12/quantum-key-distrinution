import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api } from '../api.js'
import { useAuth } from '../AuthContext.jsx'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export default function Console() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const checkHealth = () => {
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setHealth)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(checkHealth, [])

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Quantum Key Distribution</h1>
          <p className="app-header__sub">
            education console · signed in as <span className="data">{user?.email}</span>
          </p>
        </div>
        <div className="topbar-user">
          <nav className="console-nav">
            <Link to="/">Console</Link>
            <Link to="/simulate">Simulate</Link>
          </nav>
          <span className="data">{user?.name}</span>
          <button type="button" className="btn btn--secondary" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <main className="grid">
        {/* Real state: live when the API answers, abort when it doesn't */}
        <section className={`card ${error ? 'card--abort' : 'card--live'}`}>
          <div className="card__head">
            <h2>Backend link</h2>
            <span className={`led ${error ? 'led--abort' : 'led--live'}`} />
          </div>

          {error ? (
            <p className="card__note">
              unreachable — <span className="data data--abort">{error}</span>.
              Is the API running on <span className="data">{API_BASE}</span>?
            </p>
          ) : (
            <dl className="stats">
              <div className="stat">
                <dt>status</dt>
                <dd className={`data ${health?.status === 'ok' ? '' : 'data--abort'}`}>
                  {health ? health.status : '…'}
                </dd>
              </div>
              <div className="stat">
                <dt>service</dt>
                <dd className="data">{health?.app ?? '…'}</dd>
              </div>
              <div className="stat">
                <dt>version</dt>
                <dd className="data">{health?.version ?? '…'}</dd>
              </div>
              <div className="stat">
                <dt>database</dt>
                <dd className={`data ${health?.database === 'ok' ? '' : 'data--abort'}`}>
                  {health?.database ?? '…'}
                </dd>
              </div>
            </dl>
          )}

          <div className="controls">
            <button
              type="button"
              className="btn btn--secondary"
              onClick={checkHealth}
              disabled={loading}
            >
              {loading ? 'Checking…' : 'Re-check link'}
            </button>
          </div>
        </section>

        {/* Static panel demoing the abort state + danger control */}
        <section className="card card--abort">
          <div className="card__head">
            <h2>QBER watch</h2>
            <span className="tag">sample run</span>
          </div>

          <dl className="stats">
            <div className="stat">
              <dt>QBER</dt>
              <dd className="data data--abort">11.3 %</dd>
            </div>
            <div className="stat">
              <dt>threshold</dt>
              <dd className="data">8.0 %</dd>
            </div>
            <div className="stat">
              <dt>sifted keys</dt>
              <dd className="data">1 284</dd>
            </div>
          </dl>

          <div className="field">
            <label className="field__label" htmlFor="threshold">
              Abort threshold (%)
            </label>
            <input
              id="threshold"
              className="input"
              defaultValue="8.0"
              inputMode="decimal"
            />
            <p className="field__hint">
              A breach lights the panel red and arms the abort control.
            </p>
          </div>

          <div className="controls">
            <Link to="/simulate" className="btn btn--primary">
              Start run →
            </Link>
            <button type="button" className="btn btn--danger">
              Abort run
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
