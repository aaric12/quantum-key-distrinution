import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api.js'

const AuthContext = createContext(null)

/**
 * Owns the logged-in state. The JWT itself lives in an httpOnly cookie the
 * browser manages — this context only tracks the /auth/me answer, so a
 * refresh of anything sensitive is impossible from JS by construction.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api('/auth/me').then(({ ok, data }) => {
      if (!cancelled) {
        setUser(ok ? data : null)
        setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      async login(email, password) {
        const res = await api('/auth/login', {
          method: 'POST',
          body: { email, password },
        })
        if (res.ok) setUser(res.data)
        return res
      },
      async register(name, email, password) {
        const res = await api('/auth/register', {
          method: 'POST',
          body: { name, email, password },
        })
        return res
      },
      async logout() {
        const res = await api('/auth/logout', { method: 'POST' })
        setUser(null)
        return res
      },
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
