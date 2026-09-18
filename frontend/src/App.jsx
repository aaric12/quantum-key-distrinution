import { Navigate, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router'
import { AuthProvider, useAuth } from './AuthContext.jsx'
import Console from './pages/Console.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Simulate from './pages/Simulate.jsx'
import './App.css'

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="auth-shell">
        <p className="data">connecting…</p>
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}

function RedirectIfAuthed({ children }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="auth-shell">
        <p className="data">connecting…</p>
      </div>
    )
  }
  if (user) {
    return <Navigate to="/" replace />
  }
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <Console />
              </RequireAuth>
            }
          />
          <Route
            path="/simulate"
            element={
              <RequireAuth>
                <Simulate />
              </RequireAuth>
            }
 />
          <Route
            path="/login"
            element={
              <RedirectIfAuthed>
                <Login />
              </RedirectIfAuthed>
            }
          />
          <Route
            path="/register"
            element={
              <RedirectIfAuthed>
                <Register />
              </RedirectIfAuthed>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  )
}
