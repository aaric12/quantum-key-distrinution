import { Link, useParams } from 'react-router'
import { useAuth } from '../AuthContext.jsx'
import Glossary from '../components/Glossary.jsx'
import SiteNav from '../components/SiteNav.jsx'
import { APP_LINKS, PUBLIC_LINKS } from '../components/navLinks.js'
import './Content.css'

const PROTOCOLS = {
  bb84: {
    name: 'BB84',
    tagline: 'Four states, two bases — the 1984 original.',
    year: '1984 · Bennett & Brassard',
    facts: [
      ['signal states', '4 (|0⟩ |1⟩ |+⟩ |−⟩)'],
      ['bases', '2 (Z, X)'],
      ['sifting yield', '~50%'],
      ['abort threshold', 'QBER > 11%'],
      ['simulator', 'runnable'],
    ],
    lede: 'Alice encodes each random bit in one of two bases chosen at random: Z gives |0⟩ or |1⟩, X gives |+⟩ or |−⟩. Because the two bases are mutually unbiased, no measurement — in any basis — distinguishes all four states. Bob measures in his own random bases, and public comparison afterwards keeps only the rounds where their choices agreed.',
    steps: [
      'Alice draws random bits and random bases (Z/X), preparing one qubit per bit: bit 0 in Z → |0⟩, bit 1 in Z → |1⟩, bit 0 in X → |+⟩, bit 1 in X → |−⟩.',
      'The qubits cross the quantum channel — fibre or free space — picking up loss, noise, and possibly an eavesdropper.',
      'Bob chooses bases independently at random and measures. Same basis → deterministic outcome; wrong basis → a fair coin.',
      'Sifting: over an authenticated public channel they reveal bases (never bits) and keep positions where the bases matched — about half the transmission.',
      'QBER estimation: a random ~15% sample of the sifted key is compared and then discarded. If the measured error rate exceeds 11%, the channel is assumed compromised and everything is aborted.',
      'Error correction reconciles remaining disagreements by revealing block parities; privacy amplification then hashes the string down, erasing the leaked information — the output is the final secret key.',
    ],
    security:
      'An intercept-resend attacker guessing bases is wrong half the time; each wrong guess turns a sifted bit into a coin flip, so the attack injects ~25% QBER per attacked qubit — far past the 11% abort line. The no-cloning theorem rules out the quiet alternative of copying qubits for later.',
    attackNotes:
      'Against PNS on weak coherent pulses the defence is decoy states; Trojan-horse probing of the modulator is met with isolators and inbound-light monitoring. Both are modelled in the simulator.',
  },

  b92: {
    name: 'B92',
    tagline: 'Two non-orthogonal states — sifting by conclusiveness.',
    year: '1992 · Bennett',
    facts: [
      ['signal states', '2 (|0⟩, |+⟩)'],
      ['bases', '2 (Z, X)'],
      ['sifting yield', '~25%'],
      ['abort threshold', 'QBER > 11%'],
      ['simulator', 'runnable'],
    ],
    lede: 'B92 sends just two non-orthogonal states: bit 0 → |0⟩ (Z basis), bit 1 → |+⟩ (X basis). Neither state can be distinguished from the other with certainty, but some measurements can rule one out: a Z-basis result of |1⟩ is impossible if |0⟩ was sent, and an X-basis result of |−⟩ is impossible if |+⟩ was sent. Those conclusive events are the whole key.',
    steps: [
      'Alice sends |0⟩ for bit 0 and |+⟩ for bit 1 — two states with overlap ⟨0|+⟩ = 1/√2, so they are provably not perfectly distinguishable.',
      'Bob measures in a random basis (Z or X). A Z result of 1 rules out |0⟩ → the bit must have been 1; an X result of − rules out |+⟩ → the bit must have been 0.',
      'Any other outcome (a Z result of 0) is inconclusive — it could have come from either state — and is thrown away.',
      'Sifting: they keep only conclusive rounds. Roughly a quarter of the transmission survives (Bob must pick the right basis AND roll the right outcome).',
      'QBER estimation, error correction, and privacy amplification proceed as in BB84. Notably, flipped states remain conclusive-but-wrong in B92, so an intercept-resend attack adds ~33% QBER per attacked qubit — even more visible than BB84’s 25%.',
    ],
    security:
      'Security rests on the same non-orthogonality that limits its yield: because the two states overlap, Eve cannot learn the bit without sometimes being wrong, and being wrong means disturbing the state Bob eventually reads. The conclusive-event statistics themselves also constrain her.',
    attackNotes:
      'B92 is historically more exposed to PNS on multi-photon pulses — decoy states again close that gap. The simulator’s B92 sifting rule keeps outcome-1 events and infers 1 − basis, exactly as described here.',
  },

  e91: {
    name: 'E91',
    tagline: 'Entanglement and Bell inequality as a security certificate.',
    year: '1991 · Ekert',
    soon: true,
    facts: [
      ['resource', 'entangled pairs'],
      ['security test', 'CHSH inequality'],
      ['sifting', 'correlation rounds'],
      ['status', 'theory preview'],
    ],
    lede: 'Instead of Alice preparing states, a source distributes entangled pairs to both ends. Each side measures in randomly chosen settings; the correlation statistics either violate the CHSH Bell inequality — certifying that no eavesdropper holds pre-existing local hidden information — or the key is rejected. Security becomes a experimentally testable fact about the correlations themselves.',
    outline: [
      'A source emits entangled pairs; Alice and Bob measure along randomly chosen axes.',
      'Subset of rounds: both choose the correlation settings — outcomes are perfectly anti-correlated and form the raw key.',
      'Remaining rounds: alternate settings are used to estimate the CHSH parameter; violation beyond the classical bound of 2 certifies security.',
      'Post-processing (error correction + privacy amplification) follows the standard pipeline.',
    ],
  },

  sarg04: {
    name: 'SARG04',
    tagline: 'BB84’s states, announced in pairs — hardened for PNS.',
    year: '2004 · Scarani, Acín, Ribordy, Gisin',
    soon: true,
    facts: [
      ['signal states', '4 (same as BB84)'],
      ['encoding', 'two-state pairs'],
      ['sifting', 'pair announcement'],
      ['status', 'theory preview'],
    ],
    lede: 'SARG04 keeps BB84’s four signal states but changes the classical protocol: after Bob measures, Alice announces pairs of states — { |0⟩, |+⟩ } or { |1⟩, |−⟩ } — and Bob keeps the round only if his outcome is inconclusive between the pair. The twist trades sifting yield for markedly better behaviour against photon-number-splitting attacks on weak coherent sources.',
    outline: [
      'Transmission identical to BB84 (random bits in random Z/X bases).',
      'Alice announces one of two pairs containing the sent state; Bob keeps rounds where his outcome cannot distinguish the pair.',
      'Higher robustness to PNS at multi-photon pulses; lower raw yield than BB84.',
      'Standard post-processing applies.',
    ],
  },

  cow: {
    name: 'COW',
    tagline: 'Coherent pulses and decoy sequences — timing is the secret.',
    year: '2005 · Gisin, Ribordy, Kraus et al.',
    soon: true,
    facts: [
      ['encoding', 'time of pulses'],
      ['resource', 'weak coherent pulses'],
      ['defence', 'decoy sequences'],
      ['status', 'theory preview'],
    ],
    lede: 'Coherent-One-Way encodes bits in the presence or absence of pulses along one optical path: a logical 1 is a pulse, a 0 is a gap, with empty decoy frames interleaved. Security lives in the timing and coherence structure — an attacker splitting or measuring pulses disturbs the interference and visibility measured at the receiver, and the decoy sequences expose photon-number-splitting by loss statistics alone.',
    outline: [
      'Bits encoded as pulse/gap patterns in time; weak coherent pulses with multi-photon components.',
      'Empty decoy frames are interleaved to detect PNS via loss statistics.',
      'Bob checks interferometric visibility between neighbouring pulses — the coherence fingerprint.',
      'Intercept-resend on timing shows up as visibility loss; standard post-processing follows.',
    ],
  },
}

const HUB_CARDS = [
  ['bb84', 'runnable'],
  ['b92', 'runnable'],
  ['e91', 'theory'],
  ['sarg04', 'theory'],
  ['cow', 'theory'],
]

export function ProtocolDetail() {
  const { slug } = useParams()
  const { user } = useAuth()
  const p = PROTOCOLS[slug]

  if (!p) {
    return (
      <div className="container">
        <section className="card card--abort">
          <p className="sim-error">Unknown protocol “{slug}”.</p>
          <Link to="/protocols" className="btn btn--secondary">
            All protocols
          </Link>
        </section>
      </div>
    )
  }

  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>{p.name}</h1>
          <p className="app-header__sub">{p.tagline}</p>
        </div>
        <SiteNav links={user ? APP_LINKS : PUBLIC_LINKS} />
      </header>

      <section className="card">
        <div className="card__head">
          <h2>Overview</h2>
          <span className="tag">{p.year}</span>
        </div>
        <p className="proto-lede">{p.lede}</p>
        <div className="proto-facts" style={{ marginTop: 'var(--space-4)' }}>
          {p.facts.map(([k, v]) => (
            <dl className="readout" key={k}>
              <dt>{k}</dt>
              <dd className="data">{v}</dd>
            </dl>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>{p.soon ? 'Planned pipeline' : 'The pipeline, step by step'}</h2>
          {p.soon ? <span className="tag">theory preview</span> : <span className="tag">{p.name}</span>}
        </div>
        <ol className="proto-steps">
          {(p.steps || p.outline).map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
        {p.soon ? (
          <p className="content-note">
            A runnable implementation is on the roadmap — the simulator currently supports{' '}
            <Link to="/protocols/bb84" className="data">
              BB84
            </Link>{' '}
            and{' '}
            <Link to="/protocols/b92" className="data">
              B92
            </Link>
            .
          </p>
        ) : null}
      </section>

      {!p.soon ? (
        <section className="card">
          <div className="card__head">
            <h2>Why it&apos;s secure</h2>
            <span className="tag">security argument</span>
          </div>
          <p className="proto-lede">{p.security}</p>
          <p className="proto-lede" style={{ marginTop: 'var(--space-3)' }}>
            <b style={{ color: 'var(--text-hi)' }}>Known attacks &amp; countermeasures.</b> {p.attackNotes}
          </p>
        </section>
      ) : (
        <section className="card proto-soon">
          <div className="card__head">
            <h2>Implementation status</h2>
            <span className="tag">coming soon</span>
          </div>
          <p className="proto-lede">
            This page documents the theory ahead of the implementation. The backend
            protocol module for {p.name} exists as a stub and will follow the same
            eight-stage pipeline as BB84 and B92 — encode, channel, measure, sift,
            estimate, decide, correct, amplify.
          </p>
        </section>
      )}

      <section className="card">
        <div className="card__head">
          <h2>Glossary</h2>
          <span className="tag">{p.soon ? 'all terms' : 'protocol + physics'}</span>
        </div>
        <Glossary only={p.soon ? undefined : ['protocol', 'physics', 'metric']} />
      </section>
    </div>
  )
}

export default function Protocols() {
  const { user } = useAuth()
  return (
    <div className="container">
      <header className="console-topbar">
        <div>
          <h1>Protocols</h1>
          <p className="app-header__sub">
            Five ways to build a key from quantum states — two runnable today.
          </p>
        </div>
        <SiteNav links={user ? APP_LINKS : PUBLIC_LINKS} />
      </header>

      <section className="card">
        <div className="card__head">
          <h2>Runnable</h2>
          <span className="tag">in the simulator</span>
        </div>
        <div className="feature-grid">
          {HUB_CARDS.filter(([slug]) => !PROTOCOLS[slug].soon).map(([slug]) => (
            <Link key={slug} to={`/protocols/${slug}`} className="feature-card">
              <h3 className="feature-card__name">{PROTOCOLS[slug].name}</h3>
              <p className="feature-card__meta">{PROTOCOLS[slug].year}</p>
              <p>{PROTOCOLS[slug].tagline}</p>
              <span className="feature-card__arrow">→</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Theory previews</h2>
          <span className="tag">coming soon</span>
        </div>
        <div className="feature-grid">
          {HUB_CARDS.filter(([slug]) => PROTOCOLS[slug].soon).map(([slug]) => (
            <Link key={slug} to={`/protocols/${slug}`} className="feature-card">
              <h3 className="feature-card__name">
                {PROTOCOLS[slug].name} <span className="tag">theory</span>
              </h3>
              <p className="feature-card__meta">{PROTOCOLS[slug].year}</p>
              <p>{PROTOCOLS[slug].tagline}</p>
              <span className="feature-card__arrow">→</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__head">
          <h2>Glossary</h2>
          <span className="tag">all terms</span>
        </div>
        <Glossary />
      </section>
    </div>
  )
}
