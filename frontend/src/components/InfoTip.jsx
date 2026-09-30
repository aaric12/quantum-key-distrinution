import { useState } from 'react'

/**
 * Tiny inline "i" icon with a one-line educational tooltip.
 *
 * Opens on hover/focus and toggles on click (so it works on touch and with
 * a keyboard). The bubble is absolutely positioned relative to the icon and
 * sized in CSS; no portal, no dependency. Text passed as children — keep it
 * to a sentence or two, consistent with the glossary's wording.
 */
export default function InfoTip({ label, children }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="info-tip">
      <button
        type="button"
        className="info-tip__icon"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        i
      </button>
      {open ? (
        <span role="tooltip" className="info-tip__bubble">
          {children}
        </span>
      ) : null}
    </span>
  )
}
