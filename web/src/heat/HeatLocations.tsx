export type HeatLocationMarker = { id: string; label: string; longitude: number; latitude: number };

export function HeatLocations({ bounds, locations, selected, onSelect }: { bounds: [number, number, number, number]; locations: HeatLocationMarker[]; selected: string; onSelect: (id: string) => void }) {
  const [west, south, east, north] = bounds, left = 61, right = 570, top = 27, bottom = 188;
  const x = (longitude: number) => left + (longitude - west) / (east - west) * (right - left);
  const y = (latitude: number) => bottom - (latitude - south) / (north - south) * (bottom - top);
  return <figure className="heat-location-map">
    <svg viewBox="0 0 640 244" role="group" aria-label="Supported sea-surface temperature locations within the study case">
      <rect x={left} y={top} width={right - left} height={bottom - top} fill="#0a2330" stroke="#527787"/>
      {[0, .5, 1].map(f => <g key={f}><line x1={x(west + f * (east - west))} x2={x(west + f * (east - west))} y1={top} y2={bottom} stroke="#2d4e5d"/><line x1={left} x2={right} y1={y(south + f * (north - south))} y2={y(south + f * (north - south))} stroke="#2d4e5d"/><text x={x(west + f * (east - west))} y={bottom + 21} textAnchor="middle">{(west + f * (east - west)).toFixed(2)}° E</text><text x={left - 8} y={y(south + f * (north - south)) + 4} textAnchor="end">{(south + f * (north - south)).toFixed(1)}° N</text></g>)}
      {locations.map(location => <g key={location.id} role="button" aria-label={`Select ${location.label}`} aria-pressed={location.id === selected} tabIndex={0} onClick={() => onSelect(location.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(location.id); } }}>
        <rect x={x(location.longitude - .125)} y={y(location.latitude + .125)} width={x(west + .25) - x(west)} height={y(south) - y(south + .25)} fill={location.id === selected ? '#97dfc3' : '#52727d'} fillOpacity={location.id === selected ? .45 : .35} stroke={location.id === selected ? '#b8f2d9' : '#8aa9b4'}/>
        <circle cx={x(location.longitude)} cy={y(location.latitude)} r={4.5} fill={location.id === selected ? '#b8f2d9' : '#b2c5cd'}/>
        <text x={x(location.longitude)} y={y(location.latitude) - 17} textAnchor="middle">{location.label}</text>
        <rect x={x(location.longitude) - 23} y={y(location.latitude) - 25} width={46} height={50} fill="transparent"/>
      </g>)}
      <text x={(left + right) / 2} y="238" textAnchor="middle">Selected study rectangle; marked cells are 0.25° × 0.25°</text>
    </svg>
    <figcaption>These fixed source cells are local study points. They do not represent an average of the whole sea.</figcaption>
  </figure>;
}
