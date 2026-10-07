import { useMemo } from 'react'
import { CircleMarker, GeoJSON, MapContainer, Polyline, Tooltip } from 'react-leaflet'
import { feature } from 'topojson-client'
import countries from 'i18n-iso-countries'
import worldTopo from 'world-atlas/countries-110m.json'
import { cssVar, kg } from '../format.js'

const world = feature(worldTopo, worldTopo.objects.countries)
const US = [39.5, -98.35]


// Area-weighted centroid of a country's largest polygon. Good enough to
// place a marker; we only need "roughly the middle of the country".
function centroid(geom) {
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates
  let best = null
  let bestArea = 0
  for (const poly of polys) {
    const ring = poly[0]
    let a = 0, cx = 0, cy = 0
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [x0, y0] = ring[j]
      const [x1, y1] = ring[i]
      const f = x0 * y1 - x1 * y0
      a += f
      cx += (x0 + x1) * f
      cy += (y0 + y1) * f
    }
    if (Math.abs(a) > bestArea) {
      bestArea = Math.abs(a)
      best = [cy / (3 * a), cx / (3 * a)]
    }
  }
  return best
}

const byIso3 = new Map()
for (const f of world.features) {
  const iso3 = countries.numericToAlpha3(f.id)
  if (iso3) byIso3.set(iso3, { feature: f, center: centroid(f.geometry) })
}

export default function SupplyMap({ nodes, selected, onSelect, showFlows = true, theme }) {
  const c = useMemo(() => ({
    reliable: cssVar('--good'), volatile: cssVar('--warning'), unreliable: cssVar('--critical'),
    muted: cssVar('--muted'), axis: cssVar('--axis'), ink: cssVar('--ink'), surface: cssVar('--surface'),
    surface2: cssVar('--surface-2'), us: cssVar('--accent-soft'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [theme])
  const placed = useMemo(() => {
    const groups = new Map()
    for (const n of nodes) {
      const g = groups.get(n.iso3) || []
      g.push(n)
      groups.set(n.iso3, g)
    }
    const out = []
    for (const [iso3, list] of groups) {
      const c = byIso3.get(iso3)?.center
      if (!c) continue
      // Several commodities from one country: lay them out on a sunflower
      // spiral around the centre so even Mexico's twenty-odd nodes stay clickable.
      list
        .sort((a, b) => b.total_kg - a.total_kg)
        .forEach((n, i) => {
          const r = list.length > 1 ? 1.9 * Math.sqrt(i + 0.5) : 0
          const angle = i * 2.39996
          out.push({ ...n, pos: [c[0] + r * Math.sin(angle), c[1] + r * 1.25 * Math.cos(angle)] })
        })
    }
    return out
  }, [nodes])

  const origins = useMemo(() => new Set(nodes.map(n => n.iso3)), [nodes])
  const volumes = nodes.map(n => Math.log10((n.total_kg || 1) / 1000)).filter(Number.isFinite)
  const vMin = Math.min(...volumes), vMax = Math.max(...volumes)
  const radius = n => {
    const v = Math.log10((n.total_kg || 1) / 1000)
    return 4 + ((v - vMin) / (vMax - vMin || 1)) * 7
  }

  return (
    <div className="map">
      <MapContainer center={[22, -10]} zoom={2} minZoom={2} maxZoom={6} worldCopyJump
        style={{ height: '100%', width: '100%' }} attributionControl={false}>
        <GeoJSON
          key={theme}
          data={world}
          style={f => {
            const iso3 = countries.numericToAlpha3(f.id)
            const origin = origins.has(iso3)
            return {
              color: c.axis, weight: 0.6,
              fillColor: iso3 === 'USA' ? c.us : origin ? c.surface : c.surface2,
              fillOpacity: 1,
            }
          }}
        />
        {showFlows && placed.map(n => (
          <Polyline key={`f-${n.node_id}`} positions={[n.pos, US]} interactive={false}
            pathOptions={{ color: c[n.status] || c.muted, weight: 1, opacity: 0.25 }} />
        ))}
        {placed.map(n => (
          <CircleMarker key={n.node_id} center={n.pos} radius={radius(n)}
            eventHandlers={{ click: () => onSelect?.(n.node_id) }}
            pathOptions={{
              color: selected === n.node_id ? c.ink : c.surface,
              weight: selected === n.node_id ? 2.5 : 2,
              fillColor: c[n.status] || c.muted,
              fillOpacity: 0.92,
            }}>
            <Tooltip direction="top" offset={[0, -6]}>
              <b>{n.label}</b> from {n.country}<br />
              Forecast {kg(n.forecast_kg)} · {n.status}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
