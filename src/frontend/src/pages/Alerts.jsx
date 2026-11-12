import { useEffect, useState } from 'react'
import { api, fmt, slotLabel } from '../api.js'
import { ActionDialog } from '../components/DetectorDrawer.jsx'
import { Certainty, ConfDot, LevelBadge } from '../components/Widgets.jsx'

export default function Alerts({ win, st, setSelected, notify }) {
  const [log, setLog] = useState([])
  const [ev, setEv] = useState(null)
  const [dlg, setDlg] = useState(null)
  const t = st.now.t
  const load = () => {
    api.actions().then(setLog).catch(() => {})
    api.model().then((m) => setEv({ v5: m.live_eval, v4: m.live_eval_v4 })).catch(() => {})
  }
  useEffect(load, [t])
  const highs = (win?.rows || []).filter((r) => r.level === 'Cao')
  const queue = (win?.rows || []).filter((r) => r.action_code === 'QUEUE')
  const outc = log.reduce((a, r) => ({ ...a, [r.outcome]: (a[r.outcome] || 0) + 1 }), {})
  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-h">
            <div><div className="eyebrow">Choice · khung {fmt.date(win?.day)} {win ? slotLabel(win.slot) : ''}</div><div className="panel-title">Cảnh báo mức Cao cần xử lý ({highs.length}){queue.length > 0 && <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}> · {queue.length} trong hàng chờ</span>}</div></div>
          </div>
          <div className="scroll" style={{ maxHeight: 520 }}>
            <table className="table">
              <thead><tr><th>Detector</th><th>Điểm</th><th>Gợi ý hành động</th><th>Chắc chắn</th><th>Chất lượng DL</th><th /></tr></thead>
              <tbody>
                {highs.map((r) => (
                  <tr key={r.detid}>
                    <td className="click" onClick={() => setSelected(r.detid)} style={{ cursor: 'pointer' }}><div className="det">{r.detid.replace('ig11', '')}</div><div className="sub">{r.road}</div></td>
                    <td><span className="scorecell">{fmt.score(r.score)}</span><div className="sub">P30′ {fmt.pct(r.p_event30, 0)}</div></td>
                    <td style={{ maxWidth: 340 }}><div style={{ fontWeight: 500 }}>{r.action}</div><div className="sub">{r.top_factor}</div></td>
                    <td><Certainty v={r.certainty} compact /></td>
                    <td><ConfDot c={r.confidence} /></td>
                    <td><button className="btn sm primary" onClick={() => setDlg(r)}>Ghi nhận</button></td>
                  </tr>
                ))}
                {!highs.length && <tr><td colSpan={6} className="empty">Không có cảnh báo mức Cao trong khung này</td></tr>}
                {queue.length > 0 && <tr><td colSpan={6} className="sub" style={{ background: 'var(--panel-2)' }}>Hàng chờ — điểm đạt mức Cao nhưng ca trực đã đủ {st.thresholds?.max_high} cảnh báo trong khung này; xử lý khi có người rảnh</td></tr>}
                {queue.map((r) => (
                  <tr key={r.detid} style={{ opacity: 0.8 }}>
                    <td className="click" onClick={() => setSelected(r.detid)} style={{ cursor: 'pointer' }}><div className="det">{r.detid.replace('ig11', '')}</div><div className="sub">{r.road}</div></td>
                    <td><span className="scorecell">{fmt.score(r.score)}</span><div className="sub">P30′ {fmt.pct(r.p_event30, 0)}</div></td>
                    <td style={{ maxWidth: 340 }}><div style={{ fontWeight: 500 }}>Hàng chờ</div><div className="sub">{r.top_factor}</div></td>
                    <td><Certainty v={r.certainty} compact /></td>
                    <td><ConfDot c={r.confidence} /></td>
                    <td><button className="btn sm" onClick={() => setDlg(r)}>Ghi nhận</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Evaluation · trên các khung đã phát lại</div><div className="panel-title">Chất lượng cảnh báo</div></div></div>
          <div className="panel-b" style={{ display: 'grid', gap: 14 }}>
            {ev && ev.v5.windows > 0 ? (
              <>
                <div className="note">Nhãn thật: detector có sự kiện ùn tắc bất thường ngay tại khung hoặc trong 30 phút sau. So sánh DSS v5 (có học máy) với v4 (chỉ trọng số C1–C4, ngưỡng 70/40) trên cùng {fmt.int(ev.v5.windows)} khung.</div>
                <table className="table">
                  <thead><tr><th>Chỉ số</th><th className="num">v5 (ML)</th><th className="num">v4</th></tr></thead>
                  <tbody>
                    <tr><td>Precision@10 (top 10 mỗi khung)</td><td className="num">{fmt.pct(ev.v5.p_at_10)}</td><td className="num">{fmt.pct(ev.v4.p_at_10)}</td></tr>
                    <tr><td>Precision cảnh báo Cao</td><td className="num">{fmt.pct(ev.v5.high_precision)}</td><td className="num">{fmt.pct(ev.v4.high_precision)}</td></tr>
                    <tr><td>Recall sự kiện ở mức Cao</td><td className="num">{fmt.pct(ev.v5.event_recall_high)}</td><td className="num">{fmt.pct(ev.v4.event_recall_high)}</td></tr>
                    <tr><td>Số detector Cao mỗi khung</td><td className="num">{ev.v5.high_per_window}</td><td className="num">{ev.v4.high_per_window}</td></tr>
                    <tr><td>Số sự kiện cần chú ý</td><td className="num" colSpan={2}>{fmt.int(ev.v5.events)}</td></tr>
                  </tbody>
                </table>
              </>
            ) : <div className="muted">Cần phát lại thêm vài khung để có nhãn 30 phút.</div>}
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Kết quả các hành động đã ghi nhận</div>
              <div className="stats">
                {['Có sự kiện trong 30 phút', 'Không xảy ra sự kiện', 'Chờ dữ liệu', 'Không đủ dữ liệu'].map((k) => (
                  <div className="stat" key={k}><div className="eyebrow" style={{ fontSize: 9.5 }}>{k}</div><div className="v">{outc[k] || 0}</div></div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Implementation · lưu trong DuckDB (dss.action_log)</div><div className="panel-title">Nhật ký hành động của người vận hành</div></div></div>
        <div style={{ overflow: 'auto' }}>
          <table className="table">
            <thead><tr><th>#</th><th>Khung</th><th>Detector</th><th>Mức · điểm</th><th>Quyết định</th><th>Hành động</th><th>Ghi chú</th><th>Kết quả sau 30 phút</th></tr></thead>
            <tbody>
              {log.map((r) => (
                <tr key={r.id}>
                  <td className="mono muted">{r.id}</td><td className="mono">{r.window_label}</td>
                  <td><div className="det">{r.detid.replace('ig11', '')}</div><div className="sub">{r.road}</div></td>
                  <td><LevelBadge level={r.priority_level} /> <span className="mono">{fmt.score(r.priority_score)}</span></td>
                  <td>{r.decision}</td><td style={{ maxWidth: 320 }}>{r.action_text}</td><td className="sub" style={{ maxWidth: 220 }}>{r.note || '—'}</td>
                  <td><span className={`badge ${r.outcome.startsWith('Có') ? 'high' : r.outcome.startsWith('Không xảy') ? 'low' : 'nd'}`}>{r.outcome}</span></td>
                </tr>
              ))}
              {!log.length && <tr><td colSpan={8} className="empty">Chưa có hành động nào. Mở một cảnh báo và bấm “Ghi nhận”.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {dlg && <ActionDialog row={dlg} onClose={() => setDlg(null)} onSaved={() => { setDlg(null); notify('Đã lưu hành động'); load() }} />}
    </>
  )
}
