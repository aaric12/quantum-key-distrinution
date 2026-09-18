import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router'
import './SiteNav.css'

/**
 * Shared site navigation.
 *
 * >= 640px: plain horizontal link row (the existing instrument look).
 * < 640px: a hamburger toggle opening a dropdown panel; every item is a
 * 44px-minimum tap target, the panel closes on outside click / Escape /
 * navigation, and the toggle carries aria-expanded + aria-controls.
 *
 * props:
 *   links: [{ label, href }] — hrefs are router paths rendered via NavLink.
 */
export default function SiteNav({ links }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Close the panel whenever the route changes.
  useEffect(() => {
    setOpen(false)
  }, [links])

  return (
    <nav className="sitenav" ref={wrapRef} aria-label="Site">
      {/* Desktop: the plain link row. */}
      <div className="sitenav__row">
        {links.map((l) => (
          <NavLink
            key={l.href}
            to={l.href}
            end={l.href === '/'}
            className={({ isActive }) => `sitenav__link${isActive ? ' active' : ''}`}
          >
            {l.label}
          </NavLink>
        ))}
      </div>

      {/* Mobile: hamburger + dropdown panel. */}
      <button
        type="button"
        className="sitenav__toggle"
        aria-expanded={open}
        aria-controls="sitenav-panel"
        aria-label={open ? 'Close menu' : 'Open menu'}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="sitenav__burger" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </button>

      <div
        id="sitenav-panel"
        className={`sitenav__panel${open ? ' is-open' : ''}`}
        hidden={!open}
      >
        {links.map((l) => (
          <NavLink
            key={l.href}
            to={l.href}
            end={l.href === '/'}
            className={({ isActive }) => `sitenav__link sitenav__link--stack${isActive ? ' active' : ''}`}
            onClick={() => setOpen(false)}
          >
            {l.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
