import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmt } from '../api.js'

// Trang Kho dữ liệu & ETL: chế độ nạp, đối soát, cách ly, lược đồ sao, kho siêu dữ liệu, nhật ký ETL (chỉ đọc)
export default function Warehouse() {
  const [q, setQ] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api.dwQuality().then(setQ).catch((e) => setErr(e.message)) }, [])
  if (err) return (
    <div className="panel panel-b">
      <div className="panel-title">Chưa đọc được kho dữ liệu</div>
      <p className="note">{err}</p>
      <pre className="tree">python -m utd19_dw.pipeline            # tự chọn: utd19_u.csv (hạt 3 phút) hoặc bản xuất 15 phút</pre>
    </div>
  )
  if (!q) return <div className="panel empty">Đang tải…</div>
  return <Quality q={q} />
}

/* ------------------------------------------------------------------ */
function Quality({ q }) {
  const li = q.load_info || {}
  return (
    <>
      <div className="stats">
        <div className="stat"><div className="eyebrow">Chế độ nạp</div><div className="v" style={{ fontSize: 16 }}>{li.mode === 'full_3min' ? 'Đầy đủ · hạt 3 phút' : 'Bản xuất · hạt 15 phút'}</div><div className="c">{li.date_start} → {li.date_end}</div></div>
        <div className="stat"><div className="eyebrow">Lần nạp gần nhất</div><div className="v" style={{ fontSize: 16 }}>{(li.loaded_at || '').slice(0, 19)}</div><div className="c mono" style={{ wordBreak: 'break-all' }}>{(li.source || '').split('/').slice(-1)[0]}</div></div>
        <div className="stat"><div className="eyebrow">Đối soát</div><div className="v">{q.reconciliation.filter((r) => r.status === 'PASS').length}/{q.reconciliation.length}</div><div className="c">phép kiểm PASS</div></div>
        <div className="stat"><div className="eyebrow">Dòng bị cách ly</div><div className="v">{fmt.int(q.quarantine.reduce((a, r) => a + r.n, 0))}</div><div className="c">{q.quarantine.map((r) => r.rule_id).join(', ') || 'không có'}</div></div>
      </div>
      <div className="grid-2e">
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">etl.reconciliation</div><div className="panel-title">Đối soát toàn vẹn</div></div></div>
          <table className="table"><thead><tr><th>Mã</th><th>Kiểm tra</th><th className="num">Kỳ vọng</th><th className="num">Thực tế</th><th>KQ</th></tr></thead>
            <tbody>{q.reconciliation.map((r) => <tr key={r.check_id}><td className="mono">{r.check_id}</td><td>{r.description}</td><td className="num">{fmt.int(r.expected)}</td><td className="num">{fmt.int(r.actual)}</td><td><span className={`badge ${r.status === 'PASS' ? 'low' : 'high'}`}>{r.status}</span></td></tr>)}</tbody></table>
        </div>
        <div className="panel">
          <div className="panel-h"><div><div className="eyebrow">mart.detector_day_15min</div><div className="panel-title">Độ phủ khung hợp lệ & tỷ lệ lỗi theo tháng</div></div></div>
          <div className="panel-b" style={{ height: 240 }}>
            <ResponsiveContainer>
              <BarChart data={q.coverage_by_month} margin={{ left: -10 }}>
                <CartesianGrid stroke="#eef1f0" vertical={false} /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis unit="%" tick={{ fontSize: 11 }} /><Tooltip />
                <Bar dataKey="valid_pct" name="Khung hợp lệ (%)" fill="#0a9e6e" radius={[3, 3, 0, 0]} />
                <Bar dataKey="error_pct" name="Khoảng đo bị gắn lỗi (%)" fill="#d98b0b" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">Lược đồ sao (đọc từ catalog DuckDB)</div><div className="panel-title">Fact và các chiều trong schema dw</div></div></div>
        <StarSchema star={q.star} />
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">etl.metadata_catalog · siêu dữ liệu nghiệp vụ + kỹ thuật</div><div className="panel-title">Kho siêu dữ liệu</div></div></div>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="table"><thead><tr><th>Tầng</th><th>Đối tượng</th><th>Vai trò</th><th>Hạt</th><th>Nguồn</th><th>Biến đổi</th><th className="num">Số dòng</th></tr></thead>
            <tbody>{q.catalog.map((r) => <tr key={r.object_name}><td>{r.layer}</td><td><div className="mono">{r.object_name}</div><div className="sub">{r.description}</div></td><td>{r.object_role}</td><td>{r.grain}</td><td className="sub">{r.source}</td><td className="sub">{r.transformation}</td><td className="num">{fmt.int(r.row_count)}</td></tr>)}</tbody></table>
        </div>
      </div>
      <div className="panel">
        <div className="panel-h"><div><div className="eyebrow">etl.run_log</div><div className="panel-title">Nhật ký chạy ETL</div></div></div>
        <div className="scroll" style={{ maxHeight: 360 }}>
          <table className="table"><thead><tr><th>Bước</th><th className="num">Giây</th><th className="num">Số dòng</th><th>Ghi chú</th></tr></thead>
            <tbody>{q.run_log.map((r, i) => <tr key={i}><td className="mono">{r.step}</td><td className="num">{r.seconds}</td><td className="num">{r.rows_out == null ? '—' : fmt.int(r.rows_out)}</td><td className="sub">{r.note}</td></tr>)}</tbody></table>
        </div>
      </div>
    </>
  )
}

function StarSchema({ star }) {
  const tables = Object.fromEntries(star.map((t) => [t.table_name, t.columns]))
  const fact = tables.fact_traffic_15min ? 'fact_traffic_15min' : 'fact_traffic_measurement'
  const dims = ['dim_date', 'dim_time_slot', 'dim_detector', 'dim_road_class', 'dim_weather'].filter((d) => tables[d])
  const Box = ({ name, kind }) => (
    <div className={`star-box ${kind}`}>
      <div className="star-h">{name}</div>
      <div className="star-cols">{(tables[name] || []).slice(0, 12).map((c) => <span key={c} className={c.endsWith('_key') ? 'k' : ''}>{c}</span>)}{(tables[name] || []).length > 12 && <span className="muted">+{tables[name].length - 12} cột</span>}</div>
    </div>)
  return (
    <div className="panel-b star">
      <div className="star-dims">{dims.slice(0, 3).map((d) => <Box key={d} name={d} kind="dim" />)}</div>
      <div className="star-fact"><Box name={fact} kind="fact" />{tables.fact_traffic_measurement && fact !== 'fact_traffic_measurement' && <div className="note">Fact gốc hạt 3 phút: dw.fact_traffic_measurement (gộp thành fact 15 phút)</div>}</div>
      <div className="star-dims">{dims.slice(3).map((d) => <Box key={d} name={d} kind="dim" />)}
        <div className="note">dim_road_class nối qua dim_detector (snowflake một nhánh); dim_weather là outrigger của chiều ngày (cùng khóa date_key).</div></div>
    </div>)
}
