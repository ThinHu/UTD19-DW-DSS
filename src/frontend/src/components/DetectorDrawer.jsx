import { useEffect, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart, Cell } from 'recharts'
import { api, CRIT, CRIT_SHORT, LEVEL_HEX, LEVEL_KEY, fmt, slotLabel } from '../api.js'
import { I } from './Icons.jsx'
import { Certainty, ConfDot, LevelBadge } from './Widgets.jsx'

function Gauge({ score, level }) {
  const v = score ?? 0
  const r = 46, c = 2 * Math.PI * r
  return (
    <svg className="gauge" viewBox="0 0 112 112">
      <circle cx="56" cy="56" r={r} fill="none" stroke="var(--line)" strokeWidth="9" />
      <circle cx="56" cy="56" r={r} fill="none" stroke={LEVEL_HEX[level] || '#a3aeaa'} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={`${(c * Math.min(v, 100)) / 100} ${c}`} transform="rotate(-90 56 56)" />
      <text x="56" y="56" textAnchor="middle" fontFamily="var(--mono)" fontSize="26" fontWeight="600" fill="var(--ink)">{score === null ? '—' : v.toFixed(0)}</text>
      <text x="56" y="76" textAnchor="middle" fontSize="10" fill="var(--ink-3)">/ 100</text>
    </svg>
  )
}

export function ActionDialog({ row, onClose, onSaved }) {
  const [decision, setDecision] = useState('Chấp nhận')
  const [text, setText] = useState(row.action)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      await api.addAction({ detid: row.detid, decision, action_code: row.action_code, action_text: text, note, operator: 'AN' })
      onSaved()
    } finally { setBusy(false) }
  }
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="panel-h">
          <div><div className="eyebrow">Implementation · ghi nhận quyết định</div><div className="panel-title">{row.detid} · {row.road}</div></div>
          <button className="icon-btn" onClick={onClose}><I.x size={16} /></button>
        </div>
        <div className="panel-b">
          <div className="row"><LevelBadge level={row.level} /><span className="mono">Điểm {fmt.score(row.score)}</span><span className="muted">· {row.top_factor}</span></div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Quyết định của người vận hành</div>
            <div className="seg">
              {['Chấp nhận', 'Điều chỉnh', 'Bỏ qua'].map((d) => <button key={d} className={decision === d ? 'on' : ''} onClick={() => setDecision(d)}>{d}</button>)}
            </div>
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Hành động</div>
            <textarea className="input" rows={2} value={text} onChange={(e) => setText(e.target.value)} disabled={decision === 'Chấp nhận'} />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Ghi chú</div>
            <textarea className="input" rows={2} placeholder="VD: đã liên hệ đội hiện trường, tăng 10 s pha xanh hướng Bahnhof…" value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <div className="note">Sau 30 phút (2 khung), hệ thống tự đối chiếu xem sự kiện ùn tắc có thực sự xảy ra để đánh giá khuyến nghị (trang Cảnh báo).</div>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose}>Hủy</button>
            <button className="btn primary" disabled={busy} onClick={save}><I.check size={16} />Lưu vào nhật ký</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function DetectorDrawer({ id, view, st, meta, onClose, notify }) {
  const [d, setD] = useState(null)
  const [dlg, setDlg] = useState(false)
  const t = st?.now?.t
  useEffect(() => {
    const p = view ? { day: view.day, slot: view.slot } : {}
    api.detector(id, p).then(setD).catch((e) => notify(e.message))
  }, [id, view, t, notify])

  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const now = d?.now
  const series = (d?.series || []).map((s) => ({
    ...s,
    occP: s.occ === null ? null : s.occ * 100,
    muP: s.mu_occ === null ? null : s.mu_occ * 100,
    band: s.mu_occ === null ? null : [Math.max(0, (s.mu_occ - s.sd_occ) * 100), (s.mu_occ + s.sd_occ) * 100],
    fband: s.mu_flow === null ? null : [Math.max(0, s.mu_flow - s.sd_flow), s.mu_flow + s.sd_flow],
  }))
  const lvlKey = now ? LEVEL_KEY[now.level] : ''
  const top = now?.top_key

  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-h">
          <div>
            <div className="eyebrow">Chi tiết detector · {d ? `${fmt.date(d.day)} ${d.label}` : ''}</div>
            <div className="panel-title" style={{ fontSize: 22 }}><span className="mono">{id}</span></div>
            {d && <div className="row wrap" style={{ marginTop: 6 }}>
              <span>{d.info.road}</span><span className="muted">· {d.info.fclass}</span>
              <span className="badge tier">Tier {d.info.tier}</span>
              <span className="badge outline">{d.info.cluster}</span>
              <span className="muted">· {d.day_type}</span>
            </div>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Đóng"><I.x size={18} /></button>
        </div>
        {!d ? <div className="empty">Đang tải…</div> : (
          <div className="drawer-b">
            {d.info.tier === 'X' && <div className="warn">Detector thuộc nhóm X ({d.info.x_reason}) — không được chấm điểm, cần đưa vào kế hoạch bảo trì.</div>}
            {['Thấp', 'Rất thấp'].includes(now.confidence) && <div className="warn">Độ tin cậy dữ liệu {now.confidence.toLowerCase()} (tier {d.info.tier}, lỗi {d.info.error_pct}% khoảng đo). Điểm cao chưa phải kết luận chắc chắn — nên xác minh trước khi điều phối.</div>}

            <div className="panel panel-b scorebox">
              <Gauge score={now.score} level={now.level} />
              <div>
                <div className="row wrap"><LevelBadge level={now.level} /><Certainty v={now.certainty} /><ConfDot c={now.confidence} prefix="Dữ liệu: " /></div>
                {now.score !== null && <div className="certbox">
                  <div><span className="eyebrow">Độ chắc chắn cần chú ý</span><b>{now.certainty >= 0.995 ? '≥99%' : fmt.pct(now.certainty, 0)}</b>
                    <span className="sub">Ở tháng 5, trong số detector có cùng mức điểm, {now.certainty >= 0.995 ? 'gần như tất cả' : fmt.pct(now.certainty, 0)} thật sự ùn tắc bất thường ngay lúc đó hoặc trong 30 phút sau.</span></div>
                  <div><span className="eyebrow">{now.top_key === 'C5' || (now.C1 ?? 0) < 50 ? 'Dự báo 30 phút (mô hình)' : 'Hiện trạng (đo thực tế)'}</span>
                    <b>{now.top_key === 'C5' || (now.C1 ?? 0) < 50 ? fmt.pct(now.p_event30, 0) : `z = ${now.z_occ}`}</b>
                    <span className="sub">{now.top_key === 'C5' || (now.C1 ?? 0) < 50 ? 'Xác suất mô hình dự báo có sự kiện ở 1 trong 2 khung tới.' : `Occupancy đang cao hơn kỳ vọng ${now.z_occ} độ lệch chuẩn (số đo, không phải dự báo). P(ùn 30′) = ${fmt.pct(now.p_event30, 0)}.`}</span></div>
                </div>}
                <div className={`action-box ${lvlKey}`} style={{ marginTop: 12 }}>
                  <div className="eyebrow">Gợi ý hành động · yếu tố chính: {now.top_factor || '—'}</div>
                  <div style={{ fontWeight: 600, marginTop: 6 }}>{now.action}</div>
                </div>
                {!view && now.score !== null && <button className="btn primary sm" style={{ marginTop: 12 }} onClick={() => setDlg(true)}><I.check size={14} />Ghi nhận hành động</button>}
              </div>
            </div>

            <div className="kv">
              <div><span className="eyebrow">Occupancy</span><b>{fmt.occ(now.occ)}</b><span className="sub">kỳ vọng {fmt.occ(now.mu_occ)}</span></div>
              <div><span className="eyebrow">Lưu lượng</span><b>{fmt.int(now.flow)}</b><span className="sub">kỳ vọng {fmt.int(now.mu_flow)} xe/h/làn</span></div>
              <div><span className="eyebrow">z occupancy</span><b>{now.z_occ ?? '—'}</b><span className="sub">so với baseline</span></div>
              <div><span className="eyebrow">z lưu lượng</span><b>{now.z_flow ?? '—'}</b><span className="sub">{now.z_flow < 0 ? 'thấp hơn thường lệ' : 'cao hơn thường lệ'}</span></div>
            </div>

            <div className="panel">
              <div className="panel-h"><div><div className="eyebrow">Đóng góp từng tiêu chí</div><div className="panel-title">Phân rã Priority Score</div></div></div>
              <div className="panel-b">
                <div className="crit-row muted" style={{ fontSize: 11 }}><span className="eyebrow">Tiêu chí</span><span className="eyebrow">Điểm tiêu chí (0–100)</span><span className="eyebrow">Ci</span><span className="eyebrow">w×Ci</span></div>
                {CRIT.map((k) => (
                  <div key={k} className={`crit-row ${top === k ? 'top' : ''}`}>
                    <span><b className="mono">{k}</b> {CRIT_SHORT[k]}</span>
                    <div className="crit-track"><div style={{ width: `${now[k] ?? 0}%` }} /></div>
                    <span className="mono">{now[k] === null ? '—' : now[k].toFixed(0)}</span>
                    <span className="mono muted">{d.contrib[k] ?? '—'}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-h"><div><div className="eyebrow">Occupancy so với baseline ({d.day_type})</div><div className="panel-title">Diễn biến trong ngày</div></div>
                <div className="map-legend"><span><i className="dot" style={{ background: '#0f1c18' }} />Thực đo</span><span><i className="dot" style={{ background: '#9fd9c3' }} />Kỳ vọng ±1σ</span></div></div>
              <div className="panel-b" style={{ height: 230 }}>
                <ResponsiveContainer>
                  <ComposedChart data={series} margin={{ top: 6, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid stroke="#eef1f0" vertical={false} />
                    <XAxis dataKey="label" interval={11} tick={{ fontSize: 10, fontFamily: 'var(--mono)' }} />
                    <YAxis tick={{ fontSize: 10, fontFamily: 'var(--mono)' }} unit="%" />
                    <Tooltip formatter={(v) => (Array.isArray(v) ? `${v[0].toFixed(1)}–${v[1].toFixed(1)}%` : `${Number(v).toFixed(1)}%`)} />
                    <Area dataKey="band" stroke="none" fill="#cdeee0" name="Kỳ vọng ±1σ" isAnimationActive={false} />
                    <Line dataKey="muP" stroke="#0a9e6e" strokeDasharray="4 3" dot={false} strokeWidth={1.5} name="Kỳ vọng" isAnimationActive={false} />
                    <Line dataKey="occP" stroke="#0f1c18" dot={false} strokeWidth={2} name="Thực đo" connectNulls={false} isAnimationActive={false} />
                    <ReferenceLine x={slotLabel(d.slot)} stroke="#d98b0b" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="panel-b" style={{ height: 190, paddingTop: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Lưu lượng (xe/giờ/làn)</div>
                <ResponsiveContainer>
                  <ComposedChart data={series} margin={{ top: 6, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid stroke="#eef1f0" vertical={false} />
                    <XAxis dataKey="label" interval={11} tick={{ fontSize: 10, fontFamily: 'var(--mono)' }} />
                    <YAxis tick={{ fontSize: 10, fontFamily: 'var(--mono)' }} />
                    <Tooltip formatter={(v) => (Array.isArray(v) ? `${v[0].toFixed(0)}–${v[1].toFixed(0)}` : Number(v).toFixed(0))} />
                    <Area dataKey="fband" stroke="none" fill="#dde8fb" isAnimationActive={false} name="Kỳ vọng ±1σ" />
                    <Line dataKey="mu_flow" stroke="#3b6fd8" strokeDasharray="4 3" dot={false} strokeWidth={1.5} isAnimationActive={false} name="Kỳ vọng" />
                    <Line dataKey="flow" stroke="#0f1c18" dot={false} strokeWidth={2} isAnimationActive={false} name="Thực đo" />
                    <ReferenceLine x={slotLabel(d.slot)} stroke="#d98b0b" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="panel-b" style={{ height: 120, paddingTop: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 4 }}>Priority Score theo khung</div>
                <ResponsiveContainer>
                  <BarChart data={series} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                    <XAxis dataKey="label" hide /><YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                    <Tooltip formatter={(v) => Number(v).toFixed(1)} />
                    <Bar dataKey="score" isAnimationActive={false}>{series.map((s, i) => <Cell key={i} fill={LEVEL_HEX[s.level] || '#ccc'} />)}</Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="grid-2e">
              <div className="panel">
                <div className="panel-h"><div><div className="eyebrow">Diễn giải mô hình (cây quyết định)</div><div className="panel-title">Vì sao có nguy cơ?</div></div></div>
                <div className="panel-b">
                  {d.explain.length ? <ul className="rules">{d.explain.map((r, i) => <li key={i}>{r}</li>)}</ul> : <div className="muted">Không có số đo hợp lệ ở khung này.</div>}
                  <div className="note" style={{ marginTop: 10 }}>Đường đi từ gốc tới lá của cây quyết định giải thích (CART, entropy). Xác suất C5 do mô hình chính ({meta?.model?.label}) tính.</div>
                </div>
              </div>
              <div className="panel">
                <div className="panel-h"><div><div className="eyebrow">Tiêu chí C4</div><div className="panel-title">Detector lân cận</div></div></div>
                <div className="panel-b" style={{ padding: 0 }}>
                  <table className="table">
                    <thead><tr><th>Detector</th><th className="num">Cách</th><th className="num">w</th><th>Mức</th></tr></thead>
                    <tbody>
                      {d.neighbors.map((n) => (
                        <tr key={n.detid}><td><div className="det">{n.detid.replace('ig11', '')}</div><div className="sub">{n.road}</div></td>
                          <td className="num">{n.distance_m} m</td><td className="num">{n.weight}</td><td><LevelBadge level={n.level} /></td></tr>
                      ))}
                      {!d.neighbors.length && <tr><td colSpan={4} className="empty">Không có lân cận trong 50–500 m</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}
      </aside>
      {dlg && now && <ActionDialog row={now} onClose={() => setDlg(false)} onSaved={() => { setDlg(false); notify('Đã lưu hành động vào nhật ký') }} />}
    </>
  )
}
