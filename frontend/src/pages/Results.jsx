import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Legend } from 'recharts'
import { useApi } from '../api.js'
import { fix, kg, pct, pval } from '../format.js'
import { ErrorNote } from './Overview.jsx'

const MODEL_NAMES = {
  evidential: 'Evidential GRU (ours)',
  mc_dropout: 'MC-dropout GRU',
  gru_point: 'GRU, no uncertainty',
  arima: 'SARIMA',
  seasonal_naive: 'Seasonal naive',
  naive: 'Naive (last month)',
}

export default function Results() {
  const { data, error } = useApi('/results')
  if (error) return <ErrorNote error={error} />
  if (!data) return <p className="empty">Loading…</p>

  const acc = data.accuracy
  const cal = data.calibration
  const h1 = data.h1_verification
  const h2 = data.h2_lead
  const h3 = data.h3_perishability
  const mf = data.main_fold

  const calRows = cal.evidential.levels.map((l, i) => ({
    level: l.level,
    ideal: l.level,
    evidential: l.picp,
    mc_dropout: cal.mc_dropout.levels[i].picp,
    arima: cal.arima.levels[i].picp,
  }))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Evaluation</h1>
          <p>
            Trained on {fmtRange('2018-01', mf.train_end)} (each forecast also sees the 24 months before it), tuned on {fmtRange(next(mf.train_end), mf.val_end)},
            scored on the held-out months {fmtRange(next(mf.val_end), mf.test_end)}. Every number below is
            computed from real data by <code>foodtrace.model.evaluate</code>.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>1 · Forecast accuracy (test period)</h2>
          <span>MASE &lt; 1 beats the seasonal-naive forecast</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Model</th><th className="r">MASE</th><th className="r">MAE (log)</th>
                <th className="r">MAE</th><th className="r">RMSE</th><th className="r">WAPE</th><th className="r" title="months with at least 10% of the node's typical volume">MAPE*</th></tr>
            </thead>
            <tbody>
              {Object.entries(acc).sort((a, b) => a[1].mase - b[1].mase).map(([k, m]) => (
                <tr key={k} style={k === 'evidential' ? { fontWeight: 600 } : null}>
                  <td>{MODEL_NAMES[k]}</td>
                  <td className="r num">{fix(m.mase, 3)}</td>
                  <td className="r num">{fix(m.mae_log, 3)}</td>
                  <td className="r num">{kg(m.mae_kg)}</td>
                  <td className="r num">{kg(m.rmse_kg)}</td>
                  <td className="r num">{fix(m.wape_pct, 1)}%</td>
                  <td className="r num">{fix(m.mape_pct, 1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note" style={{ marginTop: 8 }}>* MAPE leaves out months where a node imported under 10% of its usual volume; on those months a percentage error is meaningless. WAPE (total error ÷ total volume) uses every month.</p>
        {data.seed_stability && (
          <p className="note" style={{ marginTop: 8 }}>
            Across {data.seed_stability.evidential.runs} training seeds, log-scale MAE varied by ±
            {fix(data.seed_stability.evidential.mae_log_sd, 3)} (evidential), ±{fix(data.seed_stability.mc_dropout.mae_log_sd, 3)} (MC-dropout),
            ±{fix(data.seed_stability.gru_point.mae_log_sd, 3)} (point GRU).
          </p>
        )}
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-head">
            <h2>2 · Calibration</h2>
            <span>closer to the diagonal is better</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={calRows} margin={{ top: 8, right: 16, bottom: 28, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis dataKey="level" type="number" domain={[0.4, 1]} tickFormatter={v => pct(v)} stroke="var(--axis)"
                tick={{ fill: 'var(--muted)', fontSize: 12 }} label={{ value: 'nominal interval', position: 'insideBottom', offset: -10, fill: 'var(--muted)', fontSize: 12 }} />
              <YAxis domain={[0.2, 1]} tickFormatter={v => pct(v)} stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 12 }} />
              <Line dataKey="ideal" stroke="var(--axis)" strokeDasharray="4 4" dot={false} name="Perfect calibration" isAnimationActive={false} />
              <Line dataKey="evidential" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4 }} name="Evidential" isAnimationActive={false} />
              <Line dataKey="mc_dropout" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 4 }} name="MC-dropout" isAnimationActive={false} />
              <Line dataKey="arima" stroke="var(--series-3)" strokeWidth={2} dot={{ r: 4 }} name="SARIMA" isAnimationActive={false} />
              <Tooltip formatter={v => pct(v, 1)} labelFormatter={v => `${pct(v)} interval`} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)' }} />
              <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12, paddingBottom: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <div className="card-head"><h2>Calibration table</h2><span>PICP = share of actuals inside the interval</span></div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Model</th><th className="r">NLL</th>
                  {cal.evidential.levels.map(l => <th key={l.level} className="r">PICP {pct(l.level)}</th>)}
                  <th className="r">Avg gap</th></tr>
              </thead>
              <tbody>
                {['evidential', 'mc_dropout', 'arima'].map(k => (
                  <tr key={k}>
                    <td>{MODEL_NAMES[k]}</td>
                    <td className="r num">{fix(cal[k].nll, 3)}</td>
                    {cal[k].levels.map(l => <td key={l.level} className="r num">{pct(l.picp, 1)}</td>)}
                    <td className="r num">{pct(cal[k].mean_coverage_gap, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note" style={{ marginTop: 8 }}>
            Interval width at 90% (log units): evidential {fix(cal.evidential.levels[2].width, 2)},
            MC-dropout {fix(cal.mc_dropout.levels[2].width, 2)}, SARIMA {fix(cal.arima.levels[2].width, 2)}.
            λ = {mf.lambda} was chosen on the validation year by calibration.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>3 · Does traceability go with lower epistemic uncertainty?</h2>
          <span>one dot per supply node, test-period mean</span>
        </div>
        <div className="grid cols-2">
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart margin={{ top: 8, right: 16, bottom: 18, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis dataKey="verification_ratio" type="number" tickFormatter={v => pct(v)} stroke="var(--axis)"
                tick={{ fill: 'var(--muted)', fontSize: 12 }} name="Verification ratio"
                label={{ value: 'verification ratio', position: 'insideBottom', offset: -10, fill: 'var(--muted)', fontSize: 12 }} />
              <YAxis dataKey="epistemic" type="number" scale="log" domain={['auto', 'auto']} stroke="var(--axis)"
                tick={{ fill: 'var(--muted)', fontSize: 12 }} tickFormatter={v => v.toFixed(2)} name="Epistemic" />
              <ZAxis range={[40, 40]} />
              <ReferenceLine x={h1.median_split} stroke="var(--axis)" strokeDasharray="4 4" />
              <Tooltip content={<NodeTip />} />
              <Scatter data={data.node_summary} isAnimationActive={false}>
                {data.node_summary.map(n => (
                  <Cell key={n.node_id} fill={n.verified_group === 'verified' ? 'var(--series-1)' : 'var(--series-2)'} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          <div>
            <div className="legend" style={{ marginTop: 0, marginBottom: 8 }}>
              <span><i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: 'var(--series-1)', marginRight: 6 }} />Verified (above median ratio)</span>
              <span><i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: 'var(--series-2)', marginRight: 6 }} />Unverified</span>
            </div>
            <table>
              <tbody>
                <tr><td>Verified group (above median ratio)</td><td className="r num">{h1.verified.n} nodes · median {fix(h1.verified.median_epistemic)}</td></tr>
                <tr><td>Unverified group</td><td className="r num">{h1.unverified.n} nodes · median {fix(h1.unverified.median_epistemic)}</td></tr>
                <tr><td>Mann–Whitney U (verified lower?)</td><td className="r num">{pval(h1.p_one_sided)} · r = {fix(h1.rank_biserial, 2)}</td></tr>
                <tr><td>Spearman ρ (ratio vs epistemic)</td><td className="r num">{fix(h1.spearman.rho, 2)} · {pval(h1.spearman.p)}</td></tr>
                <tr><td>Regression, controls for volatility, gaps, volume</td><td className="r num">β = {fix(h1.regression_controls.coef, 2)} · {pval(h1.regression_controls.p)}</td></tr>
                <tr><td>…plus commodity fixed effects</td><td className="r num">β = {fix(h1.regression_with_commodity_fe.coef, 2)} · {pval(h1.regression_with_commodity_fe.p)}</td></tr>
              </tbody>
            </table>
            <p className="callout" style={{ marginTop: 12 }}>{h1Verdict(h1)}</p>
            <PerishTable h3={h3} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>4 · Does uncertainty rise before a recall?</h2>
          <span>{LEAD_NOTE}</span>
        </div>
        <div className="grid cols-2">
          {['node', 'commodity'].map(scope => (
            <LeadPanel key={scope} scope={scope} r={h2[scope]} pairs={data.lead_pairs?.[scope]} />
          ))}
        </div>
      </div>
    </>
  )
}

const LEAD_NOTE = 'epistemic uncertainty in the 3 months before initiation vs the same node in quiet months'

function LeadPanel({ scope, r, pairs }) {
  const title = scope === 'node' ? 'Recalls that name the origin country' : 'Any recall of the commodity'
  if (!r || r.note) return <div><h3>{title}</h3><p className="note">{r?.note || 'Not available'} ({r?.n_events ?? 0} events)</p></div>
  const bars = [
    { name: 'Evidential', before: r.ev.median_pre, quiet: r.ev.median_quiet },
    { name: 'MC-dropout', before: r.mc.median_pre, quiet: r.mc.median_quiet },
  ]
  return (
    <div>
      <h3>{title}</h3>
      <p className="note">{r.n_events} events across {r.n_nodes} nodes · values relative to each node's median</p>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barGap={2}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="name" stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 12 }} />
          <YAxis stroke="var(--axis)" tick={{ fill: 'var(--muted)', fontSize: 12 }} tickFormatter={v => v.toFixed(2)} />
          <ReferenceLine y={1} stroke="var(--axis)" strokeDasharray="4 4" />
          <Bar dataKey="quiet" name="Quiet months" fill="var(--series-3)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="before" name="3 months before recall" fill="var(--series-2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Tooltip formatter={v => v.toFixed(3)} contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)' }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </BarChart>
      </ResponsiveContainer>
      <table>
        <tbody>
          <tr><td>Evidential: higher before recall in</td><td className="r num">{pct(r.ev.share_higher_before)} of events · Wilcoxon {pval(r.ev.wilcoxon_p_one_sided)}</td></tr>
          <tr><td>MC-dropout: higher before recall in</td><td className="r num">{pct(r.mc.share_higher_before)} of events · Wilcoxon {pval(r.mc.wilcoxon_p_one_sided)}</td></tr>
        </tbody>
      </table>
      {pairs && <p className="note" style={{ marginTop: 6 }}>{pairs.length} event windows used.</p>}
    </div>
  )
}

function PerishTable({ h3 }) {
  return (
    <table style={{ marginTop: 12 }}>
      <thead><tr><th>Category</th><th className="r">Verified vs unverified (median epistemic)</th><th className="r">Test</th></tr></thead>
      <tbody>
        {Object.entries(h3).map(([k, v]) => (
          <tr key={k}>
            <td>{k === 'perishable' ? 'Perishable' : 'Shelf-stable'}</td>
            {v.note
              ? <td className="r note" colSpan={2}>{v.note} ({v.n_verified}/{v.n_unverified})</td>
              : <>
                  <td className="r num">{fix(v.median_verified)} vs {fix(v.median_unverified)}</td>
                  <td className="r num">{pval(v.p_one_sided)}</td>
                </>}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function h1Verdict(h1) {
  const sig = h1.p_one_sided < 0.05
  const dir = h1.verified.median_epistemic < h1.unverified.median_epistemic
  if (sig && dir) return 'Nodes with more complete traceability records show significantly lower epistemic uncertainty.'
  if (dir) return 'Verified nodes have lower median epistemic uncertainty, but the difference is not statistically significant at the 5% level, so the data do not support a firm claim.'
  return 'Verified nodes do not show lower epistemic uncertainty in this data. The hypothesis is not supported.'
}

function NodeTip({ active, payload }) {
  if (!active || !payload?.length) return null
  const n = payload[0].payload
  return (
    <div className="tip">
      <b>{n.commodity} · {n.country}</b>
      <div className="row"><span>Verification ratio</span><span>{pct(n.verification_ratio)}</span></div>
      <div className="row"><span>Mean epistemic</span><span>{fix(n.epistemic)}</span></div>
      <div className="row"><span>Group</span><span>{n.verified_group}</span></div>
    </div>
  )
}

function next(p) {
  const [y, m] = p.split('-').map(Number)
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`
}
function fmtRange(a, b) { return `${a} to ${b}` }
