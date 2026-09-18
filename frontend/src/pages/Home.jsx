import { Link } from 'react-router'
import { useAuth } from '../AuthContext.jsx'
import Glossary from '../components/Glossary.jsx'
import './Content.css'

const STAGES = [
  ['1', 'Encode', 'Alice draws random bits and bases, preparing one qubit per bit — non-orthogonal states no listener can cleanly copy.'],
  ['2', 'Transmit', 'The qubits cross an optical channel where loss, noise, or an eavesdropper may act on them.'],
  ['3', 'Measure', 'Bob chooses bases independently and measures each qubit. Without coordination, some of his choices are wrong — and that is fine.'],
  ['4', 'Sift', 'Over a public channel they reveal bases (or outcomes) and keep only the positions that line up. BB84 keeps ~50%, B92 ~25%.'],
  ['5', 'Estimate', 'A random sample is sacrificed to measure QBER. If errors exceed the security threshold, the channel is assumed compromised and the key is discarded.'],
  ['6', 'Extract', 'Error correction reconciles the strings; privacy amplification hashes the rest down to a shorter key that is provably secret.'],
]

const FEATURES = [
  {
    to: '/foundations',
    title: 'Foundations',
    body: 'Superposition, measurement collapse, and the no-cloning theorem — with diagrams.',
  },
  {
    to: '/protocols',
    title: 'Protocols',
    body: 'BB84 and B92 in full detail; E91, SARG04, and COW as theory previews.',
  },
  {
    to: '/simulate',
    title: 'Simulate',
    body: 'Run the full pipeline, launch attacks at it, and watch the QBER react live.',
  },
  {
    to: '/keyrate',
    title: 'Key rate',
    body: 'SKR vs distance under real link physics — loss, dark counts, detectors.',
  },
]

const PROTOCOL_CARDS = [
  {
    to: '/protocols/bb84',
    name: 'BB84',
    year: 1984,
    blurb: 'Four states, two bases. The protocol that started the field.',
    states: '4 states · 2 bases',
  },
  {
    to: '/protocols/b92',
    name: 'B92',
    year: 1992,
    blurb: 'Two non-orthogonal states. Sifting by conclusiveness alone.',
    states: '2 states · 2 bases',
  },
  {
    to: '/protocols',
    name: 'E91',
    year: 1991,
    blurb: 'Entanglement and the Bell test as a security certificate.',
    states: 'entangled pairs',
    soon: true,
  },
]

export default function Home() {
  const { user } = useAuth()
  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Quantum key distribution, from qubits to keys</h1>
          <p className="app-header__sub">
            An interactive field guide: the physics, the protocols, the attacks, and the numbers.
          </p>
        </div>
        <nav className="console-nav">
          {user ? (
            <>
              <a href="/console">Console</a>
              <a href="/simulate">Simulate</a>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => window.location.assign('/console')}
              >
                Open console
              </button>
            </>
          ) : (
            <>
              <a href="/register">Sign up</a>
              <a href="/login" className="btn btn--primary">
                Log in
              </a>
            </>
          )}
        </nav>
      </header>

      <section className="card hero">
        <p className="hero__kicker">Why it matters</p>
        <h2 className="hero__title">
          Security from physics, not from hardness assumptions.
        </h2>
        <p className="hero__lede">
          Classical key exchange bets that certain maths problems are too hard to solve.
          QKD bets on something stronger: the laws of quantum mechanics. Measuring a
          qubit disturbs it, unknown states cannot be copied, and so an eavesdropper
          necessarily leaves fingerprints in the error statistics — fingerprints the
          protocol is designed to detect.
        </p>
        <div className="hero__actions">
          <Link to="/foundations" className="btn btn--primary">
            Start with the physics
          </Link>
          <Link to="/protocols" className="btn btn--secondary">
            Jump to the protocols
          </Link>
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>The six-step pipeline</h2>
          <span className="tag">every protocol</span>
        </div>
        <ol className="pipeline-grid">
          {STAGES.map(([n, title, body]) => (
            <li key={n} className="pipeline-step">
              <span className="pipeline-step__num">{n}</span>
              <div>
                <h3 className="pipeline-step__title">{title}</h3>
                <p className="pipeline-step__body">{body}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="content-note">
          See each step fire in order in the{' '}
          <Link to="/simulate" className="data">
            simulator
          </Link>
          , or watch how the numbers decay with distance in the{' '}
          <Link to="/keyrate" className="data">
            key-rate explorer
          </Link>
          .
        </p>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Explore</h2>
          <span className="tag">4 sections</span>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <Link key={f.to} to={f.to} className="feature-card">
              <h3>{f.title}</h3>
              <p>{f.body}</p>
              <span className="feature-card__arrow">→</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Three protocols, three ideas</h2>
          <Link to="/comparison" className="tag">
            compare all five →
          </Link>
        </div>
        <div className="feature-grid">
          {PROTOCOL_CARDS.map((p) => (
            <Link key={p.name} to={p.to} className="feature-card">
              <h3 className="feature-card__name">
                {p.name}
                {p.soon ? <span className="tag">theory</span> : null}
              </h3>
              <p className="feature-card__meta">{p.year} · {p.states}</p>
              <p>{p.blurb}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Glossary</h2>
          <span className="tag">shared across pages</span>
        </div>
        <Glossary />
      </section>
    </div>
  )
}
