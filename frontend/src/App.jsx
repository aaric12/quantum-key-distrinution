import { useEffect, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setHealth)
      .catch((err) => setError(err.message))
  }, [])

  return (
    <main className="container">
      <h1>Quantum Key Distribution</h1>
      <p className="subtitle">Backend health check</p>

      <section className="card" aria-live="polite">
        {error && (
          <>
            <span className="dot dot-error" />
            <div>
              <strong>Backend unreachable</strong>
              <p className="detail">{error}</p>
              <p className="detail">Is the API running on {API_BASE}?</p>
            </div>
          </>
        )}

        {!error && !health && <p className="detail">Checking…</p>}

        {!error && health && (
          <>
            <span className={`dot ${health.status === 'ok' ? 'dot-ok' : 'dot-warn'}`} />
            <div>
              <strong>status: {health.status}</strong>
              <p className="detail">
                app: {health.app} · version: {health.version} · database: {health.database}
              </p>
            </div>
          </>
        )}
      </section>
    </main>
  )
}

export default App
