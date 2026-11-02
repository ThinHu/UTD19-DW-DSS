// Gọi API backend (FastAPI). Khi build, frontend được phục vụ cùng origin với API.
async function req(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts })
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch { /* bỏ qua */ }
    throw new Error(msg)
  }
  return r.json()
}

const qs = (o) => {
  const p = new URLSearchParams()
  Object.entries(o || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v) })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  meta: () => req('/api/meta'),
  state: () => req('/api/state'),
  replay: (body) => req('/api/replay', { method: 'POST', body: JSON.stringify(body) }),
  window: (params) => req('/api/window' + qs(params)),
  windowCsvUrl: (params) => '/api/window.csv' + qs(params),
  timeline: (day) => req('/api/timeline' + qs({ day })),
  detector: (id, params) => req(`/api/detector/${encodeURIComponent(id)}` + qs(params)),
  whatif: (body) => req('/api/whatif', { method: 'POST', body: JSON.stringify(body) }),
  addAction: (body) => req('/api/actions', { method: 'POST', body: JSON.stringify(body) }),
  actions: () => req('/api/actions'),
  model: () => req('/api/model'),
  dayClusters: () => req('/api/day_clusters'),
  goalSeek: (body) => req('/api/goalseek', { method: 'POST', body: JSON.stringify(body) }),
  dwQuality: () => req('/api/dw/quality'),
}

export const LEVEL_KEY = { 'Cao': 'high', 'Trung bình': 'med', 'Thấp': 'low', 'Không đủ dữ liệu': 'nd' }
export const LEVEL_COLOR = { 'Cao': 'var(--high)', 'Trung bình': 'var(--med)', 'Thấp': 'var(--low)', 'Không đủ dữ liệu': 'var(--nd)' }
export const LEVEL_HEX = { 'Cao': '#d64545', 'Trung bình': '#d98b0b', 'Thấp': '#14a07a', 'Không đủ dữ liệu': '#a3aeaa' }
export const CRIT = ['C1', 'C2', 'C3', 'C4', 'C5']
export const CRIT_SHORT = {
  C1: 'Occupancy vượt baseline', C2: 'Lưu lượng bất thường', C3: 'Độ kéo dài',
  C4: 'Lan tỏa lân cận', C5: 'Nguy cơ 30 phút (ML)',
}
export const fmt = {
  score: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(1)),
  int: (v) => (v === null || v === undefined ? '—' : Math.round(v).toLocaleString('vi-VN')),
  pct: (v, d = 1) => (v === null || v === undefined ? '—' : (v * 100).toFixed(d) + '%'),
  occ: (v) => (v === null || v === undefined ? '—' : (v * 100).toFixed(1) + '%'),
  date: (d) => { if (!d) return ''; const [y, m, dd] = d.split('-'); return `${dd}/${m}/${y}` },
}
export const slotLabel = (s) => `${String(Math.floor(s / 4)).padStart(2, '0')}:${String((s % 4) * 15).padStart(2, '0')}`
