// Thin fetch wrapper for the auth API. The JWT travels in an httpOnly cookie,
// so no token ever touches JavaScript or localStorage.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Base URL for WebSocket connections (http(s) -> ws(s)). */
export function wsUrl(path) {
  const base = API_BASE.replace(/^http/, 'ws')
  return `${base}${path}`
}

/**
 * @param {string} path
 * @param {{ method?: string, body?: object }} [init]
 * @returns {Promise<{ ok: boolean, status: number, data: any }>}
 */
export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: 'include', // send/receive the httpOnly session cookie
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  let data = null
  try {
    data = await res.json()
  } catch {
    data = null // 204s / empty bodies
  }
  return { ok: res.ok, status: res.status, data }
}
