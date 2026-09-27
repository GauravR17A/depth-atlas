import { useMemo } from 'react';
import type { EvolutionAnalysis, EvolutionNode } from './contracts';
import { latitudeLabel, longitudeLabel } from '../geography';

export function RegionExtent({ result, node }: { result: EvolutionAnalysis; node: EvolutionNode }) {
  const longitude = result.edges.longitude, latitude = result.edges.latitude;
  const x = (value: number) => 62 + (value - longitude[0]) / (longitude.at(-1)! - longitude[0]) * 388;
  const y = (value: number) => 260 - (value - latitude[0]) / (latitude.at(-1)! - latitude[0]) * 225;
  const path = useMemo(() => node.footprint_indices.map(index => {
    const i = index % (longitude.length - 1), j = Math.floor(index / (longitude.length - 1));
    return `M${x(longitude[i]).toFixed(2)},${y(latitude[j + 1]).toFixed(2)}h${(x(longitude[i + 1]) - x(longitude[i])).toFixed(2)}v${(y(latitude[j]) - y(latitude[j + 1])).toFixed(2)}h-${(x(longitude[i + 1]) - x(longitude[i])).toFixed(2)}Z`;
  }).join(''), [result, node]);
  return <figure className="p14-extent" style={{ margin: 0 }}><div className="p14-chart-scroll" tabIndex={0} role="region" aria-label="Selected feature footprint, scroll if needed"><svg viewBox="0 0 485 318" role="img" aria-label={`Actual native-column footprint of ${node.node_id}`}><rect x="62" y="35" width="388" height="225" fill="#0c2632" stroke="#456e7a"/><path d={path} fill="#e6b480" fillOpacity=".85"/>{[0, .25, .5, .75, 1].map(t => <g key={t}><line x1={62 + 388 * t} x2={62 + 388 * t} y1="35" y2="260" stroke="#86a5ab" opacity=".25"/><line x1="62" x2="450" y1={35 + 225 * t} y2={35 + 225 * t} stroke="#86a5ab" opacity=".25"/><text x={62 + 388 * t} y="282" textAnchor="middle">{longitudeLabel(longitude[0] + t * (longitude.at(-1)! - longitude[0]), 2)}</text><text x="55" y={39 + 225 * t} textAnchor="end">{latitudeLabel(latitude.at(-1)! - t * (latitude.at(-1)! - latitude[0]), 2)}</text></g>)}<text x="256" y="309" textAnchor="middle">Longitude · native model columns</text></svg></div><figcaption className="p14-chart-caption">Amber marks every native column touched by this region, including deeper cells. The footprint does not imply that the whole water column meets the threshold.</figcaption></figure>;
}
