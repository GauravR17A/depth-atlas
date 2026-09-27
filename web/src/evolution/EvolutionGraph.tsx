import { useMemo } from 'react';
import type { EvolutionAnalysis, EvolutionNode } from './contracts';
import { number, utc } from './shared';

export function EvolutionGraph({ result, selected, onSelect }: { result: EvolutionAnalysis; selected: string; onSelect: (id: string) => void }) {
  const graph = useMemo(() => {
    const nodes = result.frames.flatMap(frame => frame.regions), links = result.transitions.flatMap(transition => transition.links);
    const adjacency = new Map<string, Set<string>>();
    for (const link of links) {
      for (const [from, to] of [[link.source_node_id, link.target_node_id], [link.target_node_id, link.source_node_id]]) {
        if (!adjacency.has(from)) adjacency.set(from, new Set());
        adjacency.get(from)!.add(to);
      }
    }
    const connected = new Set<string>(), queue = selected ? [selected] : [];
    for (let index = 0; index < queue.length; index++) {
      const id = queue[index];
      if (connected.has(id)) continue;
      connected.add(id);
      for (const neighbour of adjacency.get(id) ?? []) if (!connected.has(neighbour)) queue.push(neighbour);
    }
    const visible = result.frames.map(frame => frame.regions.filter(node => connected.has(node.node_id)).sort((a, b) => (a.node_id === selected ? -1 : b.node_id === selected ? 1 : b.estimated_volume_km3 - a.estimated_volume_km3)).slice(0, 12));
    const positions = new Map<string, { x: number; y: number; node: EvolutionNode }>();
    const height = Math.max(320, 145 + Math.max(1, ...visible.map(frame => frame.length)) * 62);
    visible.forEach((frame, frameIndex) => frame.forEach((node, row) => positions.set(node.node_id, { x: 30 + frameIndex * 180, y: 108 + row * 62, node })));
    return { positions, width: Math.max(650, result.frames.length * 180 + 30), height, links: links.filter(link => positions.has(link.source_node_id) && positions.has(link.target_node_id)), count: connected.size, total: nodes.length };
  }, [result, selected]);
  return <>
    <div className="p14-graph-key"><span><i/>Accepted overlap link</span><span><i className="ambiguous"/>Many-to-many ambiguity</span><span><i className="gap"/>Time gap, no link inferred</span></div>
    <p className="p14-chart-caption">Scroll sideways to see all snapshots on smaller screens. You can also choose a source frame below.</p>
    <div className="p14-chart-scroll" tabIndex={0} role="region" aria-label="Feature correspondence graph, scroll horizontally for all timestamps">
      <svg viewBox={`0 0 ${graph.width} ${graph.height}`} style={{ minWidth: graph.width }} role="group" aria-label="Native region correspondence across selected source frames">
        <rect width={graph.width} height={graph.height} fill="#0a222e"/>
        {result.frames.map((frame, index) => <g key={frame.time_index}><line x1={102 + index * 180} x2={102 + index * 180} y1="82" y2={graph.height - 28} stroke="#294953"/><text x={102 + index * 180} y="30" textAnchor="middle">{frame.time.slice(5, 10)} · {frame.time.slice(11, 16)} UTC</text><text x={102 + index * 180} y="52" textAnchor="middle">{frame.total_regions} native {frame.total_regions === 1 ? 'region' : 'regions'}</text><text x={102 + index * 180} y="74" textAnchor="middle" fill="#9ebcc6">Frame {frame.time_index + 1}</text></g>)}
        {result.transitions.map((transition, index) => transition.status === 'gap' && <g key={index}><rect x={175 + index * 180} y="88" width="29" height={graph.height - 115} fill="#c9b18114" stroke="#b8a98c" strokeDasharray="3 5"/><text x={189 + index * 180} y={graph.height - 14} textAnchor="middle">{number(transition.elapsed_hours, 0)} h gap</text></g>)}
        {graph.links.map(link => { const a = graph.positions.get(link.source_node_id)!, b = graph.positions.get(link.target_node_id)!, ambiguous = link.classification === 'ambiguous'; return <path key={`${link.source_node_id}/${link.target_node_id}`} d={`M${a.x + 142},${a.y + 19}C${a.x + 164},${a.y + 19} ${b.x - 22},${b.y + 19} ${b.x},${b.y + 19}`} fill="none" stroke={ambiguous ? '#e8b47b' : '#91cbb7'} strokeWidth={ambiguous ? 2 : 1.8} strokeDasharray={ambiguous ? '5 4' : undefined}><title>{link.classification}: {link.source_node_id} to {link.target_node_id}; {number(link.overlap_coefficient * 100, 2)}% of the smaller estimated volume overlaps.</title></path>; })}
        {[...graph.positions].map(([id, { x, y, node }]) => <g key={id} transform={`translate(${x},${y})`} role="button" tabIndex={0} aria-label={`Inspect ${id}, ${node.cell_count} native ${node.cell_count === 1 ? 'cell' : 'cells'}`} aria-pressed={id === selected} onClick={() => onSelect(id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(id); } }}><title>{id} at {utc(result.frames.find(frame => frame.time_index === node.time_index)!.time)}, {number(node.estimated_volume_km3)} km³</title><rect width="142" height="39" rx="2" fill={id === selected ? '#4d4230' : '#183c3d'} stroke={id === selected ? '#efc28d' : '#699487'} strokeWidth={id === selected ? 2 : 1}/><text x="9" y="16" fontWeight="500">{id}</text><text x="9" y="32" fontSize="10">{number(node.cell_count, 0)} {node.cell_count === 1 ? 'cell' : 'cells'}</text></g>)}
        {graph.positions.size === 0 && <text x={graph.width / 2} y="160" textAnchor="middle">No selected region. Choose a frame containing a region.</text>}
      </svg>
    </div>
    <p className="p14-chart-caption">Showing {graph.positions.size} of {graph.count} nodes connected to the selected region, from {graph.total} region instances in the analysis. At most 12 nodes per frame are drawn; every region remains selectable below. Horizontal columns are source snapshots. Vertical position only arranges the diagram. A link describes overlapping threshold regions, not transport of the same water.</p>
  </>;
}
