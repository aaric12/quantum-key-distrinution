import { Link } from 'react-router'
import { useAuth } from '../AuthContext.jsx'
import Glossary from '../components/Glossary.jsx'
import './Content.css'

/**
 * One row per protocol, one column per comparison axis. The `sim` flag
 * marks protocols that are actually runnable in this app's simulator.
 */
const ROWS = [
  {
    name: 'BB84',
    slug: 'protocols/bb84',
    sim: true,
    year: 1984,
    security: 'Non-orthogonal states + no-cloning; wrong-basis measurements disturb',
    hardware: 'Attenuated laser (WCP) or true single-photon source; 2 modulators; random bit/basis generator',
    keyRate: 'Highest of the prepare-and-measure family (q = ½); ~3.6 Mbps peak / 185 km cutoff in this app’s link model',
    maturity: 'Most deployed protocol in commercial QKD systems; decades of field trials',
    attacks: 'Intercept-resend clearly visible (~25% QBER); PNS needs decoy states; Trojan-horse needs isolators',
  },
  {
    name: 'B92',
    slug: 'protocols/b92',
    sim: true,
    year: 1992,
    security: 'Two non-orthogonal states; conclusive outcomes expose any learning attempt',
    hardware: 'Simplest transmitter — only two states to prepare; same detectors as BB84',
    keyRate: 'Lower yield (q = ¼) but fewer states; ~1.8 Mbps peak / 185 km cutoff in this app’s model',
    maturity: 'Demonstrated in labs and trials; rarely deployed commercially vs BB84',
    attacks: 'Intercept-resend even louder (~33% QBER); historically more PNS-sensitive — decoys close the gap',
  },
  {
    name: 'E91',
    slug: 'protocols/e91',
    sim: false,
    year: 1991,
    security: 'Bell-inequality violation certifies absence of local hidden info; device-testing lineage',
    hardware: 'Entangled-pair source (SPDC), two receive stations; hardest hardware of the five',
    keyRate: 'Modest: only correlation rounds carry key; Bell test consumes rounds',
    maturity: 'Foundational research; entanglement distribution demos (satellite, fibre) exist',
    attacks: 'Any eavesdropping degrades Bell violation — attack shows up as reduced CHSH parameter',
  },
  {
    name: 'SARG04',
    slug: 'protocols/sarg04',
    sim: false,
    year: 2004,
    security: 'BB84 states, pair-announcement sifting; non-orthogonality shifted into classical post-processing',
    hardware: 'Identical to BB84 — purely a classical protocol change',
    keyRate: 'Lower yield than BB84; advantage appears at high loss with WCP sources',
    maturity: 'Lab demonstrations; proposed as drop-in BB84 upgrade for weak coherent sources',
    attacks: 'Mainly motivated by PNS robustness; intercept-resend visible as in BB84',
  },
  {
    name: 'COW',
    slug: 'protocols/cow',
    sim: false,
    year: 2005,
    security: 'Coherence + timing structure; visibility monitoring and decoy sequences',
    hardware: 'Simple pulse train transmitter; interferometer + timing at receiver; long-reach fibre friendly',
    keyRate: 'Efficient use of pulses; strong at long distances / high loss',
    maturity: 'Fielded in long-distance trials (e.g. 300+ km fibre experiments); commercially explored',
    attacks: 'PNS detected purely by decoy loss statistics; visibility loss exposes intercept attempts',
  },
]

export default function Comparison() {
  const { user } = useAuth()
  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Comparison</h1>
          <p className="app-header__sub">
            Five QKD protocols across the axes that matter for deployment.
          </p>
        </div>
        <nav className="console-nav">
          <a href="/">Home</a>
          <a href="/protocols">Protocols</a>
          {user ? <a href="/simulate">Simulate</a> : null}
        </nav>
      </header>

      <section className="card">
        <div className="card__head">
          <h2>All five protocols</h2>
          <span className="tag">2 runnable · 3 theory</span>
        </div>
        <div className="compare-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th>Protocol</th>
                <th>Security basis</th>
                <th>Hardware needs</th>
                <th>Key rate</th>
                <th>Deployment maturity</th>
                <th>Attack resistance</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.name}>
                  <td>
                    <Link to={`/${r.slug}`} className="data">
                      {r.name}
                    </Link>
                    <br />
                    <span className="muted" style={{ fontSize: '10px' }}>
                      {r.year}
                      {r.sim ? ' · runnable' : ''}
                    </span>
                  </td>
                  <td>{r.security}</td>
                  <td>{r.hardware}</td>
                  <td>{r.keyRate}</td>
                  <td>{r.maturity}</td>
                  <td>{r.attacks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="content-note">
          Key-rate figures come from this app’s own{' '}
          <Link to="/keyrate" className="data">
            SKR model
          </Link>{' '}
          (μ = 0.2, η_det 0.6, 0.2 dB/km fibre, dark counts 3×10⁻⁶/gate) and from
          measured attack slopes in the{' '}
          <Link to="/simulate" className="data">
            simulator
          </Link>
          . &ldquo;Runnable&rdquo; protocols have a full pipeline implementation
          behind the simulator; the others are documented as theory previews.
        </p>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Reading the table</h2>
          <span className="tag">how to use this</span>
        </div>
        <p className="proto-lede">
          There is no single winner: BB84 wins on maturity and tooling, B92 on
          transmitter simplicity, SARG04 on PNS robustness without hardware change,
          COW on long-distance efficiency, and E91 on the strongest (Bell-certified)
          security argument — at the highest hardware cost. For a deployable system
          today that trade is usually settled in favour of BB84 with decoy states.
        </p>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Glossary</h2>
          <span className="tag">attack + metric terms</span>
        </div>
        <Glossary only={['attack', 'metric']} />
      </section>
    </div>
  )
}
