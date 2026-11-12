import { useEffect, useMemo, useRef, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, CRIT, CRIT_SHORT, fmt } from '../api.js'
import { LevelBadge } from '../components/Widgets.jsx'

export default function WhatIf({ meta, st, notify, setSelected }) {
  const [w, setW] = useState(st.weights || meta.weights)
  const [th, setTh] = useState(st.thresholds || meta.thresholds)
  const [res, setRes] = useState(null)
  const [m, setM] = useState(null)
  const timer = useRef(null)
  const sum = useMemo(() => CRIT.reduce((a, k) => a + Number(w[k] || 0), 0), [w])
  const norm = (k) => (sum > 0 ? w[k] / sum : 0)

  useEffect(() => { api.model().then(setM) }, [])
  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      if (sum <= 0) return
      api.whatif({ weights: w, thresholds: th }).then(setRes).catch((e) => notify(e.message))
    }, 250)
    return () => clearTimeout(timer.current)
  }, [w, th, st.now.t, sum, notify])

  const apply = async () => {
    await api.whatif({ weights: w, thresholds: th, apply: true })
    notify('Đã áp dụng trọng số & ngưỡng mới cho toàn hệ thống')
  }
  const cmp = (a, b, higherBetter = true) => (a == null || b == null || Math.abs(a - b) < 1e-9 ? '' : (a > b) === higherBetter ? 'better' : 'worse')

  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Mô hình quyết định · Priority = Σ wᵢ·Cᵢ</div><div className="panel-title">Trọng số tiêu chí</div></div>
            <div className="row">
              <button className="btn sm" onClick={() => { setW(meta.weights_default); setTh(meta.thresholds) }}>Trọng số tối ưu</button>
              <button className="btn sm" onClick={() => { setW(meta.weights_v4); setTh({ high: 70, medium: 40, max_high: 0 }) }}>Trọng số v4</button>
            </div></div>
          <div className="panel-b">
            {CRIT.map((k) => (
              <div className="slider-row" key={k}>
                <span><b className="mono">{k}</b> {CRIT_SHORT[k]}</span>
                <input type="range" min={0} max={0.6} step={0.05} value={w[k]} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} />
                <span className="mono" title="Sau chuẩn hóa tổng = 1">{norm(k).toFixed(2)}</span>
              </div>
            ))}
            <div className="note">Trọng số tự chuẩn hóa để tổng bằng 1 (cột phải). Trọng số tối ưu được tìm bằng lưới bước 0,05 trên tháng 5 (mỗi trọng số trong [0,05; 0,50]), mục tiêu là precision@10 của detector cần chú ý ngay hoặc trong 30 phút.</div>
            <div className="eyebrow" style={{ marginTop: 16 }}>Ngưỡng phân loại</div>
            <div className="slider-row"><span>Cao: điểm ≥</span><input type="range" min={20} max={90} step={5} value={th.high} onChange={(e) => setTh({ ...th, high: Number(e.target.value) })} /><span className="mono">{th.high}</span></div>
            <div className="slider-row"><span>Trung bình: điểm ≥</span><input type="range" min={10} max={80} step={5} value={th.medium} onChange={(e) => setTh({ ...th, medium: Math.min(Number(e.target.value), th.high - 5) })} /><span className="mono">{th.medium}</span></div>
            <div className="slider-row" title="Năng lực ca trực: mỗi khung chỉ giữ N detector điểm cao nhất ở mức Cao, phần vượt chuyển vào hàng chờ (0 = không giới hạn)"><span>Năng lực ca trực: tối đa Cao / khung</span><input type="range" min={0} max={30} step={1} value={th.max_high || 0} onChange={(e) => setTh({ ...th, max_high: Number(e.target.value) })} /><span className="mono">{th.max_high ? th.max_high : '∞'}</span></div>
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}><button className="btn primary" onClick={apply}>Áp dụng cho hệ thống</button></div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Khung hiện tại · {fmt.date(st.now.day)} {st.now.label}</div><div className="panel-title">Tác động của thay đổi</div></div></div>
          <div className="panel-b" style={{ display: 'grid', gap: 14 }}>
            {res && <>
              <div className="stats">
                {['Cao', 'Trung bình', 'Thấp'].map((L) => <div className="stat" key={L}><div className="eyebrow">{L}</div><div className="v">{res.counts[L]}</div><div className="c">đang dùng: {res.counts_current[L]}</div></div>)}
                <div className="stat"><div className="eyebrow">Top 10 trùng</div><div className="v">{res.overlap_top10}/10</div><div className="c">so với cấu hình đang dùng</div></div>
              </div>
              {res.eval.windows > 0 && (
                <table className="table">
                  <thead><tr><th>Trên {fmt.int(res.eval.windows)} khung đã phát lại</th><th className="num">Cấu hình thử</th><th className="num">Đang dùng</th></tr></thead>
                  <tbody>
                    <tr><td>Precision@10</td><td className={`num ${cmp(res.eval.p_at_10, res.eval_current.p_at_10)}`}>{fmt.pct(res.eval.p_at_10)}</td><td className="num">{fmt.pct(res.eval_current.p_at_10)}</td></tr>
                    <tr><td>Precision cảnh báo Cao</td><td className={`num ${cmp(res.eval.high_precision, res.eval_current.high_precision)}`}>{fmt.pct(res.eval.high_precision)}</td><td className="num">{fmt.pct(res.eval_current.high_precision)}</td></tr>
                    <tr><td>Recall sự kiện ở mức Cao</td><td className={`num ${cmp(res.eval.event_recall_high, res.eval_current.event_recall_high)}`}>{fmt.pct(res.eval.event_recall_high)}</td><td className="num">{fmt.pct(res.eval_current.event_recall_high)}</td></tr>
                    <tr><td>Số detector Cao / khung</td><td className="num">{res.eval.high_per_window}</td><td className="num">{res.eval_current.high_per_window}</td></tr>
                  </tbody>
                </table>)}
              <table className="table">
                <thead><tr><th>#</th><th>Detector</th><th className="num">Điểm</th><th>Mức</th><th className="num">Hạng cũ</th></tr></thead>
                <tbody>{res.rows.slice(0, 10).map((r, i) => (
                  <tr key={r.detid} className="click" onClick={() => setSelected(r.detid)}>
                    <td className="mono muted">{i + 1}</td><td><div className="det">{r.detid.replace('ig11', '')}</div><div className="sub">{r.road}</div></td>
                    <td className="num">{fmt.score(r.score)}</td><td><LevelBadge level={r.level} /></td>
                    <td className="num">{r.old_rank}{r.old_rank !== i + 1 && <span className={r.old_rank > i + 1 ? 'delta-up' : 'delta-down'}> {r.old_rank > i + 1 ? '▲' : '▼'}</span>}</td>
                  </tr>))}</tbody>
              </table>
            </>}
          </div>
        </div>
      </div>
      <GoalSeekPanel w={w} notify={notify} onApplied={(th2) => setTh(th2)} />
      {m && (
        <div className="grid-2e">
          <div className="panel">
            <div className="panel-h"><div><div className="eyebrow">Tối ưu trên tập kiểm định (tháng 5)</div><div className="panel-title">10 bộ trọng số tốt nhất</div></div></div>
            <table className="table">
              <thead><tr>{CRIT.map((k) => <th key={k} className="num">{k}</th>)}<th className="num">P@10</th></tr></thead>
              <tbody>{m.weights_top.map((r, i) => <tr key={i} className={i === 0 ? 'best' : ''}>{CRIT.map((k) => <td key={k} className="num">{r[k].toFixed(2)}</td>)}<td className="num">{fmt.pct(r.p_at_10)}</td></tr>)}</tbody>
            </table>
            <div className="panel-b note">Precision@10 của v4 (0,45/0,20/0,25/0,10/0) trên cùng tháng 5: {fmt.pct(m.p_at_10.valid_v4)}; v5 tối ưu: {fmt.pct(m.p_at_10.valid_v5)}. Trên tháng 6 (ngoài mẫu): v5 {fmt.pct(m.p_at_10.test_v5)} so với v4 {fmt.pct(m.p_at_10.test_v4)}.</div>
          </div>
          <div className="panel">
            <div className="panel-h"><div><div className="eyebrow">Phân tích độ nhạy (thay một trọng số, bù vào C1 hoặc C5)</div><div className="panel-title">Precision@10 khi lệch khỏi tối ưu</div></div></div>
            <div style={{ maxHeight: 420, overflow: 'auto' }}>
              <table className="table">
                <thead><tr><th>Tiêu chí</th><th className="num">Δ</th><th>Bù vào</th><th className="num">P@10</th><th className="num">Chênh</th></tr></thead>
                <tbody>{m.sensitivity.map((r, i) => {
                  const d = r.p_at_10 - m.p_at_10.valid_v5
                  return <tr key={i}><td className="mono">{r.criterion}</td><td className="num">{r.delta > 0 ? '+' : ''}{r.delta.toFixed(2)}</td><td className="mono">{r.compensate}</td><td className="num">{fmt.pct(r.p_at_10)}</td><td className={`num ${d < -0.001 ? 'worse' : ''}`}>{(d * 100).toFixed(2)} đ%</td></tr>
                })}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

const GOALS = [
  { key: 'precision', label: 'Precision mức Cao ít nhất', unit: '%', def: 75, step: 5, hint: 'Đội điều phối chỉ muốn nhận cảnh báo đúng ít nhất x% → ngưỡng thấp nhất đạt được (giữ recall cao nhất).' },
  { key: 'recall', label: 'Recall mức Cao ít nhất', unit: '%', def: 60, step: 5, hint: 'Không được bỏ sót quá (100 − x)% sự kiện → ngưỡng cao nhất vẫn đạt (giữ precision cao nhất).' },
  { key: 'alerts', label: 'Năng lực ca trực: tối đa N cảnh báo Cao / khung (ở 95% khung)', unit: '', def: 6, step: 1, hint: 'Ràng buộc nguồn lực: số detector đội trực xử lý được trong 15 phút, tính cả giờ cao điểm (phân vị 95).' },
]

function GoalSeekPanel({ w, notify, onApplied }) {
  const [goal, setGoal] = useState('precision')
  const g = GOALS.find((x) => x.key === goal)
  const [val, setVal] = useState(g.def)
  const [res, setRes] = useState(null)
  const body = () => ({ goal, value: g.unit === '%' ? val / 100 : val, weights: w })
  const run = () => api.goalSeek(body()).then(setRes).catch((e) => notify(e.message))
  useEffect(() => { setVal(g.def) }, [goal]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const id = setTimeout(run, 250); return () => clearTimeout(id) }, [goal, val, w]) // eslint-disable-line react-hooks/exhaustive-deps
  const apply = () => api.goalSeek({ ...body(), apply: true }).then((r) => { setRes(r); onApplied(r.thresholds); notify(`Đã đặt ngưỡng Cao = ${r.thresholds.high}`) }).catch((e) => notify(e.message))
  const data = (res?.curve || []).map((r) => ({ t: r.threshold, p: r.precision == null ? null : r.precision * 100, r: r.recall * 100, a: r.alerts_p95 }))
  const P = res?.pick, C = res?.current, Lv = res?.live
  return (
    <div className="panel">
      <div className="panel-h"><div><div className="eyebrow">Goal seeking (Chương 7) · ngược với what-if: cho trước kết quả mong muốn → tìm biến quyết định</div>
        <div className="panel-title">Tìm ngưỡng mức Cao thỏa mục tiêu vận hành</div></div></div>
      <div className="grid-2e" style={{ padding: 0 }}>
        <div className="panel-b" style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
          <div className="seg">{GOALS.map((x) => <button key={x.key} className={goal === x.key ? 'on' : ''} onClick={() => setGoal(x.key)}>{x.key === 'precision' ? 'Độ đúng' : x.key === 'recall' ? 'Độ phủ' : 'Năng lực ca trực'}</button>)}</div>
          <div className="slider-row"><span>{g.label}</span>
            <input type="range" min={g.unit === '%' ? 20 : 1} max={g.unit === '%' ? 99 : 20} step={g.step} value={val} onChange={(e) => setVal(Number(e.target.value))} />
            <span className="mono">{val}{g.unit}</span></div>
          <div className="note">{g.hint} Đường cong dựng trên tháng 5 (tập kiểm định) với trọng số đang chỉnh ở trên; cột “Tháng 6 đã phát lại” kiểm chứng ngoài mẫu.</div>
          {res && (!res.feasible ? <div className="warn">Không có ngưỡng nào đạt mục tiêu này với trọng số hiện tại — cần nới mục tiêu hoặc đổi trọng số (đánh đổi precision ↔ recall).</div> : (
            <>
              <table className="table">
                <thead><tr><th /><th className="num">Ngưỡng đề xuất: {P.threshold}</th><th className="num">Tháng 6 đã phát lại</th><th className="num">Đang dùng: {C?.threshold ?? '—'}</th></tr></thead>
                <tbody>
                  <tr><td>Precision mức Cao</td><td className="num">{fmt.pct(P.precision)}</td><td className="num">{Lv ? fmt.pct(Lv.precision) : '—'}</td><td className="num">{C ? fmt.pct(C.precision) : '—'}</td></tr>
                  <tr><td>Recall mức Cao</td><td className="num">{fmt.pct(P.recall)}</td><td className="num">{Lv ? fmt.pct(Lv.recall) : '—'}</td><td className="num">{C ? fmt.pct(C.recall) : '—'}</td></tr>
                  <tr><td>Cảnh báo Cao / khung (TB)</td><td className="num">{P.alerts_per_window}</td><td className="num">{Lv ? Lv.alerts_per_window : '—'}</td><td className="num">{C ? C.alerts_per_window : '—'}</td></tr>
                  <tr><td>Cảnh báo Cao ở 95% khung / tối đa</td><td className="num">{P.alerts_p95} / {P.alerts_max}</td><td className="num">{Lv ? `${Lv.alerts_p95} / ${Lv.alerts_max}` : '—'}</td><td className="num">{C ? `${C.alerts_p95} / ${C.alerts_max}` : '—'}</td></tr>
                </tbody>
              </table>
              <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" onClick={apply}>Áp dụng ngưỡng {P.threshold}</button></div>
            </>))}
        </div>
        <div className="panel-b" style={{ height: 330 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ left: -10, right: 6 }}>
              <CartesianGrid stroke="#eef1f0" /><XAxis dataKey="t" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="l" unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} />
              <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip labelFormatter={(t) => `Ngưỡng ${t}`} formatter={(v, n) => (n.includes('cảnh báo') ? v : `${Number(v).toFixed(1)}%`)} /><Legend />
              {P && <ReferenceLine yAxisId="l" x={P.threshold} stroke="#0a9e6e" strokeWidth={2} label={{ value: `đề xuất ${P.threshold}`, fontSize: 11, position: 'top' }} />}
              {C && <ReferenceLine yAxisId="l" x={C.threshold} stroke="#d64545" strokeDasharray="4 3" />}
              {goal !== 'alerts' && <ReferenceLine yAxisId="l" y={val} stroke="#94a3b8" strokeDasharray="2 3" />}
              {goal === 'alerts' && <ReferenceLine yAxisId="r" y={val} stroke="#94a3b8" strokeDasharray="2 3" />}
              <Line yAxisId="l" dataKey="p" name="Precision" stroke="#d64545" dot={false} />
              <Line yAxisId="l" dataKey="r" name="Recall" stroke="#3b6fd8" dot={false} />
              <Line yAxisId="r" dataKey="a" name="Số cảnh báo (95% khung)" stroke="#d98b0b" dot={false} strokeDasharray="5 3" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
