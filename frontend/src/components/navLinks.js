/**
 * Shared navigation link sets. The SiteNav component renders them with
 * active-state highlighting; auth-gated entries are appended conditionally
 * by the pages (user ? APP_LINKS : PUBLIC_LINKS).
 */
export const APP_LINKS = [
  { label: 'Guide', href: '/' },
  { label: 'Foundations', href: '/foundations' },
  { label: 'Protocols', href: '/protocols' },
  { label: 'Compare', href: '/comparison' },
  { label: 'Simulate', href: '/simulate' },
  { label: 'Key rate', href: '/keyrate' },
  { label: 'Console', href: '/console' },
]

export const PUBLIC_LINKS = [
  { label: 'Guide', href: '/' },
  { label: 'Foundations', href: '/foundations' },
  { label: 'Protocols', href: '/protocols' },
  { label: 'Comparison', href: '/comparison' },
  { label: 'Sign up', href: '/register' },
  { label: 'Log in', href: '/login' },
]
