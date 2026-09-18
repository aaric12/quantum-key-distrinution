import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useAuth } from '../AuthContext.jsx'

export default function Register() {
  const { register, login } = useAuth()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)

    const res = await register(name, email, password)
    if (!res.ok) {
      if (res.status === 429) {
        setError('Too many attempts — wait a minute and retry.')
      } else {
        setError(res.data?.detail ?? `Registration failed (HTTP ${res.status}).`)
      }
      setBusy(false)
      return
    }

    // Account created: log straight in (sets the httpOnly cookie + session row).
    const loginRes = await login(email, password)
    if (loginRes.ok) {
      navigate('/console', { replace: true })
    } else {
      navigate('/login', { replace: true })
    }
  }

  return (
    <div className="auth-shell">
      <section className="card auth-card">
        <div className="card__head">
          <h1>Register operator</h1>
          <span className={`led ${error ? 'led--abort' : 'led--live'}`} />
        </div>

        <form className="auth-form" onSubmit={onSubmit}>
          {error && <p className="auth-error">{error}</p>}

          <div className="field">
            <label className="field__label" htmlFor="name">
              Name
            </label>
            <input
              id="name"
              type="text"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ada Lovelace"
              autoComplete="name"
              required
            />
          </div>

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
              placeholder="min. 8 characters"
              autoComplete="new-password"
              minLength={8}
              required
            />
            <p className="field__hint">
              Stored server-side as a bcrypt hash; the session token never
              touches localStorage.
            </p>
          </div>

          <div className="controls">
            <button type="submit" className="btn btn--primary" disabled={busy}>
              {busy ? 'Provisioning…' : 'Create account'}
            </button>
          </div>
        </form>

        <p className="auth-alt">
          Already registered? <Link to="/login">Log in</Link>
        </p>
      </section>
    </div>
  )
}
