import { useEffect } from 'react'

/**
 * Memory-only API key/token input.
 *
 * Contract (do not weaken):
 * - The value lives ONLY in the parent's React state (transient memory) and
 *   is cleared by the parent as soon as the request that consumed it is sent.
 * - No localStorage/sessionStorage/cookie ever sees it: nothing here touches
 *   storage APIs, and the field is not autofillable on reload
 *   (autoComplete="off", no name attribute, type="password" so password
 *   managers are not offered either).
 * - Nothing is pre-filled from anywhere; the field always starts empty.
 * - Pasted tokens are trimmed (clipboards often carry a trailing newline).
 */
export default function ApiKeyInput({ label, hint, value, onChange, onEnter, disabled }) {
  // Belt-and-braces: if this component ever unmounts mid-edit (navigation,
  // mode switch), drop whatever half-typed value the parent still holds.
  useEffect(() => () => onChange(''), [onChange])

  return (
    <div className="field field--wide api-key">
      <label className="field__label" htmlFor="ibm-token">
        {label}
      </label>
      <input
        id="ibm-token"
        className="input input--mono"
        type="password"
        autoComplete="off"
        spellCheck="false"
        placeholder="paste token — kept in memory only"
        value={value}
        onChange={(e) => onChange(e.target.value.trim())}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onEnter && value) onEnter()
        }}
        disabled={disabled}
      />
      <p className="field__hint">{hint}</p>
    </div>
  )
}
