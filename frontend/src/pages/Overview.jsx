import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../api.js'
import SupplyMap from '../components/SupplyMap.jsx'
import StatusPill, { STATUS_HELP } from '../components/StatusPill.jsx'
import { kg, monthLabel, pct } from '../format.js'
import { useThemeName } from '../theme.js'

const ORDER = { unreliable: 0, volatile: 1, reliable: 2 }

export default function Overview() {
  const theme = useThemeName()
  const navigate = useNavigate()
  const overview = useApi('/overview')
  const months = useApi('/months')
  const [month, setMonth] = useState(null)
  const active = month || overview.data?.last_month
  const snap = useApi(active ? `/nodes?month=${active}` : null, [active])
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)

  const nodes = snap.data?.nodes ?? []
  const shown = useMemo(() => nodes
    .filter(n => filter === 'all' || n.status === filter)
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.epistemic - a.epistemic), [nodes, filter])

  if (overview.error) return <ErrorNote error={overview.error} />
  const o = overview.data
  const counts = nodes.reduce((m, n) => ({ ...m, [n.status]: (m[n.status] || 0) + 1 }), {})
  const monthList = months.data ?? []
  const idx = monthList.indexOf(active)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Where can the forecast be trusted?</h1>
          <p>
            Each dot is a supply node: one food commodity shipped to the US from one origin country.
            Colour shows how much the model trusts its own forecast for the selected month.
          </p>
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat label="Supply nodes" value={o?.nodes} sub={o && `${o.commodities} commodities · ${o.countries} countries`} />
        <Stat label="Months of real import data" value={o && monthDiff(o.first_month, o.last_month)}
          sub={o && `${monthLabel(o.first_month)} – ${monthLabel(o.last_month)}`} />
        <Stat label="FDA recalls matched" value={o?.recalls?.toLocaleString()}
          sub={o && `${pct(o.recalls_verified_share)} pass all traceability checks`} />
        <Stat label="CDC outbreaks matched" value={o?.outbreaks?.toLocaleString()}
          sub={o && `${o.ledger.blocks} ledger blocks`} />
      </div>

      <div className="split">
        <div className="card">
          <div className="card-head">
            <h2>Supply map · {monthLabel(active)}</h2>
            <span>dot size = import volume</span>
          </div>
          <div className="controls" style={{ marginBottom: 10 }}>
            <input type="range" min={0} max={Math.max(monthList.length - 1, 0)} value={Math.max(idx, 0)}
              onChange={e => setMonth(monthList[+e.target.value])} style={{ flex: 1 }}
              aria-label="Month" />
            <span className="num note" style={{ width: 70 }}>{monthLabel(active)}</span>
          </div>
          {snap.data ? (
            <SupplyMap nodes={nodes} selected={selected} theme={theme}
              onSelect={id => (selected === id ? navigate(`/node/${encodeURIComponent(id)}`) : setSelected(id))} />
          ) : <div className="map empty">Loading map…</div>}
          <div className="legend">
            {['reliable', 'volatile', 'unreliable'].map(s => (
              <span key={s} title={STATUS_HELP[s]}><StatusPill status={s} /> {counts[s] || 0}</span>
            ))}
            <span className="note">Click a dot to select it, click again to open it.</span>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Nodes</h2>
            <div className="seg">
              {['all', 'unreliable', 'volatile', 'reliable'].map(f => (
                <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>
                  {f === 'all' ? 'All' : f[0].toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 590, overflowY: 'auto' }}>
            <table>
              <thead>
                <tr><th>Node</th><th className="r">Forecast</th><th>Status</th></tr>
              </thead>
              <tbody>
                {shown.map(n => (
                  <tr key={n.node_id} className="clickable"
                    style={selected === n.node_id ? { background: 'var(--surface-2)' } : null}
                    onMouseEnter={() => setSelected(n.node_id)}
                    onClick={() => navigate(`/node/${encodeURIComponent(n.node_id)}`)}>
                    <td>
                      <Link to={`/node/${encodeURIComponent(n.node_id)}`}>{n.label}</Link>
                      <div className="note">{n.country}</div>
                    </td>
                    <td className="r num">{kg(n.forecast_kg)}</td>
                    <td><StatusPill status={n.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!shown.length && <p className="empty">No nodes in this group for {monthLabel(active)}.</p>}
          </div>
        </div>
      </div>

      <div className="grid cols-3" style={{ marginTop: 16 }}>
        {['reliable', 'volatile', 'unreliable'].map(s => (
          <div key={s} className="card">
            <StatusPill status={s} />
            <p style={{ marginTop: 8, color: 'var(--ink-2)', fontSize: '0.88rem' }}>{STATUS_HELP[s]}</p>
          </div>
        ))}
      </div>
    </>
  )
}

function monthDiff(a, b) {
  const [ya, ma] = a.split('-').map(Number)
  const [yb, mb] = b.split('-').map(Number)
  return (yb - ya) * 12 + (mb - ma) + 1
}

function Stat({ label, value, sub }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value ?? '…'}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export function ErrorNote({ error }) {
  return (
    <div className="card">
      <h2>Can't reach the API</h2>
      <p style={{ marginTop: 6, color: 'var(--ink-2)' }}>
        {String(error.message || error)}. Start the backend with <code>run.ps1</code> (or{' '}
        <code>uvicorn foodtrace.api.main:app</code>) and reload.
      </p>
    </div>
  )
}
