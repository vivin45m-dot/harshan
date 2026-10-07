import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi } from '../api.js'
import StatusPill, { STATUS_HELP } from '../components/StatusPill.jsx'
import { fdaDate, fix, kg, monthLabel, pct } from '../format.js'
import { ErrorNote } from './Overview.jsx'

const RANGES = { '3y': 36, '6y': 72, all: 9999 }

export default function NodeDetail() {
  const { id } = useParams()
  const { data, error } = useApi(`/nodes/${encodeURIComponent(id)}`, [id])
  const [range, setRange] = useState('6y')
  const [scope, setScope] = useState('origin')

  const series = useMemo(() => {
    if (!data) return []
    return data.history.slice(-RANGES[range]).map(h => ({
      ...h,
      band95: [h.lo95_kg, h.hi95_kg],
      band80: [h.lo80_kg, h.hi80_kg],
    }))
  }, [data, range])

  if (error) return <ErrorNote error={error} />
  if (!data) return <p className="empty">Loading…</p>

  const first = series[0]?.period
  const recallLines = data.recalls
    .filter(r => r.initiated >= first && (scope === 'all' || r.names_this_origin))
  const recallMonths = [...new Set(recallLines.map(r => r.initiated))]
  const testStart = data.history.find(h => h.split === 'test')?.period
  const nx = data.next
  const v = data.verification

  return (
    <>
      <div className="page-head">
        <div>
          <p className="note"><Link to="/">Supply map</Link> / node</p>
          <h1>{data.label} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>from {data.country}</span></h1>
          <p>
            HS {data.hs_codes.join(', ')} · {pct(data.share, 1)} of US imports of this commodity ·{' '}
            {data.perishable ? 'perishable' : 'shelf-stable'}
          </p>
        </div>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <div className="label">Forecast · {monthLabel(nx.period)}</div>
          <div className="value">{kg(nx.forecast_kg)}</div>
          <div className="sub">80% range {kg(nx.lo80_kg)} – {kg(nx.hi80_kg)}</div>
        </div>
        <div className="card stat">
          <div className="label">Reliability</div>
          <div className="value" style={{ fontSize: '1.2rem', marginTop: 8 }}><StatusPill status={nx.status} /></div>
          <div className="sub" style={{ marginTop: 6 }}>{STATUS_HELP[nx.status]}</div>
        </div>
        <div className="card stat">
          <div className="label">Uncertainty (model units)</div>
          <div className="value num" style={{ fontSize: '1.2rem', marginTop: 4 }}>
            {fix(nx.epistemic)} <span className="note">epistemic</span>
          </div>
          <div className="value num" style={{ fontSize: '1.2rem' }}>
            {fix(nx.aleatoric)} <span className="note">aleatoric</span>
          </div>
        </div>
        <div className="card stat">
          <div className="label">Traceability (verification ratio)</div>
          <div className="value">{pct(v.ratio)}</div>
          <div className="sub">
            {v.records
              ? `${v.verified_records} of ${v.records} pre-2022 recall records naming ${data.country} were complete`
              : `No recall naming ${data.country} before 2022; uses the ${data.label.toLowerCase()} rate`}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>Monthly imports and forecast</h2>
          <div className="controls">
            <div className="seg">
              {Object.keys(RANGES).map(r => (
                <button key={r} className={range === r ? 'on' : ''} onClick={() => setRange(r)}>{r}</button>
              ))}
            </div>
            <div className="seg" title="Which FDA recalls to mark on the chart">
              <button className={scope === 'origin' ? 'on' : ''} onClick={() => setScope('origin')}>Recalls naming {data.country}</button>
              <button className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>All {data.label.toLowerCase()} recalls</button>
            </div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="period" tickFormatter={monthLabel} minTickGap={40} stroke="var(--axis)"
              tick={{ fill: 'var(--muted)', fontSize: 12 }} />
            <YAxis tickFormatter={kg} width={70} stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 12 }} />
            {testStart && testStart >= first && (
              <ReferenceArea x1={testStart} x2={series.at(-1)?.period} fill="var(--surface-2)" fillOpacity={0.6}
                label={{ value: 'held-out test period', position: 'insideTopLeft', fill: 'var(--muted)', fontSize: 11 }} />
            )}
            {recallMonths.map(m => (
              <ReferenceLine key={m} x={m} stroke="var(--critical)" strokeDasharray="3 3" strokeOpacity={0.6} />
            ))}
            <Area dataKey="band95" stroke="none" fill="var(--band-95)" name="95% interval" isAnimationActive={false} />
            <Area dataKey="band80" stroke="none" fill="var(--band-80)" name="80% interval" isAnimationActive={false} />
            <Line dataKey="forecast_kg" stroke="var(--series-1)" strokeWidth={2} dot={false} name="Forecast" isAnimationActive={false} />
            <Line dataKey="actual_kg" stroke="var(--ink)" strokeWidth={1.5} dot={false} name="Actual imports" isAnimationActive={false} />
            <Tooltip content={<ForecastTip recalls={recallLines} />} />
            <Legend wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="note">Red dashed lines: month an FDA recall was <em>initiated</em>. The model never sees these dates; it only sees recalls after FDA publishes them.</p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>Model uncertainty over time</h2>
          <span>log scale · dashed line = "unreliable" threshold</span>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="period" tickFormatter={monthLabel} minTickGap={40} stroke="var(--axis)"
              tick={{ fill: 'var(--muted)', fontSize: 12 }} />
            <YAxis width={70} scale="log" domain={['auto', 'auto']} allowDataOverflow stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 12 }} tickFormatter={v => v.toFixed(2)} />
            {recallMonths.map(m => (
              <ReferenceLine key={m} x={m} stroke="var(--critical)" strokeDasharray="3 3" strokeOpacity={0.5} />
            ))}
            <ReferenceLine y={data.thresholds.epistemic} stroke="var(--series-2)" strokeDasharray="6 4" />
            <Line dataKey="epistemic" stroke="var(--series-2)" strokeWidth={2} dot={false} name="Epistemic (model doesn't know)" isAnimationActive={false} />
            <Line dataKey="aleatoric" stroke="var(--series-3)" strokeWidth={2} dot={false} name="Aleatoric (demand is noisy)" isAnimationActive={false} />
            <Tooltip content={<UncTip />} />
            <Legend wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>FDA recalls for {data.label.toLowerCase()}</h2>
          <span>{data.recall_count} total · newest first</span>
        </div>
        <div className="table-wrap" style={{ maxHeight: 460, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr><th>Recall</th><th>Initiated</th><th>Firm / product</th><th>Traceability checks</th></tr>
            </thead>
            <tbody>
              {data.recalls.map(r => (
                <tr key={r.recall_number}>
                  <td className="mono">
                    <Link to={`/ledger?ref=${encodeURIComponent(r.recall_number)}`}>{r.recall_number}</Link>
                    <div className="note">{r.classification}</div>
                    {r.names_this_origin && <div className="note" style={{ color: 'var(--critical-ink)' }}>names {data.country}</div>}
                  </td>
                  <td className="num" style={{ whiteSpace: 'nowrap' }}>{fdaDate(r.recall_initiation_date)}</td>
                  <td style={{ maxWidth: 460 }}>
                    <b style={{ fontWeight: 600 }}>{r.recalling_firm}</b>
                    <div style={{ color: 'var(--ink-2)' }}>{truncate(r.product_description, 160)}</div>
                    <div className="note">{truncate(r.reason_for_recall, 140)}</div>
                  </td>
                  <td style={{ minWidth: 200 }}>
                    <Checks r={r} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

export function Checks({ r }) {
  const items = [['lot', r.chk_lot], ['date', r.chk_date], ['quantity', r.chk_quantity],
    ['distribution', r.chk_distribution], ['origin', r.chk_origin]]
  return (
    <div>
      {items.map(([k, ok]) => (
        <span key={k} className={`check ${ok ? 'yes' : 'no'}`}>{ok ? '✓' : '✗'} {k}</span>
      ))}
      <div style={{ marginTop: 4 }}>
        {r.verified ? <span className="pill reliable"><i />Verified</span> : <span className="pill"><i style={{ background: 'var(--muted)' }} />Incomplete</span>}
      </div>
    </div>
  )
}

function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

function ForecastTip({ active, payload, label, recalls }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const here = recalls.filter(r => r.initiated === label)
  return (
    <div className="tip">
      <b>{monthLabel(label)} <span className="note">({d.split})</span></b>
      <div className="row"><span>Actual</span><span>{kg(d.actual_kg)}</span></div>
      <div className="row"><span>Forecast</span><span>{kg(d.forecast_kg)}</span></div>
      <div className="row"><span>80% range</span><span>{kg(d.lo80_kg)} – {kg(d.hi80_kg)}</span></div>
      <div className="row"><span>Status</span><span>{d.status}</span></div>
      {here.length > 0 && <div className="row"><span>Recalls initiated</span><span>{here.length}</span></div>}
    </div>
  )
}

function UncTip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="tip">
      <b>{monthLabel(label)}</b>
      <div className="row"><span>Epistemic</span><span>{fix(d.epistemic)}</span></div>
      <div className="row"><span>Aleatoric</span><span>{fix(d.aleatoric)}</span></div>
    </div>
  )
}
