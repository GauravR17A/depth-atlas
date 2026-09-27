import { useMemo } from 'react';
import { geoDistance, geoEquirectangular, geoGraticule10, geoOrthographic, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { GeometryObject, Topology } from 'topojson-specification';
import landTopology from 'world-atlas/land-110m.json';
import type { Region } from './contracts';
import type { MapView } from './store';

const topology = landTopology as unknown as Topology<{ land: GeometryObject }>;
const land = feature(topology, topology.objects.land);
const graticule = geoGraticule10();
const labels: { name: string; position: [number, number] }[] = [
  { name: 'AFRICA', position: [20, 2] },
  { name: 'INDIA', position: [78, 23] },
  { name: 'AUSTRALIA', position: [134, -25] },
  { name: 'ASIA', position: [105, 45] },
  { name: 'SOUTH AMERICA', position: [-62, -15] },
  { name: 'NORTH AMERICA', position: [-110, 42] },
];

function regionPolygon(bounds: Region['viewport_bounds']): GeoJSON.Polygon {
  const [west, south, rawEast, north] = bounds;
  const east = rawEast < west ? rawEast + 360 : rawEast;
  const coordinates: number[][] = [[west, south], [west, north]];
  for (let longitude = west + 1; longitude < east; longitude += 1) coordinates.push([longitude, north]);
  coordinates.push([east, north], [east, south]);
  for (let longitude = east - 1; longitude > west; longitude -= 1) coordinates.push([longitude, south]);
  coordinates.push([west, south]);
  return { type: 'Polygon', coordinates: [coordinates] };
}

export function GeographicPreview({ region, view, zoom }: { region: Region; view: MapView; zoom: number }) {
  const projection = useMemo(() => view === 'globe'
    ? geoOrthographic().rotate([-region.center[0], -region.center[1], 0]).scale(266 * zoom).translate([450, 325]).precision(0.3)
    : geoEquirectangular().rotate([-region.center[0], 0]).scale(138 * zoom).translate([450, 325]).precision(0.3), [region, view, zoom]);
  const path = geoPath(projection);
  const position = projection(region.center);

  return <svg className="geography" viewBox="0 0 900 650" role="img" aria-label={`Geographic preview of ${region.name}. Coastlines only; no ocean model data.`}>
    <defs>
      <radialGradient id="ocean-shading" cx="35%" cy="28%" r="78%">
        <stop offset="0%" stopColor="#183d4b" /><stop offset="60%" stopColor="#102b39" /><stop offset="100%" stopColor="#071621" />
      </radialGradient>
      <clipPath id="sphere-clip"><path d={path({ type: 'Sphere' }) ?? ''} /></clipPath>
    </defs>
    <g clipPath="url(#sphere-clip)">
      <path d={path({ type: 'Sphere' }) ?? ''} fill="url(#ocean-shading)" stroke="#376574" strokeWidth="1.2" />
      <path d={path(graticule) ?? ''} fill="none" stroke="#56818f" strokeWidth="0.6" strokeOpacity="0.24" />
      <path d={path(land) ?? ''} fill="#294651" stroke="#51717a" strokeWidth="0.7" />
      <path d={path(regionPolygon(region.viewport_bounds)) ?? ''} fill="#6be3ca" fillOpacity="0.13" stroke="#8ef1d9" strokeWidth="1.6" strokeDasharray="5 4" />
      {labels.map((label) => {
        if (view === 'globe' && geoDistance(region.center, label.position) > 1.35) return null;
        const point = projection(label.position);
        return point && <text key={label.name} x={point[0]} y={point[1]} textAnchor="middle" className="continent-label">{label.name}</text>;
      })}
      {position && <g transform={`translate(${position[0]}, ${position[1]})`}>
        <circle r="14" fill="#8ef1d9" fillOpacity="0.12" stroke="#8ef1d9" strokeOpacity="0.4" />
        <circle r="4" fill="#acffea" />
        <path d="M0 15v25h18" stroke="#8ef1d9" strokeWidth="1" fill="none" />
        <text x="24" y="45" className="region-map-label">{region.name}</text>
      </g>}
    </g>
    {view === 'globe' && <path d={path({ type: 'Sphere' }) ?? ''} fill="none" stroke="#477482" strokeOpacity="0.65" />}
  </svg>;
}
