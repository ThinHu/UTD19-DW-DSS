import { useMemo, useState } from 'react'
import { api, LEVEL_HEX, fmt, slotLabel } from '../api.js'
import { I } from '../components/Icons.jsx'
import { Certainty, ConfDot, LevelBadge } from '../components/Widgets.jsx'

const SORTS = { score: 'Điểm ưu tiên', occ: 'Occupancy', detid: 'Mã detector' }

export default function Fleet({ win, meta, st, view, setSelected, notify }) {
  const [q, setQ] = useState('')
  const [fclass, setFclass] = useState('')
  const [status, setStatus] = useState('')
  const [tier, setTier] = useState('')
  const [sort, setSort] = useState('score')
  const rows = useMemo(() => {
    if (!win) return []
    let r = win.rows.filter((x) =>
      (!q || x.detid.toLowerCase().includes(q.toLowerCase()) || (x.road || '').toLowerCase().includes(q.toLowerCase()) || (x.cluster || '').toLowerCase().includes(q.toLowerCase())) &&
      (!fclass || x.fclass === fclass) && (!status || x.status === status) && (!tier || x.tier === tier))
    if (sort === 'occ') r = [...r].sort((a, b) => (b.occ ?? -1) - (a.occ ?? -1))
    if (sort === 'detid') r = [...r].sort((a, b) => a.detid.localeCompare(b.detid))
    return r
  }, [win, q, fclass, status, tier, sort])
  const params = view ? { day: view.day, slot: view.slot } : {}
  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <div className="eyebrow">Danh mục mạng lưới</div>
          <div className="panel-title" style={{ fontSize: 22 }}>Detector & hàng đợi ưu tiên <span className="muted" style={{ fontWeight: 400, fontSize: 15 }}>({meta.detectors.length} detector, {st.detectors_active} hoạt động)</span></div>
          <div className="muted" style={{ marginTop: 4 }}>Phủ trung tâm Luzern · khung {fmt.date(win?.day)} {win ? slotLabel(win.slot) : ''}</div>
        </div>
        <div className="panel" style={{ padding: '10px 14px' }}>
          <div className="eyebrow">Đồng bộ gần nhất</div>
          <div className="row mono" style={{ marginTop: 4 }}><span className="dot pulse" />{fmt.date(st.now.day)} · {st.now.label}</div>
        </div>
      </div>
      <div className="panel">
        <div className="toolbar">
          <div><div className="eyebrow" style={{ marginBottom: 6 }}>Tìm trong mạng lưới</div>
            <div className="search"><I.search size={16} /><input className="input" placeholder="Mã detector, tên đường, cụm…" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
          <div className="cell"><label className="eyebrow">Loại đường</label>
            <select value={fclass} onChange={(e) => setFclass(e.target.value)}><option value="">Tất cả</option>{meta.fclasses.map((f) => <option key={f}>{f}</option>)}</select></div>
          <div className="cell"><label className="eyebrow">Trạng thái</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Mọi trạng thái</option><option>Live</option><option>Thiếu số đo</option><option>Offline</option></select></div>
          <div className="cell"><label className="eyebrow">Chất lượng (tier)</label>
            <select value={tier} onChange={(e) => setTier(e.target.value)}><option value="">Mọi tier</option><option value="A">A · lỗi ≤ 25%</option><option value="B">B · 25–50%</option><option value="C">C · &gt; 50%</option><option value="X">X · bảo trì</option></select></div>
        </div>
        <div className="toolbar-actions">
          <button className="exp" onClick={() => { window.location.href = api.windowCsvUrl({ ...params, fclass, tier }) }}><I.download size={15} />Xuất CSV</button>
          <button className="ref" onClick={() => notify('Dữ liệu được làm mới theo từng khung 15 phút')}><I.refresh size={15} />Làm mới dữ liệu</button>
        </div>
        <div className="row" style={{ padding: '10px 18px', borderBottom: '1px solid var(--line)' }}>
          <span className="muted">{rows.length} detector</span><div className="grow" />
          <span className="eyebrow">Sắp xếp</span>
          <select className="select" style={{ width: 170, padding: '6px 10px' }} value={sort} onChange={(e) => setSort(e.target.value)}>{Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        </div>
        <div style={{ overflow: 'auto', maxHeight: 'calc(100vh - 380px)' }}>
          <table className="table">
            <thead><tr><th>Mã detector</th><th>Vị trí / đường</th><th>Điểm ưu tiên</th><th>Mức</th><th>Chắc chắn</th><th className="num">Occ / kỳ vọng</th><th className="num">Lưu lượng / kỳ vọng</th><th>Trạng thái</th><th>Yếu tố chính · hành động</th><th>Chất lượng DL</th><th>Cụm hành vi</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.detid} className="click" onClick={() => setSelected(r.detid)}>
                  <td><span className="row" style={{ gap: 8 }}><span className="dot" style={{ background: r.status === 'Live' ? 'var(--accent)' : r.status === 'Offline' ? 'var(--high)' : 'var(--nd)' }} /><span className="det">{r.detid}</span></span></td>
                  <td><div style={{ fontWeight: 500 }}>{r.road}</div><div className="sub">{r.fclass} · Luzern</div></td>
                  <td><span className="scorecell">{fmt.score(r.score)}</span><span className="muted mono" style={{ fontSize: 11 }}> /100</span>
                    <div className="minibar"><div style={{ width: `${Math.min(100, r.score ?? 0)}%`, background: LEVEL_HEX[r.level] }} /></div></td>
                  <td><LevelBadge level={r.level} /></td>
                  <td><Certainty v={r.certainty} compact /></td>
                  <td className="num">{fmt.occ(r.occ)}<span className="muted"> / {fmt.occ(r.mu_occ)}</span></td>
                  <td className="num">{fmt.int(r.flow)}<span className="muted"> / {fmt.int(r.mu_flow)}</span></td>
                  <td><span className="status"><span className="dot" style={{ background: r.status === 'Live' ? 'var(--accent)' : r.status === 'Offline' ? 'var(--high)' : 'var(--nd)' }} />{r.status === 'Offline' ? `Offline · ${r.x_reason}` : r.status}</span></td>
                  <td style={{ maxWidth: 300 }}><div style={{ fontWeight: 500 }}>{r.top_factor || '—'}</div><div className="sub">{r.action}</div></td>
                  <td><ConfDot c={r.confidence} /></td>
                  <td className="sub">{r.cluster}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
