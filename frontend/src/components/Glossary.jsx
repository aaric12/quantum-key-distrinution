import { useMemo, useState } from 'react'
import './Glossary.css'

/**
 * Shared QKD glossary: one source of truth, reused across content pages.
 * Each term carries a category so pages can embed a relevant subset
 * (categories: physics, protocol, attack, metric).
 */
export const GLOSSARY_TERMS = [
  {
    term: 'qubit',
    category: 'physics',
    def: 'The basic unit of quantum information: a two-level quantum system that can exist in a superposition of |0⟩ and |1⟩. Any attempt to read it disturbs the state — the property QKD security is built on.',
  },
  {
    term: 'superposition',
    category: 'physics',
    def: 'A quantum system existing in a combination of several states at once, e.g. α|0⟩ + β|1⟩. Measuring forces it into one definite outcome with probability |amplitude|².',
  },
  {
    term: 'measurement collapse',
    category: 'physics',
    def: 'Measuring a qubit irreversibly projects it onto the measured basis: a superposition becomes a single outcome. This is why an eavesdropper cannot copy qubits unnoticed.',
  },
  {
    term: 'no-cloning theorem',
    category: 'physics',
    def: 'No device can produce a perfect copy of an unknown quantum state. In QKD this guarantees Eve cannot duplicate qubits in transit and measure them at leisure — she must interact, and interaction leaves traces.',
  },
  {
    term: 'basis (Z / X)',
    category: 'physics',
    def: 'The measurement setting: the Z basis reads |0⟩/|1⟩, the X basis reads |+⟩/|−⟩. Measuring in the wrong basis randomises the result, which is exactly what exposes an intercept-resend attacker.',
  },
  {
    term: 'sifting',
    category: 'protocol',
    def: 'The public step where Alice and Bob keep only the positions where their choices line up. BB84 keeps matching bases; B92 keeps only conclusive outcomes. Roughly half (BB84) or a quarter (B92) survive.',
  },
  {
    term: 'QBER',
    category: 'metric',
    def: 'Quantum Bit Error Rate: the fraction of sample bits where Alice and Bob disagree. Noise and eavesdropping both raise it; past a threshold (~11% for BB84) the channel must be assumed compromised.',
  },
  {
    term: 'privacy amplification',
    category: 'protocol',
    def: 'A hash-based compression step that shrinks the shared key, cutting off whatever partial information an eavesdropper might hold. The result is a shorter but secret final key.',
  },
  {
    term: 'error correction',
    category: 'protocol',
    def: 'Reconciliation of Alice’s and Bob’s strings after sifting, typically by revealing block parities. Every revealed parity bit slightly leaks information — accounted for by privacy amplification.',
  },
  {
    term: 'intercept-resend',
    category: 'attack',
    def: 'Eve measures qubits in a random basis and re-sends what she measured. Wrong-basis choices disturb the state, injecting ~25% (BB84) or ~33% (B92) QBER on attacked qubits.',
  },
  {
    term: 'photon-number splitting (PNS)',
    category: 'attack',
    def: 'On weak coherent pulses, Eve siphons one photon from multi-photon pulses and stores it, reading it after basis announcement. QBER stays at zero — decoy-state loss statistics are the countermeasure.',
  },
  {
    term: 'Trojan-horse attack',
    category: 'attack',
    def: 'Eve shines light into Alice’s or Bob’s modulator and reads reflections to learn the setting. Countermeasures include isolators, filters, and monitoring inbound light.',
  },
  {
    term: 'decoy states',
    category: 'protocol',
    def: 'Pulses of varying intensity mixed into the transmission so the receiver can check loss rates per intensity. A PNS attacker distorts these statistics and is exposed without ever flipping a bit.',
  },
  {
    term: 'secret key rate (SKR)',
    category: 'metric',
    def: 'The rate of secure key bits generated, typically per pulse or per second. Falls exponentially with fibre distance through channel loss, and dies entirely when QBER exceeds the security threshold.',
  },
]

/**
 * Filterable, optionally scoped glossary component.
 *
 * props:
 *  - only: array of categories to show (default: all)
 *  - terms: optional override list (lets pages embed custom subsets)
 */
export default function Glossary({ only, terms = GLOSSARY_TERMS, initialQuery = '' }) {
  const [query, setQuery] = useState(initialQuery)
  const scoped = only ? terms.filter((t) => only.includes(t.category)) : terms

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return scoped
    return scoped.filter(
      (t) => t.term.toLowerCase().includes(q) || t.def.toLowerCase().includes(q),
    )
  }, [query, scoped])

  return (
    <div className="glossary">
      <div className="glossary__bar">
        <input
          className="input glossary__search"
          type="search"
          placeholder="filter terms…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter glossary terms"
        />
        <span className="tag">
          {filtered.length} term{filtered.length === 1 ? '' : 's'}
        </span>
      </div>
      {filtered.length === 0 ? (
        <p className="history-empty">no matching terms.</p>
      ) : (
        <dl className="glossary__list">
          {filtered.map((t) => (
            <div key={t.term} className="glossary__entry">
              <dt>
                {t.term}
                <span className={`glossary__cat glossary__cat--${t.category}`}>{t.category}</span>
              </dt>
              <dd>{t.def}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
