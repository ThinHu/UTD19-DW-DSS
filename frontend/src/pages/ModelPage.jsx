import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmt } from '../api.js'

const DAY_NOTE = {
  '2015-01-01': 'Năm mới', '2015-01-02': 'Berchtoldstag', '2015-02-12': 'Schmutziger Donnerstag — mở màn Fasnacht Luzern',
  '2015-02-13': 'Fasnacht', '2015-02-16': 'Güdismontag (Fasnacht)', '2015-02-17': 'Güdisdienstag (Fasnacht)',
  '2015-04-03': 'Thứ Sáu Tuần Thánh', '2015-04-06': 'Thứ Hai Phục Sinh', '2015-05-14': 'Lễ Thăng Thiên',
  '2015-05-15': 'Ngày cầu sau lễ Thăng Thiên', '2015-05-25': 'Thứ Hai Hiện Xuống', '2015-06-04': 'Lễ Mình Máu Thánh Chúa',
}
const TYPE_VN = { WD: 'Ngày làm việc', SAT: 'Thứ Bảy', SUN: 'Chủ nhật / Lễ' }
const DOW = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN']
const COLORS = ['#0a9e6e', '#3b6fd8', '#c2410c', '#8b5cf6', '#64748b']
const ORDER = ['dt', 'nb', 'mlp', 'gb', 'persistence', 'rule_v4']
const LABEL = { dt: 'Decision Tree (CART)', nb: 'Naive Bayes', mlp: 'Neural Network (MLP)', gb: 'Gradient Boosting (ensemble cây)', persistence: 'Persistence (mốc)', rule_v4: 'Điểm luật v4 (mốc)' }

export default function ModelPage() {
  const [m, setM] = useState(null)
  const [tab, setTab] = useState('dm')
  useEffect(() => { api.model().then(setM) }, [])
  if (!m) return <div className="panel empty">Đang tải…</div>
  return (
    <>
      <div className="tabs">
        {[['dm', 'Mô hình quyết định & kiến trúc'], ['ml', 'Học có giám sát (C5)'], ['km', 'Học không giám sát (K-means)'], ['data', 'Dữ liệu & không gian']].map(([k, v]) =>
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      {tab === 'dm' && <DecisionModel m={m} />}
      {tab === 'ml' && <Supervised m={m} />}
      {tab === 'km' && <Unsupervised m={m} />}
      {tab === 'data' && <DataTab m={m} />}
    </>
  )
}

function Supervised({ m }) {
  const v = m.models_valid, t = m.models_test
  const chart = ORDER.map((k) => ({ name: LABEL[k], valid: v[k]?.pr_auc, test: k === m.best_model || t[k] ? (t[k] || {}).pr_auc : null }))
  return (
    <>
      <div className="stats">
        <div className="stat"><div className="eyebrow">Huấn luyện</div><div className="v">{fmt.int(m.train_rows)}</div><div className="c">{fmt.date(m.split.train[0])} – {fmt.date(m.split.train[1])} · dương {fmt.pct(m.pos_rate.train)}</div></div>
        <div className="stat"><div className="eyebrow">Kiểm định</div><div className="v">{fmt.int(m.valid_rows)}</div><div className="c">tháng 5/2015 · dương {fmt.pct(m.pos_rate.valid)}</div></div>
        <div className="stat"><div className="eyebrow">Kiểm thử (phát lại)</div><div className="v">{fmt.int(m.test_rows)}</div><div className="c">tháng 6/2015 · dương {fmt.pct(m.pos_rate.test)}</div></div>
        <div className="stat"><div className="eyebrow">Mô hình được chọn</div><div className="v" style={{ fontSize: 17 }}>{m.best_model_label}</div><div className="c">PR-AUC lớn nhất trên tập kiểm định</div></div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Bài toán: dự báo sự kiện ùn tắc bất thường trong 30 phút tới (nhãn mất cân bằng)</div><div className="panel-title">So sánh mô hình trên tập kiểm định (tháng 5)</div></div></div>
        <div style={{ overflow: 'auto' }}>
          <table className="table">
            <thead><tr><th>Mô hình</th><th className="num">PR-AUC</th><th className="num">ROC-AUC</th><th className="num">Precision</th><th className="num">Recall</th><th className="num">F1</th><th className="num">Recall sự kiện mới</th><th className="num">Brier</th><th className="num">Huấn luyện (s)</th><th>Tham số</th></tr></thead>
            <tbody>
              {ORDER.map((k) => v[k] && (
                <tr key={k} className={k === m.best_model ? 'best' : ''}>
                  <td style={{ fontWeight: 500 }}>{LABEL[k]}</td>
                  <td className="num">{v[k].pr_auc}</td><td className="num">{v[k].roc_auc}</td><td className="num">{fmt.pct(v[k].precision)}</td>
                  <td className="num">{fmt.pct(v[k].recall)}</td><td className="num">{v[k].f1}</td><td className="num">{fmt.pct(v[k].onset_recall)}</td>
                  <td className="num">{v[k].brier}</td><td className="num">{v[k].fit_seconds}</td><td className="sub">{JSON.stringify(v[k].params).replace(/[{}"]/g, '')}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <div className="panel-b note">Precision/Recall/F1 tại ngưỡng cho F1 lớn nhất. “Recall sự kiện mới”: tỷ lệ bắt được sự kiện mà ở khung hiện tại chưa có bất thường — phần mà mốc Persistence không thể dự báo. Naive Bayes kém vì giả định độc lập bị vi phạm (các đặc trưng trễ của z-score tương quan mạnh).</div>
      </div>
      <div className="grid-2e">
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">PR-AUC · kiểm định (T5) và kiểm thử ngoài mẫu (T6)</div><div className="panel-title">Học máy so với các mốc không học</div></div></div>
          <div className="panel-b" style={{ height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={chart} margin={{ left: -10 }}>
                <CartesianGrid stroke="#eef1f0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10.5 }} interval={0} angle={-12} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10.5 }} />
                <Tooltip /><Legend />
                <Bar dataKey="valid" name="Kiểm định (T5)" fill="#0a9e6e" radius={[3, 3, 0, 0]} />
                <Bar dataKey="test" name="Kiểm thử (T6)" fill="#3b6fd8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Cây quyết định · quét độ sâu</div><div className="panel-title">Chọn max_depth theo PR-AUC</div></div></div>
          <div className="panel-b" style={{ height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={m.dt_scan} margin={{ left: -10 }}>
                <CartesianGrid stroke="#eef1f0" /><XAxis dataKey="max_depth" tick={{ fontSize: 11 }} /><YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
                <Tooltip /><Line dataKey="pr_auc" stroke="#0a9e6e" strokeWidth={2} name="PR-AUC" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <CertaintyPanel m={m} />
      <div className="grid-2e">
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Tầm quan trọng đặc trưng (cây giải thích)</div><div className="panel-title">Yếu tố mô hình dựa vào nhiều nhất</div></div></div>
          <div className="panel-b" style={{ height: 380 }}>
            <ResponsiveContainer>
              <BarChart data={m.feature_importance} layout="vertical" margin={{ left: 40 }}>
                <XAxis type="number" tick={{ fontSize: 10.5 }} /><YAxis type="category" dataKey="feature" tick={{ fontSize: 10.5, fontFamily: 'var(--mono)' }} width={110} />
                <Tooltip /><Bar dataKey="importance" fill="#0a9e6e" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Luật rút ra (4 tầng đầu)</div><div className="panel-title">Cây quyết định giải thích</div></div></div>
          <div className="panel-b"><pre className="tree">{m.tree_text}</pre></div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Kiểm thử ngoài mẫu — tháng 6/2015 (mô hình huấn luyện lại trên 01/01–31/05)</div><div className="panel-title">Kết quả trên dữ liệu phát lại live</div></div></div>
        <table className="table">
          <thead><tr><th>Mô hình</th><th className="num">PR-AUC</th><th className="num">ROC-AUC</th><th className="num">Precision</th><th className="num">Recall</th><th className="num">F1</th><th className="num">Recall sự kiện mới</th></tr></thead>
          <tbody>{Object.entries(t).map(([k, r]) => (
            <tr key={k} className={k === m.best_model ? 'best' : ''}><td>{LABEL[k]}</td><td className="num">{r.pr_auc}</td><td className="num">{r.roc_auc}</td><td className="num">{fmt.pct(r.precision)}</td><td className="num">{fmt.pct(r.recall)}</td><td className="num">{r.f1}</td><td className="num">{fmt.pct(r.onset_recall)}</td></tr>))}</tbody>
        </table>
      </div>
    </>
  )
}

function CertaintyPanel({ m }) {
  const c = m.certainty_curve
  const th = m.thresholds
  const sw = (m.threshold_sweep_valid || []).map((r) => ({ ...r, precision: r.precision * 100, recall: r.recall * 100, f1: r.f1 * 100, f2: r.f2 * 100 }))
  const swT = Object.fromEntries((m.threshold_sweep_test || []).map((r) => [r.threshold, r]))
  const data = (c || []).map((v, s) => ({ s, p: v * 100 }))
  const chosen = (m.threshold_sweep_valid || []).find((r) => r.threshold === th.high)
  return (
    <div className="grid-2e">
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Quét ngưỡng trên tháng 5 · “cần chú ý” = sự kiện ngay hoặc trong 30 phút</div><div className="panel-title">Chọn ngưỡng: Cao = F1 lớn nhất, Trung bình = F2 lớn nhất</div></div></div>
        <div className="panel-b" style={{ height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={sw} margin={{ left: -10 }}>
              <CartesianGrid stroke="#eef1f0" /><XAxis dataKey="threshold" tick={{ fontSize: 11 }} />
              <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} /><Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} labelFormatter={(s) => `Ngưỡng ${s}`} /><Legend />
              <ReferenceLine x={th.high} stroke="#d64545" strokeDasharray="4 3" /><ReferenceLine x={th.medium} stroke="#d98b0b" strokeDasharray="4 3" />
              <Line dataKey="precision" name="Precision" stroke="#d64545" dot={false} />
              <Line dataKey="recall" name="Recall" stroke="#3b6fd8" dot={false} />
              <Line dataKey="f1" name="F1" stroke="#0a9e6e" strokeWidth={2.5} dot={false} />
              <Line dataKey="f2" name="F2" stroke="#d98b0b" strokeDasharray="5 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {chosen && <div className="panel-b note">Ngưỡng Cao {th.high}: tháng 5 precision {fmt.pct(chosen.precision)}, recall {fmt.pct(chosen.recall)} (bắt {fmt.pct(chosen.recall_now)} sự kiện đang diễn ra, {fmt.pct(chosen.recall_future)} sự kiện sắp xảy ra), {chosen.alerts_per_window} cảnh báo/khung.
          {swT[th.high] && <> Kiểm chứng tháng 6: precision {fmt.pct(swT[th.high].precision)}, recall {fmt.pct(swT[th.high].recall)}.</>} Trung bình {th.medium}: ưu tiên không bỏ sót cho mức theo dõi.</div>}
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Hiệu chỉnh isotonic trên tháng 5 · hiển thị là “độ chắc chắn”</div><div className="panel-title">Priority Score → xác suất thật sự cần chú ý</div></div></div>
        <div className="panel-b" style={{ height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ left: -10 }}>
              <CartesianGrid stroke="#eef1f0" /><XAxis dataKey="s" type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
              <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} /><Tooltip formatter={(v) => `${Number(v).toFixed(0)}%`} labelFormatter={(s) => `Điểm ${s}`} />
              <ReferenceLine x={th.high} stroke="#d64545" strokeDasharray="4 3" /><ReferenceLine x={th.medium} stroke="#d98b0b" strokeDasharray="4 3" />
              <Line dataKey="p" stroke="#0a9e6e" strokeWidth={2} dot={false} name="P(cần chú ý)" type="stepAfter" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="panel-b note">Mỗi khuyến nghị hiển thị “Chắc chắn x%” lấy từ đường này: trong tháng 5, x% detector có cùng mức điểm thật sự có sự kiện ngay hoặc trong 30 phút sau (tỷ lệ nền ≈ 4%). Đây là độ chắc chắn của khuyến nghị, khác với chất lượng dữ liệu đo.</div>
      </div>
    </div>
  )
}

function Unsupervised({ m }) {
  const kd = m.kmeans_days, kdet = m.kmeans_detectors
  const cent = Array.from({ length: 96 }, (_, s) => {
    const o = { label: `${String(Math.floor(s / 4)).padStart(2, '0')}:${String((s % 4) * 15).padStart(2, '0')}` }
    Object.entries(kd.centroids).forEach(([k, v]) => { o[TYPE_VN[k]] = v[s] })
    return o
  })
  const prof = Array.from({ length: 24 }, (_, h) => {
    const o = { h: `${String(h).padStart(2, '0')}h` }
    Object.entries(kdet.profiles).forEach(([k, v]) => { o[k] = v[h] * 100 })
    return o
  })
  const types = ['WD', 'SAT', 'SUN']
  return (
    <>
      <div className="grid-2e">
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">K-means trên hồ sơ lưu lượng 96 khung/ngày (151 ngày lịch sử)</div><div className="panel-title">Phân cụm ngày → loại ngày cho baseline</div></div></div>
          <div className="panel-b" style={{ height: 290 }}>
            <ResponsiveContainer>
              <LineChart data={cent} margin={{ left: -10 }}>
                <CartesianGrid stroke="#eef1f0" vertical={false} /><XAxis dataKey="label" interval={11} tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} />
                <Tooltip /><Legend />
                {types.map((k, i) => <Line key={k} dataKey={TYPE_VN[k]} stroke={COLORS[i]} dot={false} strokeWidth={2} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="panel-b" style={{ paddingTop: 0 }}>
            <table className="table">
              <thead><tr><th>Thứ</th>{types.map((k) => <th key={k} className="num">{TYPE_VN[k]}</th>)}</tr></thead>
              <tbody>{DOW.map((d, i) => <tr key={d}><td>{d}</td>{types.map((k) => <td key={k} className="num">{kd.crosstab[k]?.[i] ?? 0}</td>)}</tr>)}</tbody>
            </table>
            <div className="note" style={{ marginTop: 8 }}>Silhouette theo k: {kd.scan.map((s) => `k=${s.k}: ${s.silhouette}`).join(' · ')}. Chọn k = 3 để tách Thứ Bảy và Chủ nhật — hai loại có hồ sơ khác nhau rõ.</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Ngày bị K-means xếp khác lịch thường</div><div className="panel-title">Ngày lễ & ngày đặc biệt được phát hiện</div></div></div>
          <table className="table">
            <thead><tr><th>Ngày</th><th>Lịch</th><th>Cụm K-means</th><th className="num">Mức lưu lượng</th><th>Ghi chú</th></tr></thead>
            <tbody>{kd.mismatch.map((r) => (
              <tr key={r.day}><td className="mono">{fmt.date(r.day)}</td><td>{TYPE_VN[r.calendar]}</td><td><b>{TYPE_VN[r.cluster]}</b></td><td className="num">{r.level}</td><td className="sub">{DAY_NOTE[r.day] || ''}</td></tr>))}
            </tbody>
          </table>
          <div className="panel-b note">Ngày lễ chính thức của bang Luzern đã được gán sẵn vào “Chủ nhật / Lễ” nên không hiện ở đây; K-means xếp tất cả các ngày đó vào cụm Chủ nhật, xác nhận cách gán. Năm ngày còn lại (Fasnacht, ngày cầu) được loại khỏi baseline.</div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">K-means trên hồ sơ occupancy 24 giờ (chuẩn hóa z) của ngày làm việc</div><div className="panel-title">Cụm hành vi detector (k = {kdet.k})</div></div>
          <div className="map-legend">{Object.entries(kdet.sizes).map(([k, v], i) => <span key={k}><i className="dot" style={{ background: COLORS[i] }} />{k}: {v}</span>)}</div></div>
        <div className="panel-b" style={{ height: 300 }}>
          <ResponsiveContainer>
            <LineChart data={prof} margin={{ left: -10 }}>
              <CartesianGrid stroke="#eef1f0" vertical={false} /><XAxis dataKey="h" tick={{ fontSize: 10 }} /><YAxis unit="%" tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} /><Legend />
              {Object.keys(kdet.profiles).map((k, i) => <Line key={k} dataKey={k} stroke={COLORS[i]} dot={false} strokeWidth={2} />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="panel-b note">Silhouette: {kdet.scan.map((s) => `k=${s.k}: ${s.silhouette} (${s.sizes.join('/')})`).join(' · ')}. Từ k = 4 trở lên xuất hiện cụm chỉ 1 detector nên chọn k = {kdet.k}. Cụm được dùng làm đặc trưng cho mô hình C5 và để lọc trên bản đồ.</div>
      </div>
    </>
  )
}

function DataTab({ m }) {
  const p = m.profile
  return (
    <div className="grid-2e">
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Nguồn: {p.source}</div><div className="panel-title">Hồ sơ dữ liệu Luzern</div></div></div>
        <table className="table"><tbody>
          <tr><td>Số dòng khung 15 phút</td><td className="num">{fmt.int(p.rows)}</td></tr>
          <tr><td>Detector / ngày</td><td className="num">{p.detectors} / {p.days} ({fmt.date(p.first_day)} – {fmt.date(p.last_day)})</td></tr>
          <tr><td>Tỷ lệ khoảng đo bị gắn error</td><td className="num">{p.error_rows_pct}% (trung vị theo detector {p.error_median}%)</td></tr>
          <tr><td>Tier A / B / C / X</td><td className="num">{['A', 'B', 'C', 'X'].map((k) => p.tiers[k]).join(' / ')}</td></tr>
          <tr><td>Khung bị loại (slot 96 · cảm biến kẹt · không hợp lệ)</td><td className="num">{fmt.int(p.dropped.slot_out_of_range)} · {fmt.int(p.dropped.stuck_windows)} · {fmt.int(p.dropped.invalid_windows)}</td></tr>
          <tr><td>Loại ngày (làm việc / T7 / CN-lễ)</td><td className="num">{p.day_type_counts.WD} / {p.day_type_counts.SAT} / {p.day_type_counts.SUN}</td></tr>
          {Object.entries(p.fclass).map(([k, v]) => <tr key={k}><td className="sub">fclass = {k}</td><td className="num">{v}</td></tr>)}
        </tbody></table>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Phần dư occupancy (đã trừ baseline & mức chung), detector tier A</div><div className="panel-title">Tương quan theo khoảng cách → bán kính C4</div></div></div>
        <table className="table">
          <thead><tr><th>Khoảng cách</th><th className="num">Số cặp</th><th className="num">Tương quan TB</th><th className="num">Trung vị</th></tr></thead>
          <tbody>{m.spatial_corr.map((r) => <tr key={r.bin}><td>{r.bin}</td><td className="num">{fmt.int(r.pairs)}</td><td className="num">{r.mean}</td><td className="num">{r.median}</td></tr>)}</tbody>
        </table>
        <div className="panel-b note">Tương quan về ~0 từ 0,5 km nên C4 dùng kernel Gaussian với d_max = 0,5 km, σ = 0,3 km, loại cặp &lt; 50 m (các làn cùng điểm đo). Trung vị {m.neighbors_per_detector.median} lân cận hợp lệ mỗi detector.</div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Mô hình quyết định (Ch.5, Ch.7) và kiến trúc DSS (Ch.6)              */
/* ------------------------------------------------------------------ */
function DecisionModel({ m }) {
  const w = m.weights, th = m.thresholds
  return (
    <>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Phát biểu bài toán quyết định</div><div className="panel-title">Mỗi 15 phút: ưu tiên kiểm tra / can thiệp ở detector nào, bằng hành động gì?</div></div></div>
        <div className="panel-b">
          <table className="table">
            <tbody>
              <tr><td style={{ width: 230 }}><b>Người ra quyết định</b></td><td>Điều phối viên ca trực tại trung tâm điều hành giao thông (cá nhân, cấp tác nghiệp); quyết định cuối cùng thuộc về con người — DSS chỉ đề xuất (Alter: mô hình gợi ý).</td></tr>
              <tr><td><b>Loại bài toán</b></td><td>Bán cấu trúc, lặp lại (có thể lập trình một phần): phần phát hiện bất thường có luật rõ; phần dự báo và chọn hành động cần phán đoán của người vận hành.</td></tr>
              <tr><td><b>Loại mô hình</b></td><td>Động (dynamic) — trạng thái thay đổi theo từng khung 15 phút, đặc trưng trễ t−1..t−3; quyết định <b>trong điều kiện rủi ro</b>: kết quả không chắc chắn nhưng ước lượng được xác suất (C5 = P(sự kiện trong 30′), độ chắc chắn hiệu chỉnh isotonic).</td></tr>
              <tr><td><b>Nguyên tắc lựa chọn</b></td><td>Tối đa hóa Precision@10 (đội trực xem 10 detector đầu bảng) khi chọn trọng số; ngưỡng mức Cao/Trung bình theo F1/F2; ràng buộc năng lực ca trực tối đa {th.max_high || '∞'} cảnh báo Cao mỗi khung (phần vượt vào hàng chờ). Có thể chuyển sang thỏa mãn mục tiêu (goal seeking) ở trang What-if.</td></tr>
              <tr><td><b>Phương án (alternatives)</b></td><td>13 hành động trong bảng quyết định: bình thường, theo dõi, hàng chờ, cảnh báo sớm, can thiệp, điều phối hiện trường/VMS, phối hợp khu vực, xác minh thiết bị, bảo trì…</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Thành phần mô hình toán (Chương 7)</div><div className="panel-title">Biến quyết định · biến không kiểm soát · biến kết quả</div></div></div>
        <div className="panel-b vars">
          <div className="dv"><b>Biến quyết định</b> (người dùng / DSS chọn)
            <ul><li>Trọng số w₁…w₅ của C1–C5 (đang dùng {['C1', 'C2', 'C3', 'C4', 'C5'].map((k) => w[k]).join(' / ')})</li><li>Ngưỡng mức Cao = {th.high}, Trung bình = {th.medium}; năng lực ca trực N = {th.max_high || '∞'}</li><li>Số detector xem mỗi khung (top-K = 10)</li><li>Hành động chọn cho từng cảnh báo (chấp nhận / điều chỉnh / bỏ qua)</li></ul></div>
          <div className="uv"><b>Biến không kiểm soát</b> (môi trường)
            <ul><li>Occupancy, lưu lượng đo được mỗi khung</li><li>Loại ngày, ngày lễ, sự kiện đặc biệt (Fasnacht)</li><li>Sự cố, thời tiết, công trình (chưa quan sát trực tiếp)</li><li>Lỗi cảm biến (tỷ lệ khoảng đo bị gắn error)</li></ul></div>
          <div className="rv"><b>Biến kết quả</b> (đo hiệu quả)
            <ul><li>Precision / recall của cảnh báo mức Cao</li><li>Recall sự kiện đang diễn ra và sắp xảy ra (≤ 30′)</li><li>Số cảnh báo mỗi khung = khối lượng việc của ca trực</li><li>Precision@10 của bảng xếp hạng</li></ul></div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Sơ đồ ảnh hưởng (influence diagram)</div><div className="panel-title">Từ dữ liệu kho đến hành động và kết quả</div></div>
          <div className="map-legend"><span><i className="dot" style={{ background: '#0a9e6e', borderRadius: 2 }} />Biến quyết định</span><span><i className="dot" style={{ background: '#d98b0b' }} />Không kiểm soát</span><span><i className="dot" style={{ background: '#94a3b8' }} />Trung gian</span><span><i className="dot" style={{ background: '#3b6fd8' }} />Kết quả</span></div></div>
        <div className="panel-b influence"><InfluenceDiagram />
          <div className="note">Bảng quyết định còn dùng trực tiếp C1, C3, z lưu lượng và tier để chọn <i>loại</i> hành động (lược bớt mũi tên cho dễ đọc). Thời tiết, sự cố là biến không kiểm soát chưa đưa vào mô hình — thời tiết đã có chỗ trong kho (dw.dim_weather) để phân tích OLAP trước khi đưa thành đặc trưng.</div></div>
      </div>

      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Kiến trúc DSS (Chương 6) — 4 phân hệ</div><div className="panel-title">Thành phần hệ thống và nơi hiện thực</div></div></div>
        <div className="panel-b arch">
          <div><span className="eyebrow">Quản lý dữ liệu</span><b>Kho dữ liệu DuckDB</b>
            <ul><li>ETL staging → clean → lược đồ sao → data mart</li><li>Fact 3 phút + fact tổng hợp 15 phút; 6 chiều</li><li>Kho siêu dữ liệu, đối soát, cách ly</li><li>dss_results.duckdb: điểm live + nhật ký hành động</li></ul></div>
          <div><span className="eyebrow">Quản lý mô hình</span><b>Model base + MBMS</b>
            <ul><li>Thống kê: baseline μ/σ theo loại ngày × khung</li><li>Gom cụm K-means (ngày, detector)</li><li>Phân lớp: DT, Naive Bayes, MLP, Gradient Boosting</li><li>Tổng hợp đa tiêu chí (tổng có trọng số), tối ưu lưới, hiệu chỉnh isotonic</li><li>build.py + meta.json: dựng, chọn, lưu phiên bản mô hình</li></ul></div>
          <div><span className="eyebrow">Tri thức</span><b>Luật & giải thích</b>
            <ul><li>Bảng quyết định 13 luật → hành động</li><li>Luật rút từ cây quyết định giải thích từng cảnh báo</li><li>Luật chất lượng dữ liệu (tier A/B/C/X)</li></ul></div>
          <div><span className="eyebrow">Giao diện (dialog)</span><b>Dashboard web</b>
            <ul><li>Xếp hạng live, bản đồ, chi tiết detector</li><li>What-if, độ nhạy, goal seeking</li><li>Trang kho dữ liệu: đối soát, siêu dữ liệu ETL</li><li>Ghi nhận quyết định & đánh giá sau 30′</li></ul></div>
        </div>
        <div className="panel-b note" style={{ paddingTop: 0 }}>
          <b>Phân loại.</b> Theo Holsapple & Whinston: <b>DSS phức hợp</b> (compound) — hướng cơ sở dữ liệu (kho + OLAP) + hướng bộ giải (mô hình ML, tối ưu trọng số) + hướng luật (bảng quyết định). Theo Power: <b>DSS lai</b> (data-driven + model-driven + knowledge-driven). Theo Alter: hệ <b>gợi ý</b> (suggestion) — đầu ra đề xuất hành động cụ thể nhưng người vận hành quyết định. Triển khai dạng <b>web-based DSS</b>, phát triển theo <b>prototyping</b> (v4 → v5).
        </div>
      </div>

      {m.decision_table && (
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">Bảng quyết định (decision table) · luật đầu tiên khớp được áp dụng</div><div className="panel-title">Điều kiện → hành động gợi ý</div></div></div>
          <table className="table">
            <thead><tr><th className="num">#</th><th>Mức ưu tiên</th><th>Điều kiện</th><th>Hành động</th><th>Mã</th></tr></thead>
            <tbody>{m.decision_table.map((r) => <tr key={r.rule}><td className="num">{r.rule}</td><td>{r.level}</td><td>{r.condition}</td><td style={{ fontWeight: 500 }}>{r.action}</td><td className="mono muted">{r.code}</td></tr>)}</tbody>
          </table>
        </div>)}
    </>
  )
}

function InfluenceDiagram() {
  const N = {
    occ: [70, 60, 'Occupancy, lưu lượng', 'u'], cal: [70, 150, 'Loại ngày / lễ', 'u'], err: [70, 240, 'Lỗi cảm biến', 'u'],
    base: [250, 150, 'Baseline μ, σ', 'm'], z: [250, 60, 'z occupancy / flow', 'm'], tier: [250, 240, 'Tier dữ liệu', 'm'],
    c13: [430, 40, 'C1 · C2 · C3', 'm'], c4: [430, 110, 'C4 lân cận', 'm'], c5: [430, 180, 'C5 = P(ùn 30′) — ML', 'm'],
    w: [430, 262, 'Trọng số w₁…w₅', 'd'], score: [610, 110, 'Priority Score', 'm'], th: [610, 210, 'Ngưỡng Cao / TB', 'd'],
    lvl: [780, 110, 'Mức ưu tiên', 'm'], act: [945, 245, 'Hành động (bảng QĐ)', 'd'],
    r1: [1110, 50, 'Precision / recall', 'r'], r2: [1110, 135, 'Số cảnh báo / khung', 'r'], r3: [1110, 245, 'Sự kiện bị bỏ sót', 'r'],
  }
  const E = [['occ', 'z'], ['cal', 'base'], ['base', 'z'], ['err', 'tier'], ['z', 'c13'], ['z', 'c4'], ['z', 'c5'], ['tier', 'c5'], ['cal', 'c5'],
    ['c13', 'score'], ['c4', 'score'], ['c5', 'score'], ['w', 'score'], ['score', 'lvl'], ['th', 'lvl'], ['lvl', 'act'],
    ['lvl', 'r1'], ['lvl', 'r2'], ['act', 'r3']]
  const W = 150, H = 38
  const col = { u: ['#fdf2df', '#d98b0b'], m: ['#f1f5f9', '#94a3b8'], d: ['#e2f5ed', '#0a9e6e'], r: ['#e8eefb', '#3b6fd8'] }
  return (
    <svg viewBox="0 0 1200 300" role="img" aria-label="Sơ đồ ảnh hưởng của DSS">
      <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 10 5 0 10z" fill="#94a3b8" /></marker></defs>
      {E.map(([a, b], i) => {
        const [x1, y1] = N[a], [x2, y2] = N[b]
        return <line key={i} x1={x1 + W / 2} y1={y1} x2={x2 - W / 2 - 2} y2={y2} stroke="#cbd5e1" strokeWidth="1.3" markerEnd="url(#ah)" />
      })}
      {Object.entries(N).map(([k, [x, y, t, kind]]) => {
        const [fill, stroke] = col[kind]
        const rx = kind === 'd' ? 3 : kind === 'r' ? 10 : 19
        return (
          <g key={k}>
            <rect x={x - W / 2} y={y - H / 2} width={W} height={H} rx={rx} fill={fill} stroke={stroke} strokeWidth={kind === 'd' ? 2 : 1.3} />
            <text x={x} y={y + 4} textAnchor="middle" fontSize="11.5" fill="#0f1c18" fontFamily="var(--sans)">{t}</text>
          </g>)
      })}
    </svg>
  )
}
