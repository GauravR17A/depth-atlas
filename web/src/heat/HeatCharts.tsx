import { useId } from 'react';

export type SurfaceSample = { date: string; temperature: number | null; baseline: number | null; threshold: number | null };
export type EventBand = { id: string; start: string; end: string };
export type DepthSample = { depth: number; value: number | null };
const tick = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 2 });
const day = (value: string) => Date.parse(value.slice(0, 10) + 'T00:00:00Z');
const shortDate = (value: string) => new Date(day(value)).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });

/** Gaps are preserved: every null starts a separate path. Display lines do not change source samples. */
function linePath(points: { x: number; y: number | null }[]) {
  let connected = false;
  return points.map(point => {
    if (point.y === null || !Number.isFinite(point.y)) { connected = false; return ''; }
    const command = connected ? 'L' : 'M'; connected = true;
    return `${command}${point.x.toFixed(3)},${point.y.toFixed(3)}`;
  }).join(' ');
}

export function SurfaceChart({ samples, events, selectedEvent, selectedIndex, onSample }: {
  samples: SurfaceSample[]; events: EventBand[]; selectedEvent: string | null; selectedIndex: number; onSample: (index: number) => void;
}) {
  const id = useId(), left = 95, right = 910, top = 38, bottom = 300;
  const temperatures = samples.flatMap(p => [p.temperature, p.baseline, p.threshold].filter((v): v is number => v !== null && Number.isFinite(v)));
  const minimum = temperatures.length ? Math.floor(Math.min(...temperatures) * 2) / 2 - .25 : 0;
  const maximum = temperatures.length ? Math.ceil(Math.max(...temperatures) * 2) / 2 + .25 : 1;
  const first = samples.length ? day(samples[0].date) : 0, last = samples.length ? day(samples[samples.length - 1].date) : 1;
  const x = (date: string) => left + (day(date) - first) / Math.max(86400000, last - first) * (right - left);
  const y = (temperature: number) => bottom - (temperature - minimum) / (maximum - minimum) * (bottom - top);
  const picked = samples[selectedIndex];
  function inspect(clientX: number, target: SVGSVGElement) {
    if (!samples.length) return;
    const rect = target.getBoundingClientRect(), plotX = (clientX - rect.left) * 960 / rect.width;
    const targetTime = first + (plotX - left) / (right - left) * (last - first);
    let chosen = 0;
    samples.forEach((sample, index) => { if (Math.abs(day(sample.date) - targetTime) < Math.abs(day(samples[chosen].date) - targetTime)) chosen = index; });
    onSample(chosen);
  }
  return <figure className="heat-chart heat-surface-chart">
    <div className="heat-chart-scroll" tabIndex={0} role="region" aria-label="Daily temperature chart, horizontally scrollable on small screens">
      <svg viewBox="0 0 960 370" role="img" aria-labelledby={`${id}-title ${id}-description`} onClick={event => inspect(event.clientX, event.currentTarget)}>
        <title id={`${id}-title`}>Daily analysed sea-surface temperature, seasonal mean and 90th-percentile threshold</title>
        <desc id={`${id}-description`}>Dates increase from left to right. Temperature in degrees Celsius increases upward. Shaded bands mark detected events. Missing readings interrupt curves. Use the daily sample control for exact values.</desc>
        <defs><clipPath id={`${id}-clip`}><rect x={left} y={top} width={right - left} height={bottom - top}/></clipPath></defs>
        {[0, .25, .5, .75, 1].map(fraction => <g key={fraction}><line x1={left} x2={right} y1={top + fraction * (bottom - top)} y2={top + fraction * (bottom - top)} className="heat-gridline"/><text x={left - 12} y={top + fraction * (bottom - top) + 4} textAnchor="end">{tick(maximum - fraction * (maximum - minimum))}</text></g>)}
        <g clipPath={`url(#${id}-clip)`}>
          {events.map(event => <rect key={event.id} x={x(event.start)} y={top} width={Math.max(2, x(event.end) - x(event.start) + (right - left) / Math.max(1, samples.length))} height={bottom - top} fill={event.id === selectedEvent ? '#e6a066' : '#c0956f'} opacity={event.id === selectedEvent ? .2 : .07}/>)}
          {([['baseline', '#a8b9bf', '5 4'], ['threshold', '#eab988', '7 3'], ['temperature', '#85dec7', undefined]] as const).map(([key, colour, dash]) => <path key={key} d={linePath(samples.map(p => ({ x: x(p.date), y: p[key] === null ? null : y(p[key]!) })))} fill="none" stroke={colour} strokeWidth={key === 'temperature' ? 2.1 : 1.6} strokeDasharray={dash}/>)}
          {picked && <g><line x1={x(picked.date)} x2={x(picked.date)} y1={top} y2={bottom} stroke="#deeaec" strokeDasharray="2 4"/>{picked.temperature !== null && <circle cx={x(picked.date)} cy={y(picked.temperature)} r={4.5} fill="#e7f5ed" stroke="#0a2730"/>}</g>}
        </g>
        {[0, .2, .4, .6, .8, 1].map(fraction => { const sample = samples[Math.round(fraction * Math.max(0, samples.length - 1))]; return sample ? <text key={fraction} x={x(sample.date)} y={bottom + 25} textAnchor="middle">{shortDate(sample.date)}</text> : null; })}
        <text transform="translate(19,170) rotate(-90)" textAnchor="middle">Temperature (°C)</text><text x={(left + right) / 2} y="355" textAnchor="middle">Daily source dates (UTC)</text>
      </svg>
    </div>
    <p className="heat-chart-scroll-hint">Swipe or scroll the chart horizontally to see later dates. The daily sample control gives exact values.</p>
    <figcaption><span><i className="heat-line-key sst"/>Analysed SST</span><span><i className="heat-line-key baseline"/>Seasonal mean</span><span><i className="heat-line-key threshold"/>90th-percentile threshold</span><span><i className="heat-band-key"/>Selected event</span></figcaption>
  </figure>;
}

export function DepthChart({ samples, name, units, selectedDepth, onDepth, referenceDepths = [] }: {
  samples: DepthSample[]; name: string; units: string; selectedDepth: number | null; onDepth?: (depth: number) => void; referenceDepths?: { depth: number; label: string; colour: string }[];
}) {
  const id = useId(), left = 72, right = 402, top = 32, bottom = 378;
  const values = samples.flatMap(p => p.value === null ? [] : [p.value]);
  const low = values.length ? Math.min(...values) : 0, high = values.length ? Math.max(...values) : 1;
  const padding = Math.max((high - low) * .08, Math.abs(high) * .0001, 1e-7), min = low - padding, max = high + padding;
  const maximumDepth = Math.max(1, ...samples.map(p => p.depth));
  const x = (value: number) => left + (value - min) / (max - min) * (right - left), y = (depth: number) => top + depth / maximumDepth * (bottom - top);
  const selected = samples.find(p => p.depth === selectedDepth);
  const tickDigits = Math.min(8, Math.max(0, 1 - Math.floor(Math.log10((max - min) / 4))));
  const format = (value: number) => Math.abs(value) < .001 && value !== 0 ? value.toExponential(2) : value.toLocaleString('en-US', { maximumFractionDigits: tickDigits });
  function inspect(clientY: number, target: SVGSVGElement) {
    if (!onDepth || !samples.length) return;
    const rect = target.getBoundingClientRect(), plotY = (clientY - rect.top) * 445 / rect.height, depth = (plotY - top) / (bottom - top) * maximumDepth;
    let closest = samples[0]; for (const sample of samples) if (Math.abs(sample.depth - depth) < Math.abs(closest.depth - depth)) closest = sample;
    onDepth(closest.depth);
  }
  return <figure className="heat-chart heat-depth-chart"><svg viewBox="0 0 450 445" role="img" aria-labelledby={`${id}-title ${id}-description`} onClick={event => inspect(event.clientY, event.currentTarget)}>
    <title id={`${id}-title`}>{name} versus depth, {units}</title><desc id={`${id}-description`}>Actual depth increases downwards. Lines stop at missing levels. Values come from the selected historical model column.</desc>
    {[0, .25, .5, .75, 1].map(fraction => <g key={fraction}><line x1={left} x2={right} y1={y(fraction * maximumDepth)} y2={y(fraction * maximumDepth)} className="heat-gridline"/><text x={left - 12} y={y(fraction * maximumDepth) + 4} textAnchor="end">{tick(fraction * maximumDepth)}</text><text x={left + fraction * (right - left)} y={bottom + 24} textAnchor="middle">{format(min + fraction * (max - min))}</text></g>)}
    {referenceDepths.filter(reference => reference.depth <= maximumDepth).map(reference => <g key={reference.label}><line x1={left} x2={right} y1={y(reference.depth)} y2={y(reference.depth)} stroke={reference.colour} strokeDasharray="5 4"/><text x={right - 3} y={y(reference.depth) - 6} textAnchor="end" style={{ fill: reference.colour }}>{reference.label}</text></g>)}
    <path d={linePath(samples.map(sample => ({ x: sample.value === null ? left : x(sample.value), y: sample.value === null ? null : y(sample.depth) })))} stroke="#8ce0c8" strokeWidth={2} fill="none"/>
    {samples.filter(p => p.value !== null).map(p => <circle key={p.depth} cx={x(p.value!)} cy={y(p.depth)} r={2} fill="#8ce0c8"/>)}
    {selected && <g><line x1={left} x2={right} y1={y(selected.depth)} y2={y(selected.depth)} stroke="#cadbdf" strokeDasharray="2 4"/>{selected.value !== null && <circle cx={x(selected.value)} cy={y(selected.depth)} r={4} fill="#ffe6bf"/>}</g>}
    <text transform="translate(20,205) rotate(-90)" textAnchor="middle">Depth (m), positive down</text><text x={(left + right) / 2} y="432" textAnchor="middle">{name} ({units})</text>
    {!values.length && <text x={(left + right) / 2} y="205" textAnchor="middle">No supported values</text>}
  </svg><figcaption>Dots mark samples at their actual depths. Connecting lines are guides, without smoothing.</figcaption></figure>;
}
