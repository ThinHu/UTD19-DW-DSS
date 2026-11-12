import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTooltip, useMap } from 'react-leaflet'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmt } from '../api.js'

const METRICS = {
  avg_occupancy_pct: { label: 'Occupancy TB', unit: '%' },
  avg_flow: { label: 'Flow TB', unit: ' xe/giờ/làn' },
}
const WEEKDAYS = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']
const fmtValue = (value, unit = '') => value == null ? '—' : Number(value).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + unit
const metricValue = (row, key) => row?.[key] == null ? null : Number(row[key])
const validRange = (scope) => Boolean(scope.start && scope.end && scope.start <= scope.end)

function MetricButtons({ value, onChange }) {
  return <div className="olap-segment" aria-label="Chọn chỉ số phân tích">
    {Object.entries(METRICS).map(([key, item]) =>
      <button key={key} type="button" className={value === key ? 'active' : ''} onClick={() => onChange(key)}>{item.label}</button>)}
  </div>
}

function TimeDrill({ scope, title = 'Diễn biến giao thông', selectedMetric }) {
  const [drill, setDrill] = useState({ level: 'year' })
  const [localMetric, setLocalMetric] = useState('avg_occupancy_pct')
  const metric = selectedMetric ?? localMetric
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!validRange(scope)) return
    let active = true
    setLoading(true)
    setError('')
    const query = { ...scope, group_by: drill.level }
    if (drill.year) query.year = drill.year
    if (drill.month) query.month = drill.month
    if (drill.day) query.date_value = drill.day
    if (drill.hour != null) query.hour = drill.hour
    api.olapQuery(query).then((value) => { if (active) setResult(value) })
      .catch((err) => { if (active) { setResult(null); setError(err.message) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope.start, scope.end, scope.road_name, scope.detid, drill])

  const rows = result?.rows || []
  function selectPoint(row) {
    if (!row) return
    if (drill.level === 'year') setDrill({ level: 'month', year: Number(row.group_key) })
    else if (drill.level === 'month') setDrill({ level: 'day', year: drill.year, month: Number(String(row.group_key).split('-')[1]) })
    else if (drill.level === 'day') setDrill({ level: 'hour', year: drill.year, month: drill.month, day: row.group_key })
    else if (drill.level === 'hour') setDrill({ ...drill, level: 'slot', hour: Number(row.group_key) })
  }
  const hourLabel = drill.hour == null ? '' : String(drill.hour).padStart(2, '0') + ':00'

  return <section className="panel olap-analysis-panel">
    <div className="olap-section-head"><div><div className="olap-section-label">Năm → Tháng → Ngày → Giờ → 15 phút</div><h3>{title}</h3></div>
      {selectedMetric == null && <MetricButtons value={metric} onChange={setLocalMetric} />}</div>
    <div className="olap-trail">
      <button type="button" className={drill.level === 'year' ? 'current' : ''} onClick={() => setDrill({ level: 'year' })}>Năm</button>
      {drill.year && <><span className="olap-chevron">›</span><button type="button" className={drill.level === 'month' ? 'current' : ''} onClick={() => setDrill({ level: 'month', year: drill.year })}>{drill.year} · Tháng</button></>}
      {drill.month && <><span className="olap-chevron">›</span><button type="button" className={drill.level === 'day' ? 'current' : ''} onClick={() => setDrill({ level: 'day', year: drill.year, month: drill.month })}>Tháng {drill.month} · Ngày</button></>}
      {drill.day && <><span className="olap-chevron">›</span><button type="button" className={drill.level === 'hour' ? 'current' : ''} onClick={() => setDrill({ level: 'hour', year: drill.year, month: drill.month, day: drill.day })}>{fmt.date(drill.day)} · Giờ</button></>}
      {drill.level === 'slot' && <><span className="olap-chevron">›</span><span>{hourLabel} · 15 phút</span></>}
    </div>
    {error && <div className="warn" role="alert">{error}</div>}
    {loading && <p className="olap-small">Đang tải biểu đồ…</p>}
    {!loading && !error && (rows.length ? <div className="olap-chart">
      <ResponsiveContainer><LineChart key={metric} data={rows} margin={{ top: 16, right: 24, bottom: 8, left: 0 }}
        onClick={(event) => selectPoint(event?.activePayload?.[0]?.payload)}>
        <CartesianGrid stroke="#e8eeea" vertical={false} />
        <XAxis dataKey="group_label" tick={{ fontSize: 11 }} minTickGap={drill.level === 'day' ? 26 : 8} />
        <YAxis tick={{ fontSize: 11 }} width={55} unit={metric === 'avg_occupancy_pct' ? '%' : ''} />
        <Tooltip formatter={(value) => fmtValue(value, METRICS[metric].unit)} />
        <Line type="monotone" dataKey={metric} name={METRICS[metric].label} stroke="#0a9e6e" strokeWidth={2.5}
          activeDot={{ r: 6, onClick: (props) => selectPoint(props?.payload) }} dot={{ r: drill.level === 'day' ? 2 : 3 }} connectNulls={false} />
      </LineChart></ResponsiveContainer>
    </div> : <div className="empty">Không có dữ liệu trong phạm vi này.</div>)}
    <p className="olap-hint">{drill.level === 'slot' ? 'Mỗi điểm là một khung 15 phút trong giờ đã chọn.' : 'Bấm một điểm trên đường biểu diễn để xem mức thời gian chi tiết hơn.'}</p>
  </section>
}

function Heatmap({ rows, title = 'Nhịp giao thông theo tuần', selectedMetric }) {
  const [localMetric, setLocalMetric] = useState('avg_occupancy_pct')
  const metric = selectedMetric ?? localMetric
  const [showValues, setShowValues] = useState(false)
  const heatMap = new Map(rows.map((row) => [row.group_key + '-' + row.split_key, row]))
  const max = Math.max(1, ...rows.map((row) => metricValue(row, metric) || 0))

  return <section className="panel olap-analysis-panel">
    <div className="olap-section-head"><div><div className="olap-section-label">Thứ trong tuần × Giờ</div><h3>{title}</h3></div>
      <div className="olap-heat-controls">{selectedMetric == null && <MetricButtons value={metric} onChange={setLocalMetric} />}
        <button type="button" className="olap-value-toggle" aria-pressed={showValues} onClick={() => setShowValues((current) => !current)}>{showValues ? 'Ẩn giá trị' : 'Hiện giá trị'}</button></div></div>
    <p className="olap-small olap-heat-description">{METRICS[metric].label} ({METRICS[metric].unit.trim()}) theo ngày trong tuần và khoảng giờ. Rê chuột vào ô để xem số liệu.</p>
    <div className="olap-heat-scroll"><div className={'olap-heat-grid' + (showValues ? ' show-values' : '')}>
      <div className="olap-heat-corner">Ngày trong tuần</div>
      {Array.from({ length: 24 }, (_, hour) => <div className="olap-heat-hour" key={hour} title={String(hour).padStart(2, '0') + ':00–' + String(hour).padStart(2, '0') + ':59'}>{hour}</div>)}
      {WEEKDAYS.map((day, index) => <div className="olap-heat-row" key={day}><div className="olap-heat-day">{day}</div>
        {Array.from({ length: 24 }, (_, hour) => {
          const row = heatMap.get((index + 1) + '-' + hour)
          const value = metricValue(row, metric)
          const strength = value == null ? 0 : value / max
          return <div key={hour} className="olap-heat-cell"
            style={{ background: value == null ? '#edf0ed' : 'rgba(10, 158, 110, ' + (0.12 + 0.82 * strength) + ')', color: strength > 0.6 ? '#fff' : '#173b2d' }}
            title={day + ', ' + String(hour).padStart(2, '0') + ':00–' + String(hour).padStart(2, '0') + ':59 · ' + fmtValue(value, METRICS[metric].unit)}>
            {showValues && value != null ? fmtValue(value) : null}
          </div>
        })}</div>)}
    </div></div>
    <div className="olap-heat-legend"><span className="olap-heat-gradient" />Màu càng đậm, giá trị càng cao<span className="olap-heat-missing" />Xám: không có dữ liệu</div>
  </section>
}

function DetectorFocus({ detector }) {
  const map = useMap()
  useEffect(() => {
    if (detector?.lat != null && detector?.long != null) map.flyTo([detector.lat, detector.long], Math.max(map.getZoom(), 15), { duration: 0.5 })
  }, [map, detector?.detid, detector?.lat, detector?.long])
  return null
}

function DetectorFit({ detectors, selected }) {
  const map = useMap()
  const ids = detectors.map((detector) => detector.detid).join('|')
  useEffect(() => {
    if (!selected && detectors.length) map.fitBounds(detectors.map((detector) => [detector.lat, detector.long]), { padding: [28, 28], maxZoom: 14 })
  }, [map, ids, selected])
  return null
}

function DetectorMap({ detectors, roadName, selected, onSelect }) {
  const [tileFailed, setTileFailed] = useState(false)
  const points = detectors.filter((detector) => Number.isFinite(detector.lat) && Number.isFinite(detector.long))
  const roadPoints = roadName ? points.filter((detector) => detector.road === roadName) : points
  const markerRank = (detector) => detector.detid === selected ? 2 : !roadName || detector.road === roadName ? 1 : 0
  const orderedPoints = [...points].sort((a, b) => markerRank(a) - markerRank(b))
  const selectedPoint = points.find((detector) => detector.detid === selected)
  const center = points.length ? [
    points.reduce((total, detector) => total + detector.lat, 0) / points.length,
    points.reduce((total, detector) => total + detector.long, 0) / points.length,
  ] : [47.0505, 8.3063]

  return <div className="olap-map">
    <MapContainer center={center} zoom={13} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
      <TileLayer maxZoom={19} opacity={0.8} attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        eventHandlers={{ tileerror: () => setTileFailed(true), tileload: () => setTileFailed(false) }} />
      <DetectorFit detectors={roadPoints.length ? roadPoints : points} selected={selected} />
      <DetectorFocus detector={selectedPoint} />
      {orderedPoints.map((detector) => <CircleMarker key={detector.detid} center={[detector.lat, detector.long]}
        radius={detector.detid === selected ? 9 : roadName && detector.road === roadName ? 7 : 5}
        pathOptions={{ color: '#fff', weight: 2, fillColor: detector.detid === selected ? '#e99728' : !roadName || detector.road === roadName ? '#0a9e6e' : '#697d75', fillOpacity: detector.detid === selected || !roadName || detector.road === roadName ? 0.95 : 0.55 }}
        eventHandlers={{ click: () => onSelect(detector.detid) }}>
        <MapTooltip direction="top"><b>{detector.detid}</b><br />{detector.road || 'Chưa có tên đường'}</MapTooltip>
      </CircleMarker>)}
    </MapContainer>
    <div className="olap-map-count">{tileFailed ? 'Nền đường phố chưa tải · ' : ''}{roadName ? roadPoints.length + ' cảm biến trên ' + roadName + ' · ' : ''}{points.length} cảm biến có tọa độ</div>
  </div>
}

function DetectorDetails({ detector, stats, scope }) {
  const [heat, setHeat] = useState(null)
  const [heatError, setHeatError] = useState('')
  const [metric, setMetric] = useState('avg_occupancy_pct')
  const [otherRoadStats, setOtherRoadStats] = useState(null)
  useEffect(() => {
    if (stats) { setOtherRoadStats(null); return }
    let active = true
    setOtherRoadStats(null)
    api.olapQuery({ start: scope.start, end: scope.end, detid: detector.detid, group_by: 'detector' })
      .then((value) => { if (active) setOtherRoadStats(value.rows[0] || null) })
      .catch(() => { if (active) setOtherRoadStats(null) })
    return () => { active = false }
  }, [detector.detid, scope.start, scope.end, stats])
  useEffect(() => {
    if (!detector) return
    let active = true
    setHeat(null)
    setHeatError('')
    api.olapQuery({ start: scope.start, end: scope.end, detid: detector.detid, group_by: 'day_of_week', split_by: 'hour' })
      .then((value) => { if (active) setHeat(value) })
      .catch((err) => { if (active) setHeatError(err.message) })
    return () => { active = false }
  }, [detector?.detid, scope.start, scope.end])
  if (!detector) return null
  const location = detector.lat == null || detector.long == null
    ? 'Chưa có tọa độ'
    : Number(detector.lat).toFixed(5) + ', ' + Number(detector.long).toFixed(5)
  const detectorStats = stats || otherRoadStats

  return <>
    <aside className="olap-detector-info" aria-label={'Thông tin cảm biến ' + detector.detid}>
      <div className="olap-section-head"><div><div className="olap-section-label">Cảm biến đã chọn</div><h3>{detector.detid}</h3></div></div>
      <p className="olap-small">{detector.road || 'Chưa rõ đường'} · {fmt.date(scope.start)}–{fmt.date(scope.end)}</p>
      <div className="olap-detector-metrics">
        <div><small>Occupancy TB</small><b>{fmtValue(detectorStats?.avg_occupancy_pct, '%')}</b></div>
        <div><small>Flow TB</small><b>{fmtValue(detectorStats?.avg_flow)}</b><small>xe/giờ/làn</small></div>
      </div>
      <div className="olap-detail-grid">
        <div><small>Đường</small><b>{detector.road || 'Chưa rõ'}</b></div>
        <div><small>Nhóm đường</small><b>{detector.road_group || '—'}</b></div>
        <div><small>Loại đường</small><b>{detector.fclass || '—'}</b></div>
        <div><small>Số làn</small><b>{detector.lanes ?? '—'}</b></div>
        <div><small>Giới hạn tốc độ</small><b>{fmtValue(detector.speed_limit_kmh, ' km/h')}</b></div>
        <div><small>Tọa độ</small><b>{location}</b></div>
      </div>
      <div className="olap-detector-quality"><div className="eyebrow">Chất lượng dữ liệu</div>
        <div className="olap-quality-pair">
          <div title="Số khung 15 phút hợp lệ / số khung có dữ liệu của cảm biến trong khoảng ngày đang xem"><small>Khung hợp lệ</small><b>{fmtValue(detectorStats?.valid_coverage_pct, '%')}</b></div>
          <div title="Số khoảng đo gắn lỗi / tổng số khoảng đo của cảm biến trong khoảng ngày đang xem"><small>Tỷ lệ khoảng đo lỗi</small><b>{fmtValue(detectorStats?.error_pct, '%')}</b></div>
        </div>
      </div>
    </aside>
    <div className="olap-detector-analysis">
      <div className="olap-overview-toolbar"><span>Chỉ số cho hai biểu đồ cảm biến</span><MetricButtons value={metric} onChange={setMetric} /></div>
      <TimeDrill scope={{ start: scope.start, end: scope.end, detid: detector.detid }} title="Thống kê cảm biến theo thời gian" selectedMetric={metric} />
      {heatError && <div className="warn" role="alert">{heatError}</div>}
      {heat ? <Heatmap rows={heat.rows} title="Nhịp giao thông của cảm biến" selectedMetric={metric} /> : !heatError && <p className="olap-small">Đang tải heatmap cảm biến…</p>}
    </div>
  </>
}

function DetectorPicker({ detectors, selected, onToggle }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef(null)
  const searchRef = useRef(null)
  const selectedDetector = detectors.find((detector) => detector.detid === selected)
  const visible = detectors.filter((detector) => (detector.detid + ' ' + (detector.road || '')).toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')))
    .sort((a, b) => (a.detid === selected ? -1 : b.detid === selected ? 1 : a.detid.localeCompare(b.detid, 'vi')))

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    const closeOutside = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false) }
    const closeEscape = (event) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeEscape)
    }
  }, [open])

  function toggle(detid) {
    onToggle(detid)
    setOpen(false)
    setQuery('')
  }

  return <div className="olap-detector-picker" ref={rootRef}>
    <span className="olap-picker-label">Cảm biến</span>
    <button type="button" className="olap-picker-trigger" aria-expanded={open} aria-controls="olap-detector-list"
      onClick={() => { setQuery(''); setOpen((current) => !current) }}>
      <span>{selectedDetector ? selectedDetector.detid : 'Chọn cảm biến'}</span><span aria-hidden="true">⌄</span>
    </button>
    {open && <div className="olap-picker-popup" id="olap-detector-list">
      <input ref={searchRef} type="search" aria-label="Tìm cảm biến" placeholder="Tìm mã hoặc tên đường…" value={query} onChange={(event) => setQuery(event.target.value)} />
      <p>Chọn lại cảm biến đang bật để bỏ chọn.</p>
      <div className="olap-picker-list">
        {visible.map((detector) => <button type="button" key={detector.detid} className={'olap-picker-item' + (selected === detector.detid ? ' selected' : '')}
          aria-pressed={selected === detector.detid} onClick={() => toggle(detector.detid)}>
          <span><b>{detector.detid}</b><small>{detector.road || 'Chưa rõ đường'}</small></span><span aria-hidden="true">{selected === detector.detid ? '✓' : ''}</span>
        </button>)}
        {!visible.length && <div className="olap-picker-empty">Không tìm thấy cảm biến.</div>}
      </div>
    </div>}
  </div>
}

const QUERY_GROUPS = [
  ['day_of_week', 'Ngày trong tuần'], ['daypart', 'Khoảng thời gian trong ngày'],
  ['road_name', 'Đường'], ['road_group', 'Nhóm đường'],
  ['road_class', 'Loại đường'], ['detector', 'Cảm biến'],
]
const ROAD_GROUP_KEYS = new Set(['road_name', 'road_group', 'road_class'])

function QueryTable({ scope, selected, onSelect }) {
  const [groupBy, setGroupBy] = useState('day_of_week')
  const [sort, setSort] = useState({ key: null, direction: 'asc' })
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const availableGroups = scope.road_name ? QUERY_GROUPS.filter(([key]) => !ROAD_GROUP_KEYS.has(key)) : QUERY_GROUPS
  const activeGroupBy = scope.road_name && ROAD_GROUP_KEYS.has(groupBy) ? 'day_of_week' : groupBy

  useEffect(() => {
    if (activeGroupBy !== groupBy) setGroupBy(activeGroupBy)
  }, [activeGroupBy, groupBy])

  useEffect(() => {
    if (!validRange(scope)) { setResult(null); return }
    let active = true
    setLoading(true)
    setError('')
    setResult(null)
    api.olapQuery({ ...scope, group_by: activeGroupBy }).then((value) => { if (active) setResult(value) })
      .catch((err) => { if (active) { setResult(null); setError(err.message) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [scope.start, scope.end, scope.road_name, activeGroupBy])

  const rows = useMemo(() => {
    const source = result?.rows || []
    if (!sort.key) return source
    const collator = new Intl.Collator('vi', { numeric: true, sensitivity: 'base' })
    return [...source].sort((left, right) => {
      const a = sort.key === 'group_label' && !['day_of_week', 'daypart'].includes(activeGroupBy) ? left.group_label : sort.key === 'group_label' ? left.group_key : left[sort.key]
      const b = sort.key === 'group_label' && !['day_of_week', 'daypart'].includes(activeGroupBy) ? right.group_label : sort.key === 'group_label' ? right.group_key : right[sort.key]
      if (a == null && b == null) return collator.compare(String(left.group_key), String(right.group_key))
      if (a == null) return 1
      if (b == null) return -1
      const order = sort.key === 'group_label'
        ? collator.compare(String(a), String(b))
        : Number(a) - Number(b)
      return (sort.direction === 'asc' ? order : -order) || collator.compare(String(left.group_key), String(right.group_key))
    })
  }, [result, sort, activeGroupBy])
  function toggleSort(key) {
    setSort((current) => ({ key, direction: current.key === key && current.direction === 'desc' ? 'asc' : current.key === key ? 'desc' : key === 'group_label' ? 'asc' : 'desc' }))
  }
  function sortHeader(key, label, numeric = false, hint = '') {
    const direction = sort.key === key ? sort.direction : null
    return <th className={numeric ? 'num' : ''} aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'} title={hint || undefined}>
      <button type="button" className={'olap-sort-button' + (direction ? ' active' : '')} onClick={() => toggleSort(key)}
        aria-label={'Sắp xếp ' + label + (direction ? (direction === 'asc' ? ' giảm dần' : ' tăng dần') : key === 'group_label' ? ' tăng dần' : ' giảm dần')}>
        {label}<span aria-hidden="true">{direction === 'asc' ? ' ↑' : direction === 'desc' ? ' ↓' : ' ↕'}</span>
      </button>
    </th>
  }

  return <section className="panel olap-analysis-panel olap-query-panel">
    <div className="olap-section-head"><div><div className="olap-section-label">Tổng hợp theo chiều phân tích</div><h3>Bảng phân tích đa chiều</h3></div>
      <label className="olap-group-select">Nhóm theo<select value={activeGroupBy} onChange={(event) => setGroupBy(event.target.value)}>
        {availableGroups.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
    <p className="olap-small">Áp dụng bộ lọc hiện tại: {fmt.date(scope.start)}–{fmt.date(scope.end)} · {scope.road_name || 'Tất cả đường'}. Bấm tiêu đề cột để sắp xếp.</p>
    {error && <div className="warn" role="alert">{error}</div>}
    {loading && <p className="olap-small">Đang tính bảng phân tích…</p>}
    {result && <div className="scroll olap-query-scroll"><table className="table"><thead><tr>
      {sortHeader('group_label', 'Nhóm')}
      {sortHeader('avg_occupancy_pct', 'Occupancy TB (%)', true)}
      {sortHeader('avg_flow', 'Flow TB (xe/giờ/làn)', true)}
      {sortHeader('valid_coverage_pct', 'Khung hợp lệ (%)', true, 'Số khung 15 phút hợp lệ / số khung có dữ liệu')}
      {sortHeader('error_pct', 'Tỷ lệ lỗi (%)', true, 'Số khoảng đo gắn lỗi / tổng số khoảng đo')}
    </tr></thead><tbody>{rows.map((row) => <tr key={row.group_key} className={activeGroupBy === 'detector' && selected === row.group_key ? 'olap-selected-row' : ''}>
      <td>{activeGroupBy === 'detector' ? <button type="button" className="olap-table-select" onClick={() => onSelect(row.group_key)}>{row.group_label}</button> : row.group_label}</td>
      <td className="num">{fmtValue(row.avg_occupancy_pct, '%')}</td><td className="num">{fmtValue(row.avg_flow)}</td>
      <td className="num">{fmtValue(row.valid_coverage_pct, '%')}</td><td className="num">{fmtValue(row.error_pct, '%')}</td>
    </tr>)}</tbody></table>{!rows.length && <div className="empty">Không có dữ liệu trong phạm vi này.</div>}</div>}
  </section>
}

function DataQuality({ summary, registeredCount }) {
  return <details className="panel olap-analysis-panel olap-data-quality">
    <summary><b>Chất lượng dữ liệu</b><span>Xem tỷ lệ lỗi, độ phủ và số mẫu sạch</span></summary>
    <div className="olap-quality-grid">
      <div><small>Khung 15 phút hợp lệ</small><b>{fmtValue(summary.valid_coverage_pct, '%')}</b><span>{fmt.int(summary.valid_windows)} / {fmt.int(summary.observed_windows)} khung có dữ liệu</span></div>
      <div><small>Tỷ lệ khoảng đo lỗi</small><b>{fmtValue(summary.error_pct, '%')}</b><span>Số khoảng đo gắn lỗi / tổng số khoảng đo</span></div>
      <div><small>Mẫu Occupancy sạch</small><b>{fmt.int(summary.clean_occ_samples)}</b></div>
      <div><small>Mẫu Flow sạch</small><b>{fmt.int(summary.clean_flow_samples)}</b></div>
      <div title="Số cảm biến có ít nhất một khung dữ liệu / tổng số cảm biến hiện hành thuộc đường đang chọn"><small>Cảm biến có bản ghi</small><b>{summary.detectors == null ? '—' : fmt.int(summary.detectors) + ' / ' + fmt.int(registeredCount)}</b><span>Trong khoảng ngày đang xem</span></div>
    </div>
    <p className="olap-small">Các chỉ số giao thông chỉ tổng hợp từ khung 15 phút đạt quy tắc hợp lệ của kho dữ liệu.</p>
  </details>
}

export default function OLAP() {
  const [options, setOptions] = useState(null)
  const [scope, setScope] = useState({ start: '', end: '', road_name: '' })
  const [overviewMetric, setOverviewMetric] = useState('avg_occupancy_pct')
  const [selected, setSelected] = useState('')
  const [heat, setHeat] = useState(null)
  const [detectorRows, setDetectorRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const detectorSectionRef = useRef(null)

  useEffect(() => {
    api.olapOptions().then((value) => {
      setOptions(value)
      setScope({ start: value.start || '', end: value.end || '', road_name: '' })
    }).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    if (!options || !validRange(scope)) return
    let active = true
    setLoading(true)
    setError('')
    setHeat(null)
    setDetectorRows([])
    Promise.all([
      api.olapQuery({ ...scope, group_by: 'day_of_week', split_by: 'hour' }),
      api.olapQuery({ ...scope, group_by: 'detector' }),
    ]).then(([heatResult, detectorsResult]) => {
      if (active) { setHeat(heatResult); setDetectorRows(detectorsResult.rows) }
    }).catch((err) => { if (active) { setHeat(null); setDetectorRows([]); setError(err.message) } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [options, scope])

  const detectorById = useMemo(() => new Map((options?.detectors || []).map((detector) => [detector.detid, detector])), [options])
  const detectors = options?.detectors || []
  const selectedDetector = detectorById.get(selected)
  const selectedStats = detectorRows.find((row) => row.group_key === selected)
  const summary = heat?.summary || {}
  const registeredCount = detectors.filter((detector) => !scope.road_name || detector.road === scope.road_name).length

  if (!options) return <div className="panel panel-b"><div className="panel-title">{error ? 'Chưa đọc được kho dữ liệu' : 'Đang tải OLAP…'}</div>{error && <p>{error}</p>}</div>
  function updateScope(key, value) {
    setScope((current) => ({ ...current, [key]: value }))
    if (key === 'road_name') setSelected('')
  }
  function selectFromAnalysis(detid) {
    setSelected((current) => current === detid ? '' : detid)
    if (selected !== detid) requestAnimationFrame(() => detectorSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  return <div className="olap">
    <div className="olap-top-row"><section className="panel olap-filter-panel"><div className="olap-primary-filters">
      <label>Từ ngày<input type="date" min={options.start} max={options.end} value={scope.start} onChange={(event) => updateScope('start', event.target.value)} /></label>
      <label>Đến ngày<input type="date" min={options.start} max={options.end} value={scope.end} onChange={(event) => updateScope('end', event.target.value)} /></label>
      <label>Đường<select value={scope.road_name} onChange={(event) => updateScope('road_name', event.target.value)}>
        <option value="">Tất cả đường</option>{options.roads.map((road) => <option key={road} value={road}>{road}</option>)}</select></label>
    </div><div className="olap-context"><b>Đang xem:</b> {fmt.date(scope.start)}–{fmt.date(scope.end)} · {scope.road_name || 'Tất cả đường'}
      {loading && <span className="olap-loading">Đang tính…</span>}</div></section>
    {validRange(scope) && <div className="olap-summary-groups">
      <div className="olap-summary-group"><div className="olap-section-label">Traffic Measures · Chỉ số giao thông</div><div className="olap-summary-metrics">
        <div className="stat"><div className="eyebrow">Occupancy trung bình</div><div className="v">{fmtValue(summary.avg_occupancy_pct, '%')}</div></div>
        <div className="stat"><div className="eyebrow">Flow trung bình</div><div className="v">{fmtValue(summary.avg_flow)}</div><div className="c">xe/giờ/làn</div></div>
      </div></div>
      <div className="olap-summary-group"><div className="olap-section-label">Data Reliability · Độ tin cậy dữ liệu</div><div className="olap-summary-metrics">
        <div className="stat" title="Số cảm biến có ít nhất một khung 15 phút hợp lệ trong khoảng ngày đang xem / tất cả cảm biến hiện hành thuộc đường đang chọn, kể cả cảm biến không có bản ghi"><div className="eyebrow">Cảm biến có dữ liệu hợp lệ</div><div className="v">{summary.valid_detectors == null ? '—' : fmt.int(summary.valid_detectors) + ' / ' + fmt.int(registeredCount)}</div></div>
        <div className="stat" title="Số khung 15 phút hợp lệ / số khung 15 phút có dữ liệu trong phạm vi đang xem; khung hợp lệ dùng cùng quy tắc với kho dữ liệu"><div className="eyebrow">Độ phủ dữ liệu hợp lệ</div><div className="v">{fmtValue(summary.valid_coverage_pct, '%')}</div><div className="c">Trên các khung có dữ liệu</div></div>
      </div></div>
    </div>}</div>
    {!validRange(scope) && <div className="warn" role="alert">Hãy chọn ngày bắt đầu không sau ngày kết thúc.</div>}
    {error && <div className="warn" role="alert">{error}</div>}

    {validRange(scope) && <>
      <div className="olap-overview-toolbar"><span>Chỉ số cho hai biểu đồ</span><MetricButtons value={overviewMetric} onChange={setOverviewMetric} /></div>
      <div className="olap-overview-charts">
        <TimeDrill key={scope.start + ':' + scope.end + ':' + scope.road_name} scope={scope} selectedMetric={overviewMetric} />
        <Heatmap rows={heat?.rows || []} selectedMetric={overviewMetric} />
      </div>
      <section ref={detectorSectionRef} className="panel olap-analysis-panel"><div className="olap-section-head"><div><div className="olap-section-label">Vị trí cảm biến</div><h3>Chọn cảm biến trên bản đồ</h3></div>
        <DetectorPicker detectors={detectors} selected={selected} onToggle={(detid) => setSelected((current) => current === detid ? '' : detid)} /></div>
        <p className="olap-small">Chọn một điểm hoặc mã cảm biến để xem thông tin ngay cạnh bản đồ.</p>
        <div className="olap-detector-layout">
          <DetectorMap detectors={detectors} roadName={scope.road_name} selected={selected} onSelect={(detid) => setSelected((current) => current === detid ? '' : detid)} />
          {selectedDetector ? <DetectorDetails key={selected + ':' + scope.start + ':' + scope.end} detector={selectedDetector} stats={selectedStats} scope={scope} />
            : <div className="olap-detector-placeholder">Chọn cảm biến trên bản đồ để xem thông tin, biểu đồ thời gian và heatmap.</div>}
        </div>
      </section>
      <QueryTable scope={scope} selected={selected} onSelect={selectFromAnalysis} />
      <DataQuality summary={summary} registeredCount={registeredCount} />
    </>}
  </div>
}
