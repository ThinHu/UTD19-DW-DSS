import { I } from '../components/Icons.jsx'
import { KpiCards, MapView, PriorityQueue, ReplayBar, Timeline } from '../components/Widgets.jsx'
import { fmt, slotLabel } from '../api.js'

export default function Overview(p) {
  const { st, win, rows, selected, setSelected, setPage, timeline, view, setView } = p
  const counts = win?.counts
  return (
    <>
      <ReplayBar {...p} />
      <KpiCards counts={view ? win?.counts : st.counts} prev={view ? null : st.counts_prev} total={st.detectors_total} th={st.thresholds} />
      <div className="grid-2">
        <div className="panel">
          <div className="panel-h">
            <div><div className="eyebrow">Phân bố không gian</div><div className="panel-title">Bản đồ mức ưu tiên</div></div>
            <div className="map-legend"><span><i className="dot" style={{ background: 'var(--high)' }} />Cao</span><span><i className="dot" style={{ background: 'var(--med)' }} />Trung bình</span><span><i className="dot" style={{ background: 'var(--low)' }} />Thấp</span><span><i className="dot" style={{ background: 'var(--nd)' }} />Thiếu dữ liệu</span></div>
          </div>
          <MapView rows={rows} selected={selected} onSelect={setSelected} />
        </div>
        <div className="panel">
          <div className="panel-h">
            <div><div className="eyebrow">Xếp hạng {view ? `lúc ${slotLabel(view.slot)}` : 'live'}</div><div className="panel-title">Hàng đợi ưu tiên · Top 10</div></div>
            <button className="link" onClick={() => setPage('fleet')}>Xem tất cả <I.arrow size={16} /></button>
          </div>
          <PriorityQueue rows={rows} selected={selected} onSelect={setSelected} />
        </div>
      </div>
      <div className="panel">
        <div className="panel-h">
          <div><div className="eyebrow">Diễn biến trong ngày · {fmt.date(timeline?.day)}</div><div className="panel-title">Số detector mức Cao / Trung bình theo khung 15 phút</div></div>
          <div className="map-legend"><span><i className="dot" style={{ background: 'var(--high)' }} />Cao</span><span><i className="dot" style={{ background: '#f0c46b' }} />Trung bình</span><span className="muted">Bấm vào cột để xem lại khung đó</span></div>
        </div>
        <div className="panel-b"><Timeline timeline={timeline} st={st} view={view} setView={setView} /></div>
      </div>
      <DecisionPhases />
    </>
  )
}

function DecisionPhases() {
  const ph = [
    ['Intelligence', 'Phát hiện vấn đề', 'Kho dữ liệu (mart.dss_detector_window) + baseline theo loại ngày (K-means) → C1–C4 phát hiện bất thường hiện tại'],
    ['Design', 'Dự báo & phương án', 'Học máy (Gradient Boosting) dự báo nguy cơ 30 phút (C5); bảng quyết định sinh phương án hành động'],
    ['Choice', 'Chọn ưu tiên', 'Priority Score có trọng số tối ưu → xếp hạng top 10; ngưỡng Cao/TB chọn theo F1/F2 trên tháng 5 (hoặc goal seeking theo năng lực ca trực), kèm độ chắc chắn đã hiệu chỉnh'],
    ['Implementation', 'Thực thi', 'Người vận hành xác nhận / điều chỉnh / bỏ qua, lưu nhật ký hành động'],
    ['Evaluation', 'Đánh giá', 'Đối chiếu sự kiện thực tế sau 30 phút, theo dõi precision/recall của cảnh báo'],
  ]
  return (
    <div className="panel">
      <div className="panel-h"><div><div className="eyebrow">Quy trình ra quyết định (Simon) trong DSS</div><div className="panel-title">Hệ thống hỗ trợ ở từng giai đoạn</div></div></div>
      <div className="panel-b phase">
        {ph.map(([a, b, c], i) => <div key={a}><span className="eyebrow">{i + 1} · {a}</span><b>{b}</b><span>{c}</span></div>)}
      </div>
    </div>
  )
}
