import { useApi } from '../api.js'
import { pct } from '../format.js'

export default function Method() {
  const { data: commodities } = useApi('/commodities')
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data &amp; method</h1>
          <p>What goes in, what the model does with it, and what the numbers can and cannot tell you.</p>
        </div>
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        <Source title="US imports — UN Comtrade"
          url="https://comtradeapi.un.org"
          body="Monthly US import quantity (net weight, kg) by six-digit HS code and origin country, January 2016 onwards (earlier months carry values but no weights). This is the demand signal: each commodity–country pair is a supply node." />
        <Source title="Recalls — openFDA food enforcement"
          url="https://open.fda.gov/apis/food/enforcement/"
          body="Every FDA food recall with product, firm, lot codes, quantity, distribution and dates. Matched to commodities by keywords in the product description. Used for model inputs (only after FDA publishes them) and as evaluation events." />
        <Source title="Outbreaks — CDC NORS"
          url="https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/NORS/5xkq-dg7x"
          body="Foodborne outbreaks reported to CDC with the implicated food. Stored on the ledger and shown on node pages. Kept out of the model inputs because NORS is published with a long delay." />
      </div>

      <div className="grid cols-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>How a forecast is made</h2>
          <ol style={{ color: 'var(--ink-2)', paddingLeft: 18, marginBottom: 0 }}>
            <li>Take the node's last 24 months: log imports, calendar month, and how many FDA recalls of the commodity had been <em>published</em> by then.</li>
            <li>A two-layer GRU reads the sequence. The node's verification ratio, perishability and typical volume are added after it.</li>
            <li>The evidential head outputs four numbers (γ, ν, α, β) describing a Normal-Inverse-Gamma distribution.</li>
            <li>From those, in one pass: forecast = γ, aleatoric = β/(α−1), epistemic = β/(ν(α−1)), and a Student-t prediction interval.</li>
            <li>A node is <b>unreliable</b> when epistemic uncertainty is in the top 20% of what the model produced on the validation year, and <b>volatile</b> when aleatoric is.</li>
          </ol>
        </div>
        <div className="card">
          <h2>What "verified" means here</h2>
          <p style={{ color: 'var(--ink-2)' }}>
            No public data says which shipments were recorded on a blockchain. Instead, each real FDA
            recall record is checked against the Key Data Elements of the FDA Food Traceability Rule
            (FSMA §204): a lot code, a date, a quantity with unit, named distribution locations and a
            full firm address. A record passing all five is <b>verified</b>. A node's
            <b> verification ratio</b> is the share of its recall records that are verified, shrunk
            toward its commodity's rate when it has few records.
          </p>
          <p className="note" style={{ marginTop: 8 }}>
            The ratio uses only recalls published before the training cut-off, so it carries no
            information from the test period.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Limitations</h2>
        <ul style={{ color: 'var(--ink-2)', paddingLeft: 18, marginBottom: 0 }}>
          <li>Imports are a proxy for demand: they measure what crossed the border, not what consumers bought.</li>
          <li>Recall-to-commodity matching uses keywords, and most recalls do not name a country of origin, so many links are commodity-level rather than node-level.</li>
          <li>Record completeness is a stand-in for traceability infrastructure; it is not proof that a supplier used a blockchain.</li>
          <li>Statistical tests are run on about a hundred nodes. A null result is reported as a null result.</li>
        </ul>
      </div>

      {commodities && (
        <div className="card">
          <div className="card-head"><h2>Commodities tracked</h2><span>{commodities.length}</span></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Commodity</th><th>HS codes</th><th className="r">Nodes</th><th className="r">FDA recalls</th><th className="r">Verified share</th><th>Type</th></tr></thead>
              <tbody>
                {commodities.map(c => (
                  <tr key={c.key}>
                    <td>{c.label}</td>
                    <td className="mono">{c.hs_codes.join(', ')}</td>
                    <td className="r num">{c.nodes}</td>
                    <td className="r num">{c.recalls}</td>
                    <td className="r num">{pct(c.verified_share)}</td>
                    <td>{c.perishable ? 'perishable' : 'shelf-stable'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

function Source({ title, body, url }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      <p style={{ color: 'var(--ink-2)', fontSize: '0.88rem', margin: '6px 0' }}>{body}</p>
      <a href={url} target="_blank" rel="noreferrer" className="note">{url.replace('https://', '')}</a>
    </div>
  )
}
