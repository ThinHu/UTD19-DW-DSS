const S = ({ children, size = 20, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" {...p}>{children}</svg>
)

export const I = {
  db: (p) => <S {...p}><ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" /><path d="M4.5 5.5v6.5c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8V5.5" /><path d="M4.5 12v6.5c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8V12" /></S>,
  cube: (p) => <S {...p}><path d="M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z" /><path d="M4 7.5 12 12l8-4.5M12 12v9" /></S>,
  grid: (p) => <S {...p}><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /></S>,
  map: (p) => <S {...p}><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z" /><path d="M9 4v14M15 6v14" /></S>,
  radio: (p) => <S {...p}><circle cx="12" cy="12" r="2" /><path d="M8.2 15.8a5.4 5.4 0 0 1 0-7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6M5.4 18.6a9.3 9.3 0 0 1 0-13.2M18.6 5.4a9.3 9.3 0 0 1 0 13.2" /></S>,
  alert: (p) => <S {...p}><path d="M12 4 2.8 19.5h18.4L12 4Z" /><path d="M12 10v4.2M12 17h.01" /></S>,
  brain: (p) => <S {...p}><path d="M4 19h16M6 16V9M10 16V5M14 16v-6M18 16v-9" /></S>,
  sliders: (p) => <S {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></S>,
  settings: (p) => <S {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z" /></S>,
  play: (p) => <S {...p}><path d="M7 5v14l11-7L7 5Z" fill="currentColor" /></S>,
  pause: (p) => <S {...p}><path d="M8 5v14M16 5v14" strokeWidth="3" /></S>,
  step: (p) => <S {...p}><path d="M6 5v14l9-7-9-7Z" fill="currentColor" /><path d="M18 5v14" strokeWidth="2.4" /></S>,
  ff: (p) => <S {...p}><path d="M3 6v12l8-6-8-6ZM12 6v12l8-6-8-6Z" fill="currentColor" /></S>,
  reset: (p) => <S {...p}><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.6" /><path d="M4 4v4.6h4.6" /></S>,
  search: (p) => <S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></S>,
  download: (p) => <S {...p}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></S>,
  refresh: (p) => <S {...p}><path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.6" /><path d="M20 4v4.6h-4.6" /></S>,
  arrow: (p) => <S {...p}><path d="M5 12h14M13 6l6 6-6 6" /></S>,
  back: (p) => <S {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></S>,
  x: (p) => <S {...p}><path d="M6 6l12 12M18 6 6 18" /></S>,
  trend: (p) => <S {...p}><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></S>,
  clock: (p) => <S {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></S>,
  check: (p) => <S {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></S>,
  chevron: (p) => <S {...p}><path d="m9 6 6 6-6 6" /></S>,
  log: (p) => <S {...p}><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" /></S>,
}

export function Logo() {
  return (
    <svg className="logo" viewBox="0 0 40 40">
      <rect x="7" y="7" width="26" height="26" rx="2" transform="rotate(45 20 20)" fill="none" stroke="var(--accent)" strokeWidth="2" />
      <rect x="14" y="14" width="12" height="12" transform="rotate(45 20 20)" fill="var(--accent)" />
    </svg>
  )
}
