import { useId, useMemo } from 'react';
import { latitudeLabel, longitudeLabel } from '../geography';

type Maybe = number | null;
const number = (value: Maybe, digits = 2) => value === null ? 'Missing' : (value === 0 ? 0 : value).toLocaleString('en-US', { maximumFractionDigits: digits });
const edges = (axis: number[]) => [axis[0], ...axis.slice(1).map((value, index) => (axis[index] + value) / 2), axis.at(-1)!];
const palette = { anomaly: [[49, 110, 146], [210, 223, 222], [178, 83, 50]], temperature: [[30, 74, 113], [74, 157, 151], [234, 195, 112]] };
function colour(value: number, range: [number, number], mode: 'anomaly' | 'temperature') {
  const t = range[0] === range[1] ? 1 : Math.max(0, Math.min(1, (value - range[0]) / (range[1] - range[0]))) * 2;
  const stops = palette[mode], low = t <= 1 ? stops[0] : stops[1], high = t <= 1 ? stops[1] : stops[2], fraction = t <= 1 ? t : t - 1;
  return `rgb(${low.map((channel, index) => Math.round(channel + (high[index] - channel) * fraction)).join(',')})`;
}

export function ClimateSection({ title, subtitle, longitude, depth, latitude, values, range, mode, quantityLabel, selected, onSelect }: {
  title: string; subtitle: string; longitude: number[]; depth: number[]; latitude: number; values: Maybe[];
  range: [number, number]; mode: 'anomaly' | 'temperature'; quantityLabel?: string; selected?: [number, number]; onSelect?: (longitudeIndex: number, depthIndex: number) => void;
}) {
  const id = useId().replaceAll(':', ''), width = 830, height = 350, left = 62, right = 24, top = 20, bottom = 61;
  const x = (value: number) => left + (value - longitude[0]) / (longitude.at(-1)! - longitude[0]) * (width - left - right);
  const y = (value: number) => top + (value - depth[0]) / (depth.at(-1)! - depth[0]) * (height - top - bottom);
  const longitudeEdges = useMemo(() => edges(longitude), [longitude]), depthEdges = useMemo(() => edges(depth), [depth]);
  const cells = useMemo(() => values.map((value, index) => {
    const zi = Math.floor(index / longitude.length), xi = index % longitude.length;
    return <rect key={index} x={x(longitudeEdges[xi])} y={y(depthEdges[zi])} width={Math.max(.1, x(longitudeEdges[xi + 1]) - x(longitudeEdges[xi]))} height={Math.max(.1, y(depthEdges[zi + 1]) - y(depthEdges[zi]))} fill={value === null ? `url(#${id})` : colour(value, range, mode)}/>;
  }), [values, longitude, depth, range, mode, id]);
  const marker = selected && selected[0] < longitude.length && selected[1] < depth.length ? selected : undefined;
  return <figure className="climate-section-figure">
    <figcaption><h4>{title}</h4><p>{subtitle}</p></figcaption>
    <div className="climate-chart-scroll" role="region" tabIndex={0} aria-label={`${title}, scroll horizontally when needed`}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title}: ${quantityLabel ?? (mode === 'anomaly' ? 'temperature anomaly' : 'potential temperature')} by longitude and depth`} onClick={event => {
        if (!onSelect) return;
        const matrix = event.currentTarget.getScreenCTM(); if (!matrix) return;
        const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
        if (point.x < left || point.x > width - right || point.y < top || point.y > height - bottom) return;
        const lon = longitude[0] + (point.x - left) / (width - left - right) * (longitude.at(-1)! - longitude[0]);
        const z = depth[0] + (point.y - top) / (height - top - bottom) * (depth.at(-1)! - depth[0]);
        const nearest = (axis: number[], value: number) => axis.reduce((best, current, index) => Math.abs(current - value) < Math.abs(axis[best] - value) ? index : best, 0);
        onSelect(nearest(longitude, lon), nearest(depth, z));
      }}>
        <defs><pattern id={id} width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#19323e"/><path d="M0 7L7 0" stroke="#67818a" strokeWidth="1"/></pattern></defs>
        <g shapeRendering="crispEdges">{cells}</g>
        <rect x={left} y={top} width={width - left - right} height={height - top - bottom} fill="none" stroke="#7595a0"/>
        {[0, .25, .5, .75, 1].map(fraction => <g key={fraction}><text x={left + fraction * (width - left - right)} y={height - bottom + 23} textAnchor={fraction === 0 ? 'start' : fraction === 1 ? 'end' : 'middle'}>{longitudeLabel(longitude[0] + fraction * (longitude.at(-1)! - longitude[0]), 1)}</text><text x={left - 10} y={top + fraction * (height - top - bottom) + 4} textAnchor="end">{number(depth[0] + fraction * (depth.at(-1)! - depth[0]), 0)}</text></g>)}
        <text x={(width + left - right) / 2} y={height - 10} textAnchor="middle">Longitude west to east · latitude {latitudeLabel(latitude, 3)}</text>
        <text transform={`translate(16 ${(height + top - bottom) / 2}) rotate(-90)`} textAnchor="middle">Depth (m)</text>
        {marker && <g pointerEvents="none"><line x1={x(longitude[marker[0]])} x2={x(longitude[marker[0]])} y1={top} y2={height - bottom} stroke="#122a32" strokeWidth="3"/><line x1={x(longitude[marker[0]])} x2={x(longitude[marker[0]])} y1={top} y2={height - bottom} stroke="#f5f1dc" strokeWidth="1" strokeDasharray="5 4"/><circle cx={x(longitude[marker[0]])} cy={y(depth[marker[1]])} r="5" fill="none" stroke="#122a32" strokeWidth="4"/><circle cx={x(longitude[marker[0]])} cy={y(depth[marker[1]])} r="5" fill="none" stroke="#fff9e6" strokeWidth="1.5"/></g>}
      </svg>
    </div>
    <p className="climate-chart-hint">Scroll sideways on a small screen. {onSelect && 'Select a cell or use the longitude and depth controls to inspect its exact value. '}Hatching means missing source or baseline data.</p>
  </figure>;
}

export function ClimateColourbar({ range, mode, label, hasFinite = true }: { range: [number, number]; mode: 'anomaly' | 'temperature'; label: string; hasFinite?: boolean }) {
  if (!hasFinite) return <p className="climate-note" aria-label={label}>No finite values for this colour scale. Hatched cells have missing source or baseline data.</p>;
  return <div className="climate-colourbar" aria-label={label}><span>{number(range[0])} °C</span><div><span style={{ background: range[0] === range[1] ? colour(range[0], range, mode) : `linear-gradient(to right,${palette[mode].map(channels => `rgb(${channels.join(',')})`).join(',')})` }}/><small>{label}{range[0] === range[1] ? ' · constant finite value' : ''}</small></div><span>{number(range[1])} °C</span></div>;
}

export function ClimateProfiles({ depth, first, second, baseline, labels, selectedDepth }: { depth: number[]; first: Maybe[]; second: Maybe[]; baseline: Maybe[]; labels: [string, string]; selectedDepth: number }) {
  const width = 480, height = 390, left = 59, right = 30, top = 35, bottom = 49;
  const finite = [...first, ...second, ...baseline].filter((value): value is number => value !== null);
  const min = finite.length ? Math.floor(Math.min(...finite)) : 0, max = finite.length ? Math.max(min + 1, Math.ceil(Math.max(...finite))) : 1;
  const x = (value: number) => left + (value - min) / (max - min) * (width - left - right), y = (value: number) => top + (value - depth[0]) / (depth.at(-1)! - depth[0]) * (height - top - bottom);
  const line = (values: Maybe[]) => { let previous = false; return values.map((value, index) => { if (value === null) { previous = false; return ''; } const command = previous ? 'L' : 'M'; previous = true; return `${command}${x(value)},${y(depth[index])}`; }).join(' '); };
  return <figure className="climate-profile-figure"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Synchronized potential temperature profiles versus actual depth">
    {[0, .25, .5, .75, 1].map(fraction => <g key={fraction}><line x1={left} x2={width - right} y1={top + fraction * (height - top - bottom)} y2={top + fraction * (height - top - bottom)} stroke="#355361"/><text x={left - 9} y={top + fraction * (height - top - bottom) + 4} textAnchor="end">{number(depth[0] + fraction * (depth.at(-1)! - depth[0]), 0)}</text><text x={left + fraction * (width - left - right)} y={height - bottom + 22} textAnchor="middle">{number(min + fraction * (max - min), 1)}</text></g>)}
    <path d={line(baseline)} fill="none" stroke="#a2b2ba" strokeWidth="1.7" strokeDasharray="5 4"/><path d={line(first)} fill="none" stroke="#e2b07e" strokeWidth="2.2"/><path d={line(second)} fill="none" stroke="#83cdda" strokeWidth="2.2"/>
    <line x1={left} x2={width - right} y1={y(selectedDepth)} y2={y(selectedDepth)} stroke="#b6dfb5" strokeWidth="1.4" strokeDasharray="3 4"/>
    <text x={(width + left - right) / 2} y={height - 6} textAnchor="middle">Potential temperature (°C)</text><text transform={`translate(15 ${(height + top - bottom) / 2}) rotate(-90)`} textAnchor="middle">Depth (m)</text>
  </svg><figcaption><span><i className="climate-line first"/>{labels[0]}</span><span><i className="climate-line second"/>{labels[1]}</span><span><i className="climate-line baseline"/>1991–2020 mean for the same months</span></figcaption></figure>;
}
