import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import { I, Logo } from './components/Icons.jsx'
import DetectorDrawer from './components/DetectorDrawer.jsx'
import Overview from './pages/Overview.jsx'
import MapPage from './pages/MapPage.jsx'
import Fleet from './pages/Fleet.jsx'
import Alerts from './pages/Alerts.jsx'
import ModelPage from './pages/ModelPage.jsx'
import WhatIf from './pages/WhatIf.jsx'
import Warehouse from './pages/Warehouse.jsx'

const PAGES = [
  { id: 'overview', icon: I.grid, tip: 'Tổng quan ưu tiên', crumb: 'Trung tâm điều hành / Mạng lưới live', title: 'Tổng quan ưu tiên giao thông' },
  { id: 'map', icon: I.map, tip: 'Bản đồ mạng lưới', crumb: 'Trung tâm điều hành / Bản đồ', title: 'Bản đồ detector trung tâm Luzern' },
  { id: 'fleet', icon: I.radio, tip: 'Danh sách detector', crumb: 'Trung tâm điều hành / Mạng lưới / Detector', title: 'Danh sách detector & hàng đợi ưu tiên' },
  { id: 'alerts', icon: I.alert, tip: 'Cảnh báo & nhật ký', crumb: 'Trung tâm điều hành / Cảnh báo', title: 'Cảnh báo, hành động & đánh giá' },
  { id: 'model', icon: I.brain, tip: 'Mô hình học máy', crumb: 'Mô hình / Phân tích', title: 'Mô hình hỗ trợ ra quyết định' },
  { id: 'whatif', icon: I.sliders, tip: 'What-if & goal seeking', crumb: 'Mô hình / Phân tích độ nhạy', title: 'Trọng số, ngưỡng, what-if & goal seeking' },
  { id: 'dw', icon: I.db, tip: 'Kho dữ liệu & ETL', crumb: 'Kho dữ liệu / ETL', title: 'Kho dữ liệu: nạp, đối soát & siêu dữ liệu' },
]

export default function App() {
  const [page, setPage] = useState('overview')
  const [meta, setMeta] = useState(null)
  const [st, setSt] = useState(null)
  const [view, setView] = useState(null)          // null = khung live hiện tại; {day, slot} = xem lại
  const [win, setWin] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [filters, setFilters] = useState({ fclass: '', level: '', tier: '' })
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)
  const [err, setErr] = useState(null)
  const lastT = useRef(null)

  const notify = useCallback((m) => { setToast(m); setTimeout(() => setToast(null), 2600) }, [])

  useEffect(() => { api.meta().then(setMeta).catch((e) => setErr(e.message)) }, [])

  const refreshState = useCallback(() => api.state().then((s) => { setSt(s); setErr(null) }).catch((e) => setErr(e.message)), [])
  useEffect(() => {
    refreshState()
    const id = setInterval(refreshState, 1500)
    return () => clearInterval(id)
  }, [refreshState])

  const nowT = st?.now?.t
  const viewKey = view ? `${view.day}-${view.slot}` : 'live'
  useEffect(() => {
    if (nowT === undefined) return
    const params = view ? { day: view.day, slot: view.slot } : {}
    api.window(params).then(setWin).catch((e) => notify(e.message))
    const day = view ? view.day : st.now.day
    if (lastT.current !== nowT || view) api.timeline(day).then(setTimeline).catch(() => {})
    lastT.current = nowT
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nowT, viewKey])

  const control = useCallback(async (body) => {
    try {
      const s = await api.replay(body)
      setSt(s)
      if (body.action !== 'play' && body.action !== 'pause' && body.action !== 'speed') setView(null)
    } catch (e) { notify(e.message) }
  }, [notify])

  const rows = useMemo(() => {
    if (!win) return []
    return win.rows.filter((r) =>
      (!filters.fclass || r.fclass === filters.fclass) &&
      (!filters.level || r.level === filters.level) &&
      (!filters.tier || (filters.tier === 'AB' ? ['A', 'B'].includes(r.tier) : r.tier === filters.tier)))
  }, [win, filters])

  const P = PAGES.find((p) => p.id === page)
  const ctx = { meta, st, win, rows, timeline, filters, setFilters, view, setView, control, selected, setSelected, notify, setPage }

  return (
    <div className="app">
      <aside className="sidebar">
        <Logo />
        {PAGES.map((p) => (
          <button key={p.id} className={`nav-btn ${page === p.id ? 'active' : ''}`} onClick={() => setPage(p.id)} aria-label={p.tip}>
            <p.icon /><span className="tip">{p.tip}</span>
          </button>
        ))}
        <div className="spacer" />
        <div className="avatar" title="Người vận hành ca trực">AN</div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="crumb">{P.crumb}</div>
            <h1 className="title">{P.title}</h1>
          </div>
          <div className="sysbadge">
            {err ? <span style={{ color: 'var(--high)' }}>● Mất kết nối API</span> : (
              <span className="row" style={{ gap: 8 }}><span className={`dot ${st?.playing ? 'pulse' : ''}`} />
                {st?.playing ? 'Đang phát live' : 'Tạm dừng'}</span>)}
            <span><b className="mono" style={{ color: 'var(--ink)' }}>{st?.detectors_active ?? '—'}</b> / {st?.detectors_total ?? '—'} detector hoạt động</span>
            <span>Luzern · UTD19</span>
          </div>
        </header>

        <div className="content">
          {!meta || !st ? <div className="panel empty">{err ? `Không kết nối được API: ${err}` : 'Đang tải dữ liệu…'}</div> : (
            <>
              {page === 'overview' && <Overview {...ctx} />}
              {page === 'map' && <MapPage {...ctx} />}
              {page === 'fleet' && <Fleet {...ctx} />}
              {page === 'alerts' && <Alerts {...ctx} />}
              {page === 'model' && <ModelPage {...ctx} />}
              {page === 'whatif' && <WhatIf {...ctx} />}
              {page === 'dw' && <Warehouse {...ctx} />}
            </>
          )}
        </div>
      </main>

      {selected && <DetectorDrawer id={selected} view={view} st={st} meta={meta} onClose={() => setSelected(null)} notify={notify} />}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
