import { Navigate, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router'
import { AuthProvider, useAuth } from './AuthContext.jsx'
import Comparison from './pages/Comparison.jsx'
import Console from './pages/Console.jsx'
import Foundations from './pages/Foundations.jsx'
import Home from './pages/Home.jsx'
import KeyRate from './pages/KeyRate.jsx'
import Login from './pages/Login.jsx'
import Protocols, { ProtocolDetail } from './pages/Protocols.jsx'
import Register from './pages/Register.jsx'
import ReportView from './pages/ReportView.jsx'
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
    return <Navigate to="/console" replace />
  }
  return children
}

export default function App() {
  return (
    <AuthProvider>      <Router>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/console"
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
            path="/keyrate"
            element={
              <RequireAuth>
                <KeyRate />
              </RequireAuth>
            }
 />          {/* Public read-only report page — intentionally outside RequireAuth. */}
          <Route path="/reports/:uuid" element={<ReportView />} />
          {/* Content pages — public by design. */}
          <Route path="/foundations" element={<Foundations />} />
          <Route path="/protocols" element={<Protocols />} />
          <Route path="/protocols/:slug" element={<ProtocolDetail />} />
          <Route path="/comparison" element={<Comparison />} />
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
          <Route path="/home" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  )
}
