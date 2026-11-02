import { useState } from 'react'
import { MapView, ReplayBar } from '../components/Widgets.jsx'

const COLORS = ['#0a9e6e', '#3b6fd8', '#c2410c', '#8b5cf6', '#64748b']

export default function MapPage(p) {
  const { rows, selected, setSelected, meta } = p
  const [by, setBy] = useState('level')
  const clusters = Object.keys(meta.clusters)
  return (
    <>
      <ReplayBar {...p} />
      <div className="panel">
        <div className="panel-h">
          <div><div className="eyebrow">Bản đồ · {rows.length} detector theo bộ lọc</div><div className="panel-title">{by === 'level' ? 'Tô màu theo mức ưu tiên' : 'Tô màu theo cụm hành vi (K-means)'}</div></div>
          <div className="row wrap">
            {by === 'cluster' && <div className="map-legend wrap">{clusters.map((c, i) => <span key={c}><i className="dot" style={{ background: COLORS[i] }} />{c} ({meta.clusters[c]})</span>)}</div>}
            <div className="seg" style={{ width: 280 }}>
              <button className={by === 'level' ? 'on' : ''} onClick={() => setBy('level')}>Mức ưu tiên</button>
              <button className={by === 'cluster' ? 'on' : ''} onClick={() => setBy('cluster')}>Cụm K-means</button>
            </div>
          </div>
        </div>
        <MapView rows={rows} selected={selected} onSelect={setSelected} colorBy={by} clusters={clusters} tall />
      </div>
    </>
  )
}
