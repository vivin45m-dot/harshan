import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, post } from '../api.js'
import { monthLabel } from '../format.js'
import { ErrorNote } from './Overview.jsx'

const KINDS = ['all', 'recall', 'outbreak', 'shipment']

export default function Ledger() {
  const [params] = useSearchParams()
  const [blocks, setBlocks] = useState(null)
  const [status, setStatus] = useState(null)
  const [sel, setSel] = useState(null)
  const [detail, setDetail] = useState(null)
  const [kind, setKind] = useState('recall')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState(params.get('ref') || '')
  const [hits, setHits] = useState(null)

  const refresh = () => Promise.all([
    api('/ledger/blocks?limit=500').then(setBlocks),
    api('/ledger/verify').then(setStatus),
  ]).catch(setError)

  useEffect(() => { refresh() }, [])

  useEffect(() => {
    if (blocks && sel == null) setSel(blocks.blocks[0]?.idx ?? null)
  }, [blocks, sel])

  useEffect(() => {
    if (sel == null) return
    api(`/ledger/blocks/${sel}${kind === 'all' ? '' : `?kind=${kind}`}`).then(setDetail).catch(setError)
  }, [sel, kind, status])

  useEffect(() => {
    const ref = params.get('ref')
    if (ref) runSearch(ref)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runSearch(q) {
    if (!q.trim()) { setHits(null); return }
    const res = await api(`/ledger/search?ref=${encodeURIComponent(q.trim())}`)
    setHits(res)
    if (res.length === 1) { setSel(res[0].block_idx); setKind(res[0].kind) }
  }

  async function tamper(record) {
    const field = record.kind === 'shipment' ? 'qty_kg' : record.kind === 'recall' ? 'quantity' : 'illnesses'
    const current = record.payload[field]
    const value = record.kind === 'recall' ? `${current ?? ''} (edited)` : Number(current || 0) + 1000
    setBusy(true)
    try { setStatus(await post('/ledger/tamper', { record_id: record.id, field, value })) }
    finally { setBusy(false) }
  }

  async function restore() {
    setBusy(true)
    try { setStatus(await post('/ledger/restore')) } finally { setBusy(false) }
  }

  if (error) return <ErrorNote error={error} />
  const broken = new Set((status?.problems ?? []).map(p => p.block_index))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Provenance ledger</h1>
          <p>
            Every import figure, FDA recall and CDC outbreak used by the model is stored in a
            SHA-256 proof-of-work chain, one block per month. Edit any record and the chain
            shows exactly which block no longer matches.
          </p>
        </div>
      </div>

      {status && (
        <div className={`chain-banner ${status.valid ? 'ok' : 'bad'}`} style={{ marginBottom: 16 }}>
          <span className={`pill ${status.valid ? 'reliable' : 'unreliable'}`}><i />{status.valid ? 'Chain valid' : 'Chain broken'}</span>
          <span style={{ flex: 1 }}>
            {status.valid
              ? `All ${blocks?.total ?? ''} blocks re-hashed: Merkle roots, links and proof of work all check out (difficulty ${blocks?.difficulty}).`
              : status.problems.map(p => `Block #${p.block_index} (${monthLabel(p.period)}): ${p.detail}`).join(' · ')}
          </span>
          {!status.valid && <button className="btn" disabled={busy} onClick={restore}>Restore original records</button>}
          <button className="btn" disabled={busy} onClick={refresh}>Re-verify</button>
        </div>
      )}

      <div className="split" style={{ gridTemplateColumns: '320px minmax(0,1fr)' }}>
        <div className="card">
          <div className="card-head">
            <h2>Blocks</h2>
            <span>{blocks?.total} · newest first</span>
          </div>
          <form className="controls" style={{ marginBottom: 10 }}
            onSubmit={e => { e.preventDefault(); runSearch(search) }}>
            <input type="search" placeholder="Find a recall number, e.g. F-0276-2017" value={search}
              onChange={e => setSearch(e.target.value)} style={{ flex: 1 }} />
          </form>
          {hits && (
            <div style={{ marginBottom: 10 }} className="note">
              {hits.length ? hits.map(h => (
                <div key={h.id}>
                  <a href="#" onClick={e => { e.preventDefault(); setSel(h.block_idx); setKind(h.kind) }}>
                    {h.source_ref}</a> → block #{h.block_idx}
                </div>
              )) : 'No match.'}
            </div>
          )}
          <div className="blocks">
            {blocks?.blocks.map(b => (
              <div key={b.idx} className={`block ${sel === b.idx ? 'sel' : ''} ${broken.has(b.idx) ? 'broken' : ''}`}
                onClick={() => setSel(b.idx)}>
                <span className="mono">#{b.idx}</span>
                <span>
                  {monthLabel(b.period)}
                  <div className="note">{b.recalls} recalls · {b.outbreaks} outbreaks · {b.shipments} shipments</div>
                </span>
                <span className="hash" title={b.hash}>{b.hash.slice(0, 8)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          {detail ? <BlockDetail detail={detail} kind={kind} setKind={setKind} onTamper={tamper} busy={busy}
            broken={broken.has(detail.block.idx)} /> : <p className="empty">Select a block.</p>}
        </div>
      </div>
    </>
  )
}

function BlockDetail({ detail, kind, setKind, onTamper, busy, broken }) {
  const b = detail.block
  return (
    <>
      <div className="card-head">
        <h2>Block #{b.idx} · {monthLabel(b.period)}</h2>
        {broken && <span className="pill unreliable"><i />does not verify</span>}
      </div>
      <dl className="kv" style={{ marginBottom: 14 }}>
        <dt>Block hash</dt><dd className="hash">{b.hash}</dd>
        <dt>Previous hash</dt><dd className="hash">{b.prev_hash}</dd>
        <dt>Merkle root</dt><dd className="hash">{b.merkle}</dd>
        <dt>Nonce</dt><dd className="num">{b.nonce.toLocaleString()}</dd>
        <dt>Records</dt><dd className="num">{b.record_count}</dd>
      </dl>
      <div className="controls" style={{ marginBottom: 10 }}>
        <div className="seg">
          {KINDS.map(k => (
            <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{k}</button>
          ))}
        </div>
        <span className="note">"Tamper" edits one stored field without re-mining, the way an insider might.</span>
      </div>
      <div className="table-wrap" style={{ maxHeight: 520, overflowY: 'auto' }}>
        <table>
          <thead>
            <tr><th>Record</th><th>Contents</th><th>Leaf hash</th><th /></tr>
          </thead>
          <tbody>
            {detail.records.map(r => (
              <tr key={r.id} style={r.tampered ? { background: 'color-mix(in srgb, var(--critical) 10%, transparent)' } : null}>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <span className="mono">{r.source_ref}</span>
                  <div className="note">{r.kind} · {r.commodity}{r.verified === 1 ? ' · verified' : r.verified === 0 ? ' · incomplete' : ''}</div>
                </td>
                <td style={{ maxWidth: 420 }}><Payload r={r} /></td>
                <td className="hash" style={{ maxWidth: 120 }}>{r.hash.slice(0, 16)}…</td>
                <td>
                  {r.tampered
                    ? <span className="note" style={{ color: 'var(--critical-ink)' }}>edited</span>
                    : <button className="btn danger" disabled={busy} onClick={() => onTamper(r)}>Tamper</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!detail.records.length && <p className="empty">No {kind} records in this block.</p>}
      </div>
    </>
  )
}

function Payload({ r }) {
  const p = r.payload
  if (r.kind === 'shipment') {
    return <span>{p.origin}: <b className="num">{Number(p.qty_kg).toLocaleString()} kg</b></span>
  }
  if (r.kind === 'recall') {
    return (
      <div>
        <b style={{ fontWeight: 600 }}>{p.firm}</b> <span className="note">({p.classification})</span>
        <div style={{ color: 'var(--ink-2)' }}>{(p.product || '').slice(0, 140)}</div>
        <div className="note">Qty: {p.quantity || '—'}</div>
      </div>
    )
  }
  return (
    <div>
      {p.food_vehicle || p.ingredient} <span className="note">· {p.state}</span>
      <div className="note">{p.etiology || 'unknown agent'} · {p.illnesses} ill · {p.hospitalizations} hospitalised</div>
    </div>
  )
}
