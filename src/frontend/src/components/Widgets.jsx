import { useMemo, useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { LEVEL_HEX, LEVEL_KEY, fmt, slotLabel } from '../api.js'
import { I } from './Icons.jsx'

export function LevelBadge({ level }) {
  if (!level) return null
  const label = level === 'Không đủ dữ liệu' ? 'Thiếu dữ liệu' : level
  return <span className={`badge ${LEVEL_KEY[level]}`}>{label}</span>
}

export function ConfDot({ c, prefix = '' }) {
  const col = { 'Cao': 'var(--low)', 'Trung bình': 'var(--med)', 'Thấp': '#e07a3f', 'Rất thấp': 'var(--high)' }[c] || 'var(--nd)'
  return <span className="status" title="Chất lượng dữ liệu đo (tier, số khoảng đo hợp lệ) — không phải độ chắc chắn của khuyến nghị"><span className="dot" style={{ background: col }} />{prefix}{c || '—'}</span>
}

/* Độ chắc chắn đã hiệu chỉnh: P(detector thật sự cần chú ý | mức điểm) — isotonic trên tháng 5 */
export function Certainty({ v, compact = false }) {
  if (v === null || v === undefined) return <span className="muted">—</span>
  const cls = v >= 0.6 ? 'cert-hi' : v >= 0.2 ? 'cert-mid' : 'cert-lo'
  return <span className={`cert ${cls}`} title="Xác suất detector thật sự có ùn tắc bất thường ngay hoặc trong 30 phút, ở các trường hợp cùng mức điểm (hiệu chỉnh trên tháng 5)">
    {compact ? '' : 'Chắc chắn '}{v >= 0.995 ? '≥99' : Math.round(v * 100)}%</span>
}

/* ---------------- Thanh lọc + điều khiển phát lại ---------------- */
export function ReplayBar({ meta, st, filters, setFilters, control, view, setView, showTier = true }) {
  const [seekDay, setSeekDay] = useState('')
  const [seekSlot, setSeekSlot] = useState(68)
  const n = st.now
  return (
    <div className="panel filterbar">
      <div className="cell">
        <label className="eyebrow">Loại đường</label>
        <select value={filters.fclass} onChange={(e) => setFilters({ ...filters, fclass: e.target.value })}>
          <option value="">Tất cả loại đường</option>
          {meta.fclasses.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>
      <div className="cell">
        <label className="eyebrow">Mức ưu tiên</label>
        <select value={filters.level} onChange={(e) => setFilters({ ...filters, level: e.target.value })}>
          <option value="">Tất cả mức</option>
          <option>Cao</option><option>Trung bình</option><option>Thấp</option><option>Không đủ dữ liệu</option>
        </select>
      </div>
      <div className="cell">
        <label className="eyebrow">Độ tin cậy dữ liệu</label>
        {showTier && (
          <select value={filters.tier} onChange={(e) => setFilters({ ...filters, tier: e.target.value })}>
            <option value="">Mọi tier (A/B/C)</option>
            <option value="A">Chỉ tier A (đáng tin)</option>
            <option value="AB">Tier A + B</option>
            <option value="C">Tier C (tham khảo)</option>
            <option value="X">X — cần bảo trì</option>
          </select>
        )}
      </div>
      <div className="cell replay">
        <div className="ctrl">
          <button className={`icon-btn ${st.playing ? 'on' : ''}`} title={st.playing ? 'Tạm dừng' : 'Phát live (mỗi khung 15 phút)'}
            onClick={() => control({ action: st.playing ? 'pause' : 'play' })}>{st.playing ? <I.pause size={16} /> : <I.play size={16} />}</button>
          <button className="icon-btn" title="Khung kế tiếp (+15 phút)" onClick={() => control({ action: 'step', n: 1 })}><I.step size={16} /></button>
          <button className="icon-btn" title="Tiến 1 giờ (+4 khung)" onClick={() => control({ action: 'step', n: 4 })}><I.ff size={16} /></button>
          <select className="select" style={{ width: 66, padding: '6px 8px' }} value={st.tick_seconds}
            onChange={(e) => control({ action: 'speed', tick_seconds: Number(e.target.value) })} title="Tốc độ phát">
            <option value={1}>1 s</option><option value={3}>3 s</option><option value={6}>6 s</option><option value={15}>15 s</option>
          </select>
          <details style={{ position: 'relative' }}>
            <summary className="icon-btn" style={{ listStyle: 'none' }} title="Nhảy tới thời điểm"><I.clock size={16} /></summary>
            <div className="panel" style={{ position: 'absolute', zIndex: 1200, top: 40, left: 0, padding: 14, width: 270, display: 'grid', gap: 10 }}>
              <div className="eyebrow">Nhảy tới khung (tháng 6/2015)</div>
              <select className="select" value={seekDay} onChange={(e) => setSeekDay(e.target.value)}>
                <option value="">Chọn ngày…</option>
                {meta.replay_days.map((d) => <option key={d} value={d}>{fmt.date(d)} · {meta.day_types[d]}</option>)}
              </select>
              <select className="select" value={seekSlot} onChange={(e) => setSeekSlot(Number(e.target.value))}>
                {Array.from({ length: 96 }, (_, s) => <option key={s} value={s}>{slotLabel(s)}–{slotLabel((s + 1) % 96)}</option>)}
              </select>
              <div className="row">
                <button className="btn primary sm" disabled={!seekDay} onClick={() => control({ action: 'seek', day: seekDay, slot: seekSlot })}>Nhảy tới</button>
                <button className="btn sm" onClick={() => control({ action: 'reset' })}><I.reset size={14} />Về 01/06</button>
              </div>
            </div>
          </details>
        </div>
        <div className="clock">
          <div className="eyebrow row" style={{ justifyContent: 'flex-end', gap: 6 }}><I.clock size={13} />{n.day_type}</div>
          <div className="big">{fmt.date(n.day)} · {n.label}–{slotLabel((n.slot + 1) % 96)}</div>
          {view ? (
            <div className="viewing" style={{ marginTop: 6 }}>Đang xem lại {slotLabel(view.slot)}
              <button className="link" onClick={() => setView(null)}>Về live</button></div>
          ) : <div className="progress" title="Tiến độ phát lại tháng 6"><div style={{ width: `${n.progress * 100}%` }} /></div>}
        </div>
      </div>
    </div>
  )
}

/* ---------------- Thẻ KPI ---------------- */
export function KpiCards({ counts, prev, total, th }) {
  const items = [
    { k: 'Cao', label: 'Ưu tiên cao', color: 'var(--high)', soft: 'var(--high-soft)', icon: I.alert },
    { k: 'Trung bình', label: 'Ưu tiên trung bình', color: 'var(--med)', soft: 'var(--med-soft)', icon: I.trend },
    { k: 'Thấp', label: 'Ưu tiên thấp', color: 'var(--low)', soft: 'var(--low-soft)', icon: I.radio },
  ]
  return (
    <div className="grid-3">
      {items.map((it) => {
        const v = counts?.[it.k] ?? 0
        const d = prev ? v - (prev[it.k] ?? 0) : null
        return (
          <div className="panel kpi" key={it.k}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div className="ico" style={{ background: it.soft, color: it.color }}><it.icon size={20} /></div>
              <span className="delta">{d === null ? 'khung đầu' : `${d > 0 ? '+' : ''}${d} so với 15 phút trước`}</span>
            </div>
            <div className="eyebrow" style={{ marginTop: 18 }}>{it.label}</div>
            <div style={{ marginTop: 8 }}><span className="num">{v}</span><span className="unit">detector</span></div>
            <div className="bar"><div style={{ width: `${(100 * v) / Math.max(total, 1)}%`, background: it.color }} /></div>
            {it.k === 'Thấp' && <div className="kpi-sub"><span>Không đủ dữ liệu</span><span className="mono">{counts?.['Không đủ dữ liệu'] ?? 0}</span></div>}
            {it.k === 'Cao' && <div className="kpi-sub"><span>Ngưỡng</span><span className="mono">điểm ≥ {th?.high ?? ''}</span></div>}
            {it.k === 'Trung bình' && <div className="kpi-sub"><span>Ngưỡng</span><span className="mono">{th?.medium ?? ''} ≤ điểm &lt; {th?.high ?? ''}</span></div>}
          </div>
        )
      })}
    </div>
  )
}

/* ---------------- Bản đồ ---------------- */
const CLUSTER_COLORS = ['#0a9e6e', '#3b6fd8', '#c2410c', '#8b5cf6', '#64748b']

export function MapView({ rows, selected, onSelect, colorBy = 'level', clusters = [], tall = false }) {
  const pts = useMemo(() => {
    // xòe các detector trùng vị trí (các làn của cùng một điểm đo) thành vòng nhỏ
    const groups = {}
    rows.forEach((r) => {
      if (r.lat == null) return
      const k = `${r.lat.toFixed(4)},${r.long.toFixed(4)}`
      ;(groups[k] = groups[k] || []).push(r)
    })
    const out = []
    Object.values(groups).forEach((g) => {
      const n = g.length
      g.forEach((r, i) => {
        const rad = n > 1 ? 0.00012 + 0.000012 * n : 0
        const a = (2 * Math.PI * i) / n
        out.push({ ...r, plat: r.lat + rad * Math.sin(a) * 0.68, plng: r.long + rad * Math.cos(a) })
      })
    })
    const order = { 'Cao': 3, 'Trung bình': 2, 'Thấp': 1 }
    return out.sort((a, b) => (order[a.level] || 0) - (order[b.level] || 0))
  }, [rows])

  const color = (r) => {
    if (colorBy === 'cluster') {
      const i = clusters.indexOf(r.cluster)
      return i >= 0 ? CLUSTER_COLORS[i % CLUSTER_COLORS.length] : '#a3aeaa'
    }
    if (r.tier === 'X') return '#5b6662'
    return LEVEL_HEX[r.level] || '#a3aeaa'
  }

  return (
    <div className={`mapwrap ${tall ? 'tall' : ''}`}>
      <MapContainer center={[47.0505, 8.3063]} zoom={15} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        {/* Nền OpenStreetMap chuẩn (không cần API key); CSS .map-base làm nhạt màu cho hợp giao diện sáng.
            Nền CARTO trước đây hiện watermark "API Key required". */}
        <TileLayer className="map-base" maxZoom={19} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {pts.map((r) => {
          const sel = r.detid === selected
          const big = r.level === 'Cao'
          return (
            <CircleMarker key={r.detid} center={[r.plat, r.plng]} radius={sel ? 10 : big ? 7 : 5}
              pathOptions={{ color: sel ? '#0f1c18' : '#fff', weight: sel ? 3 : 1.2, fillColor: color(r), fillOpacity: r.level === 'Không đủ dữ liệu' ? 0.45 : 0.92 }}
              eventHandlers={{ click: () => onSelect(r.detid) }}>
              <Tooltip direction="top" offset={[0, -6]}>
                <div style={{ fontWeight: 600 }}>{r.detid}</div>
                <div>{r.road} · {r.fclass}</div>
                <div>Điểm <b>{fmt.score(r.score)}</b> · {r.level}{colorBy === 'cluster' ? ` · ${r.cluster}` : ''}</div>
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <div className="map-chip"><span className="row" style={{ gap: 6 }}><I.radio size={14} /><b className="mono">{rows.filter((r) => r.status === 'Live').length}</b> detector đang gửi số đo</span></div>
    </div>
  )
}

/* ---------------- Hàng đợi ưu tiên ---------------- */
export function PriorityQueue({ rows, selected, onSelect, limit = 10, showDelta = true }) {
  const [q, setQ] = useState('')
  const list = rows.filter((r) => r.score !== null && (!q || r.detid.toLowerCase().includes(q.toLowerCase()) || (r.road || '').toLowerCase().includes(q.toLowerCase()))).slice(0, limit)
  return (
    <>
      <div style={{ padding: '14px 20px' }}>
        <div className="search"><I.search size={16} /><input className="input" placeholder="Tìm detector hoặc tên đường" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      <div className="scroll" style={{ maxHeight: 470 }}>
        <table className="queue">
          <thead><tr><th>#</th><th>Detector</th><th>Vị trí</th><th>Điểm</th><th>Mức</th><th /></tr></thead>
          <tbody>
            {list.map((r, i) => (
              <tr key={r.detid} className={selected === r.detid ? 'sel' : ''} onClick={() => onSelect(r.detid)}>
                <td className="mono muted">{i + 1}</td>
                <td><div className="det">{r.detid.replace('ig11', '')}</div><div className="sub">{r.top_key ? r.top_factor : ''}</div></td>
                <td><div>{r.road}</div><div className="sub">{r.fclass} · tier {r.tier}</div></td>
                <td>
                  <span className="scorecell">{fmt.score(r.score)}</span>{' '}
                  {showDelta && r.delta !== null && Math.abs(r.delta) >= 0.5 && (
                    <span className={r.delta > 0 ? 'delta-up' : 'delta-down'}>{r.delta > 0 ? '▲' : '▼'}{Math.abs(r.delta).toFixed(0)}</span>)}
                  <div className="minibar"><div style={{ width: `${Math.min(100, r.score)}%`, background: LEVEL_HEX[r.level] }} /></div>
                </td>
                <td><LevelBadge level={r.level} /><div style={{ marginTop: 6 }}><Certainty v={r.certainty} compact /></div></td>
                <td style={{ color: 'var(--ink-3)' }}><I.chevron size={16} /></td>
              </tr>
            ))}
            {!list.length && <tr><td colSpan={6} className="empty">Không có detector phù hợp bộ lọc</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

/* ---------------- Dải thời gian 96 khung ---------------- */
export function Timeline({ timeline, st, view, setView }) {
  if (!timeline) return null
  const max = Math.max(10, ...timeline.slots.map((s) => (s.high || 0) + (s.medium || 0)))
  const nowSlot = st.now.day === timeline.day ? st.now.slot : -1
  return (
    <div>
      <div className="strip">
        {timeline.slots.map((s) => {
          const fut = s.high === null
          const cls = ['b', fut ? 'future' : '', s.slot === nowSlot && !view ? 'now' : '', view && view.slot === s.slot ? 'view' : ''].join(' ')
          return (
            <div key={s.slot} className={cls} title={fut ? `${s.label} — chưa tới` : `${s.label}: ${s.high} Cao, ${s.medium} Trung bình`}
              onClick={() => !fut && setView(s.slot === nowSlot ? null : { day: timeline.day, slot: s.slot })}>
              {!fut && <>
                <div className="m" style={{ height: `${(100 * s.medium) / max}%` }} />
                <div className="h" style={{ height: `${(100 * s.high) / max}%` }} />
              </>}
              {fut && <div style={{ height: 3, background: 'var(--line)' }} />}
            </div>
          )
        })}
      </div>
      <div className="strip-axis">{Array.from({ length: 24 }, (_, h) => <span key={h}>{h % 3 === 0 ? `${String(h).padStart(2, '0')}h` : ''}</span>)}</div>
    </div>
  )
}
