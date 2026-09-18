import { Link } from 'react-router'
import { useAuth } from '../AuthContext.jsx'
import Glossary from '../components/Glossary.jsx'
import SiteNav from '../components/SiteNav.jsx'
import { APP_LINKS, PUBLIC_LINKS } from '../components/navLinks.js'
import './Content.css'

const S = {
  line: 'var(--grey-400)',
  live: 'var(--live-500)',
  abort: 'var(--abort-500)',
  ink: 'var(--text-hi)',
}

function Label({ x, y, children, anchor = 'middle', color }) {
  return (
    <text x={x} y={y} textAnchor={anchor} className="diag-label" style={color ? { fill: color } : undefined}>
      {children}
    </text>
  )
}

/** Superposition: a state vector between the Z poles of the qubit sphere. */
function SuperpositionFigure() {
  const cx = 130
  const cy = 90
  return (
    <svg viewBox="0 0 300 180" role="img" aria-label="Superposition: a qubit state between |0> and |1>">
      {/* sphere outline + axes */}
      <circle cx={cx} cy={cy} r="52" fill="none" style={{ stroke: S.line, strokeDasharray: '3 4' }} />
      <line x1={cx} y1={cy - 66} x2={cx} y2={cy + 66} style={{ stroke: S.line }} />
      <line x1={cx - 60} y1={cy} x2={cx + 60} y2={cy} style={{ stroke: S.line, strokeDasharray: '2 4' }} />
      <Label x={cx} y={cy - 74} color={S.ink}>|0⟩</Label>
      <Label x={cx} y={cy + 84} color={S.ink}>|1⟩</Label>
      <Label x={cx - 70} y={cy + 3} color={S.ink}>|−⟩</Label>
      <Label x={cx + 70} y={cy + 3} color={S.ink}>|+⟩</Label>
      {/* superposed state vector, tilted between poles */}
      <line x1={cx} y1={cy} x2={cx + 30} y2={cy - 40} style={{ stroke: S.live }} strokeWidth="2.5" />
      <circle cx={cx + 30} cy={cy - 40} r="4" style={{ fill: S.live }} />
      <Label x={cx + 66} y={cy - 48} anchor="start" color={S.live}>ψ = α|0⟩ + β|1⟩</Label>
    </svg>
  )
}

/** Measurement collapse: one measurement, one random outcome, no undo. */
function CollapseFigure() {
  const y0 = 88
  return (
    <svg viewBox="0 0 560 180" role="img" aria-label="Measurement projects a superposition onto one outcome">
      {/* before: superposed vector */}
      <circle cx="80" cy={y0} r="42" fill="none" style={{ stroke: S.line, strokeDasharray: '3 4' }} />
      <line x1="80" y1={y0 - 52} x2="80" y2={y0 + 52} style={{ stroke: S.line }} />
      <line x1="80" y1={y0} x2="104" y2={y0 - 32} style={{ stroke: S.live }} strokeWidth="2.5" />
      <Label x="80" y={y0 - 60} color={S.ink}>|0⟩</Label>
      <Label x="80" y={y0 + 68} color={S.ink}>|1⟩</Label>
      <Label x="80" y="26" color={S.live}>before: ψ = α|0⟩ + β|1⟩</Label>
      {/* measurement device */}
      <rect x="210" y={y0 - 26} width="110" height="52" rx="8" fill="none" style={{ stroke: S.ink }} />
      <Label x="265" y={y0 - 2} color={S.ink}>measure</Label>
      <Label x="265" y={y0 + 14} color={S.ink}>(Z basis)</Label>
      {/* arrow */}
      <line x1="340" y1={y0} x2="382" y2={y0} style={{ stroke: S.line }} />
      <path d="M 382 88 l -8 -4 v 8 z" style={{ fill: S.line }} />
      {/* after: collapsed */}
      <circle cx="452" cy={y0} r="42" fill="none" style={{ stroke: S.line, strokeDasharray: '3 4' }} />
      <line x1="452" y1={y0 - 52} x2="452" y2={y0 + 52} style={{ stroke: S.line }} />
      <line x1="452" y1={y0} x2="452" y2={y0 - 42} style={{ stroke: S.abort }} strokeWidth="2.5" />
      <circle cx="452" cy={y0 - 42} r="4" style={{ fill: S.abort }} />
      <Label x="452" y="26" color={S.abort}>after: one outcome, randomly</Label>
      <Label x="500" y={y0 - 48} anchor="start" color={S.abort}>|0⟩</Label>
      <Label x="500" y={y0 + 55} anchor="start" color={S.line}>|1⟩ (not this time)</Label>
      <Label x="265" y="166" color={S.line}>outcome 0 with probability |α|² · outcome 1 with |β|² — the original superposition is gone</Label>
    </svg>
  )
}

/** No-cloning: a copy machine fed an unknown state cannot spit out a copy. */
function NoCloningFigure() {
  return (
    <svg viewBox="0 0 560 180" role="img" aria-label="No device can copy an unknown quantum state">
      <circle cx="70" cy="80" r="34" fill="none" style={{ stroke: S.line, strokeDasharray: '3 4' }} />
      <line x1="70" y1="48" x2="70" y2="112" style={{ stroke: S.line }} />
      <line x1="70" y1="80" x2="88" y2="56" style={{ stroke: S.live }} strokeWidth="2.5" />
      <Label x="70" y="132" color={S.live}>unknown ψ</Label>
      {/* machine */}
      <rect x="190" y="52" width="130" height="56" rx="8" fill="none" style={{ stroke: S.ink }} />
      <Label x="255" y="76" color={S.ink}>ideal copier?</Label>
      <Label x="255" y="94" color={S.line}>no-cloning: impossible</Label>
      <line x1="128" y1="80" x2="182" y2="80" style={{ stroke: S.line }} />
      <path d="M 182 80 l -8 -4 v 8 z" style={{ fill: S.line }} />
      {/* outputs */}
      <line x1="330" y1="66" x2="392" y2="66" style={{ stroke: S.live }} />
      <path d="M 392 66 l -8 -4 v 8 z" style={{ fill: S.live }} />
      <line x1="330" y1="98" x2="392" y2="98" style={{ stroke: S.abort, strokeDasharray: '4 3' }} />
      <path d="M 392 98 l -8 -4 v 8 z" style={{ fill: S.abort }} />
      <Label x="452" y="70" anchor="middle" color={S.live}>ψ (original, disturbed)</Label>
      <Label x="462" y="102" anchor="middle" color={S.abort}>✗ no clean copy</Label>
      <Label x="280" y="166" color={S.line}>any copying attempt necessarily disturbs the state — the disturbance is what QKD detects</Label>
    </svg>
  )
}

export default function Foundations() {
  const { user } = useAuth()
  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Foundations</h1>
          <p className="app-header__sub">
            The three quantum rules QKD&apos;s security rests on.
          </p>
        </div>
        <SiteNav links={user ? APP_LINKS : PUBLIC_LINKS} />
      </header>

      <section className="card">
        <div className="card__head">
          <h2>1 · Superposition</h2>
          <span className="tag">physics</span>
        </div>
        <p className="proto-lede">
          A qubit is not limited to 0 or 1. Until measured, it exists in a weighted
          combination α|0⟩ + β|1⟩ of both — the numbers α and β (amplitudes) set the
          odds of each outcome. BB84 exploits the direction of the state, not just its
          two poles: preparing in the Z basis gives |0⟩/|1⟩, preparing in the X basis
          gives the halfway states |+⟩/|−⟩. Two of those four directions are
          pairwise non-orthogonal — impossible to tell apart perfectly in one shot.
        </p>
        <figure className="figure">
          <SuperpositionFigure />
          <figcaption>
            <b>Fig 1 —</b> The qubit state as an arrow on the sphere of possible
            states. The poles are the classical bits; the equator states |+⟩ and |−⟩
            are what BB84/B92 use to hide key bits.
          </figcaption>
        </figure>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>2 · Measurement &amp; collapse</h2>
          <span className="tag">physics</span>
        </div>
        <p className="proto-lede">
          Measuring a qubit in a chosen basis forces it to a definite outcome of that
          basis — and destroys the superposition that was there. For the states QKD
          uses, measuring in the &ldquo;wrong&rdquo; basis gives a perfectly random
          result: the information simply is not in the qubit anymore. Bob&apos;s wrong
          guesses are harmless (they get sifted out), but Eve&apos;s wrong guesses
          corrupt the very bits she tried to steal.
        </p>
        <figure className="figure">
          <CollapseFigure />
          <figcaption>
            <b>Fig 2 —</b> A Z-basis measurement projects the tilted state onto one
            pole. |α|² of the time it reads 0, |β|² of the time 1. This is a one-way
            door — no measurement can be undone or retried on the same qubit.
          </figcaption>
        </figure>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>3 · The no-cloning theorem</h2>
          <span className="tag">physics</span>
        </div>
        <p className="proto-lede">
          Quantum mechanics forbids any device from producing a perfect copy of an
          unknown state. So Eve cannot quietly duplicate the qubit stream, let the
          originals fly to Bob, and measure her copies later at leisure. She must
          interact with the qubits themselves — and by rule 2, interacting means
          disturbing them. That disturbance shows up as QBER, which is exactly what
          the estimate step is designed to catch.
        </p>
        <figure className="figure">
          <NoCloningFigure />
          <figcaption>
            <b>Fig 3 —</b> The copy machine Eve wishes she had. The no-cloning theorem
            proves it cannot exist for arbitrary unknown states; the best she can do
            is guess a measurement basis (the intercept-resend attack the{' '}
            <Link to="/simulate" className="data">
              simulator
            </Link>{' '}
            implements) and accept the errors she causes.
          </figcaption>
        </figure>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Glossary — physics</h2>
          <span className="tag">subset</span>
        </div>
        <Glossary only={['physics']} />
      </section>
    </div>
  )
}
