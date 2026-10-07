export function kg(v) {
  if (v == null || Number.isNaN(v)) return '—'
  const t = v / 1000
  if (t >= 1e6) return `${(t / 1e6).toFixed(2)}M t`
  if (t >= 1e3) return `${(t / 1e3).toFixed(1)}k t`
  if (t >= 10) return `${t.toFixed(0)} t`
  if (t >= 1) return `${t.toFixed(1)} t`
  return `${Math.round(v).toLocaleString()} kg`
}

export const pct = (v, d = 0) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`)
export const fix = (v, d = 3) => (v == null ? '—' : Number(v).toFixed(d))

export function pval(p) {
  if (p == null) return '—'
  if (p < 0.001) return 'p < 0.001'
  return `p = ${p.toFixed(3)}`
}

export function monthLabel(p) {
  if (!p) return ''
  const [y, m] = p.split('-')
  return `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1]} ${y}`
}

export function fdaDate(s) {
  if (!s || s.length !== 8) return s || '—'
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}`
}

// Leaflet writes colours as SVG attributes, which cannot use CSS variables,
// so resolve the theme token to a concrete colour first.
export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
