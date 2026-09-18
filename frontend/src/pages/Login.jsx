import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../AuthContext.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const res = await login(email, password)
    if (res.ok) {
      navigate(from, { replace: true })
    } else if (res.status === 429) {
      setError('Too many attempts — wait a minute and retry.')
    } else {
      setError(res.data?.detail ?? `Login failed (HTTP ${res.status}).`)
    }
    setBusy(false)
  }

  return (
    <div className="auth-shell">
      <section className="card auth-card">
        <div className="card__head">
          <h1>Operator login</h1>
          <span className={`led ${error ? 'led--abort' : 'led--live'}`} />
        </div>

        <form className="auth-form" onSubmit={onSubmit}>
          {error && <p className="auth-error">{error}</p>}

          <div className="field">
            <label className="field__label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@lab.example"
              autoComplete="email"
              required
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              minLength={8}
              required
            />
          </div>

          <div className="controls">
            <button type="submit" className="btn btn--primary" disabled={busy}>
              {busy ? 'Authenticating…' : 'Log in'}
            </button>
          </div>
        </form>

        <p className="auth-alt">
          No account? <Link to="/register">Register</Link>
        </p>
      </section>
    </div>
  )
}
