import type { Subset } from '../contracts';

export type Point = [number, number, number];
export type Grid = Pick<Subset, 'longitude' | 'latitude' | 'depth_m' | 'shape' | 'values'>;
export type ScalarDisplayGrid = Grid & { units: string };
export type ViewMode = 'volume' | 'slice' | 'section' | 'iso' | 'currents';
export type Palette = 'thermal' | 'teal' | 'mono';
export type Paint = { min: number; max: number; log: boolean; palette: Palette; opacity: number };
export const palettes: Record<Palette, string[]> = {
  thermal: ['#3686c4', '#39b2cc', '#78d2bd', '#d5dfa0', '#f3c775', '#ed8551'],
  teal: ['#297c9b', '#329baf', '#65bfae', '#a9ddbf', '#e2f1cc'],
  mono: ['#658394', '#8ba5b4', '#b7ccd5', '#e4eef2'],
};
export function rangeError(p: Paint): string | null {
  if (!Number.isFinite(p.min) || !Number.isFinite(p.max) || p.min >= p.max) return 'Minimum must be smaller than maximum.';
  if (p.log && p.min <= 0) return 'Log scale needs a minimum greater than zero.';
  return null;
}
export function fraction(value: number, p: Paint): number | null {
  if (!Number.isFinite(value) || rangeError(p) || (p.log && value <= 0)) return null;
  const v = p.log ? Math.log(value) : value;
  const lo = p.log ? Math.log(p.min) : p.min, hi = p.log ? Math.log(p.max) : p.max;
  return Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
}
export function rgb(value: number, p: Paint): Point | null {
  const t = fraction(value, p); if (t === null) return null;
  const stops = palettes[p.palette], f = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(f)), a = f - i;
  const decode = (hex: string) => [1, 3, 5].map(n => parseInt(hex.slice(n, n + 2), 16) / 255);
  const x = decode(stops[i]), y = decode(stops[i + 1]);
  return x.map((v, n) => v + (y[n] - v) * a) as Point;
}
export function nearest(axis: number[], value: number): number {
  let result = 0;
  for (let i = 1; i < axis.length; i++) if (Math.abs(axis[i] - value) < Math.abs(axis[result] - value)) result = i;
  return result;
}
export function bracket(axis: number[], value: number): [number, number] | null {
  if (axis.length < 2 || value < axis[0] || value > axis[axis.length - 1]) return null;
  let lo = 0, hi = axis.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (axis[mid] <= value) lo = mid; else hi = mid; }
  return [lo, (value - axis[lo]) / (axis[lo + 1] - axis[lo])];
}
export const offset = (g: Grid, x: number, y: number, z: number) => (z * g.latitude.length + y) * g.longitude.length + x;
export function sample(g: Grid, lon: number, lat: number, depth: number): number | null {
  const axes = [bracket(g.longitude, lon), bracket(g.latitude, lat), bracket(g.depth_m, depth)];
  if (axes.some(a => !a)) return null;
  const [a, b, c] = axes as [number, number][];
  let result = 0;
  for (let k = 0; k < 2; k++) for (let j = 0; j < 2; j++) for (let i = 0; i < 2; i++) {
    const w = (i ? a[1] : 1 - a[1]) * (j ? b[1] : 1 - b[1]) * (k ? c[1] : 1 - c[1]);
    if (w <= 1e-12) continue;
    const v = g.values[offset(g, a[0] + i, b[0] + j, c[0] + k)];
    if (v === null) return null;
    result += w * v;
  }
  return result;
}

// Local equirectangular display projection at the domain's central latitude.
// Depth uses metres and a separate, explicitly labelled visual exaggeration.
export function projection(g: Grid, exaggeration: number) {
  const rad = Math.PI / 180, radius = 6371008.8;
  const midLon = (g.longitude[0] + g.longitude.at(-1)!) / 2, midLat = (g.latitude[0] + g.latitude.at(-1)!) / 2;
  const eastM = radius * rad * Math.cos(midLat * rad), northM = radius * rad;
  const scale = 10 / ((g.longitude.at(-1)! - g.longitude[0]) * eastM);
  return {
    scale,
    point: (lon: number, lat: number, depth: number): Point => [(lon - midLon) * eastM * scale, -depth * scale * exaggeration, -(lat - midLat) * northM * scale],
    inverse: ([x, y, z]: Point): Point => [midLon + x / (eastM * scale), midLat - z / (northM * scale), -y / (scale * exaggeration)],
  };
}
export function speed(u: Subset, v: Subset): Subset {
  if (u.case_id !== v.case_id || u.time !== v.time || u.manifest_sha256 !== v.manifest_sha256 || JSON.stringify([u.longitude, u.latitude, u.depth_m]) !== JSON.stringify([v.longitude, v.latitude, v.depth_m])) throw new Error('Current components do not share the same coordinates and timestamp.');
  return { ...u, units: 'm/s', values: u.values.map((x, i) => x === null || v.values[i] === null ? null : Math.hypot(x, v.values[i]!)), processing: [...u.processing, 'Displayed horizontal speed = sqrt(eastward² + northward²). No vertical velocity.'] };
}
export type Surface = { positions: number[]; scalars: number[] };

/** A view window selects supplied depth levels; it never rescales their spacing. */
export function depthWindow(g: Subset, maximum: number): Subset {
  const count=g.depth_m.filter(d=>d<=maximum).length;
  if(count<2)throw new Error('A depth window needs at least two supplied levels.');
  return {...g,depth_m:g.depth_m.slice(0,count),shape:[count,g.latitude.length,g.longitude.length],values:g.values.slice(0,count*g.latitude.length*g.longitude.length)};
}
export function coverage(g: Grid) {
  const plane=g.latitude.length*g.longitude.length;
  const counts=g.depth_m.map((_,z)=>g.values.slice(z*plane,(z+1)*plane).filter(v=>v!==null).length);
  return {counts,empty:g.depth_m.filter((_,i)=>counts[i]===0),partial:g.depth_m.filter((_,i)=>counts[i]>0&&counts[i]<plane),deepest:g.depth_m.filter((_,i)=>counts[i]>0).at(-1)??null};
}

/** The cut lies on real source coordinate planes. Quarter removal is display-only. */
export function cutawayPlanes(g:Grid,exaggeration:number){
  const x=Math.floor(g.longitude.length/2),y=Math.floor(g.latitude.length/2),p=projection(g,exaggeration).point(g.longitude[x],g.latitude[y],0);
  return {x,y,worldX:p[0],worldZ:p[2]};
}

// Geometry uses real coordinates. No triangles are created across missing cells.
export function sliceMesh(g: Grid, mode: 'slice' | 'section' | 'meridian', index: number, exaggeration: number, missing=false): Surface {
  const project = projection(g, exaggeration), positions: number[] = [], scalars: number[] = [];
  const rows = mode === 'slice' ? g.latitude.length : g.depth_m.length;
  const cols = mode==='meridian'?g.latitude.length:g.longitude.length;
  for (let row = 0; row < rows - 1; row++) for (let col = 0; col < cols - 1; col++) {
    const nodes = [[col, row], [col + 1, row], [col + 1, row + 1], [col, row + 1]].map(([c, r]) => {
      const x=mode==='meridian'?index:c,y=mode==='slice'?r:mode==='meridian'?c:index,z=mode==='slice'?index:r;
      return { p: project.point(g.longitude[x], g.latitude[y], g.depth_m[z]), v: g.values[offset(g, x, y, z)] };
    });
    if (nodes.some(n => n.v === null)!==missing) continue;
    for (const i of [0, 1, 2, 0, 2, 3]) { positions.push(...nodes[i].p); scalars.push(nodes[i].v??0); }
  }
  return { positions, scalars };
}

export function cutawayFaces(g:Grid,exaggeration:number,missing=false):Surface {
  const cut=cutawayPlanes(g,exaggeration),out:Surface={positions:[],scalars:[]};
  for(const [mode,index,axis,keepAbove] of [['section',cut.y,0,true],['meridian',cut.x,2,true]] as const){
    const shape=sliceMesh(g,mode,index,exaggeration,missing),limit=axis===0?cut.worldX:cut.worldZ;
    for(let i=0;i<shape.scalars.length;i+=3){
      const center=(shape.positions[i*3+axis]+shape.positions[(i+1)*3+axis]+shape.positions[(i+2)*3+axis])/3;
      if(keepAbove&&center<limit-1e-8)continue;
      out.positions.push(...shape.positions.slice(i*3,(i+3)*3));out.scalars.push(...shape.scalars.slice(i,i+3));
    }
  }
  return out;
}

// Six tetrahedra share the same cell diagonal. Scalar values are piecewise
// linear within each tetrahedron. This is a display surface, not analysis.
export function isoMesh(g: Grid, threshold: number, exaggeration: number): Surface {
  const project = projection(g, exaggeration), positions: number[] = [], scalars: number[] = [];
  const corners = [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]];
  const tetra = [[0,5,1,6],[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6]];
  const vertex = (a: {p: Point; v: number}, b: {p: Point; v: number}): Point => {
    const f = (threshold - a.v) / (b.v - a.v);
    return a.p.map((v, i) => v + f * (b.p[i] - v)) as Point;
  };
  const add = (a: Point, b: Point, c: Point) => { positions.push(...a, ...b, ...c); scalars.push(threshold, threshold, threshold); };
  for (let z = 0; z < g.depth_m.length - 1; z++) for (let y = 0; y < g.latitude.length - 1; y++) for (let x = 0; x < g.longitude.length - 1; x++) {
    const values = corners.map(([i,j,k]) => g.values[offset(g, x+i, y+j, z+k)]);
    if (values.some(v => v === null) || threshold < Math.min(...values as number[]) || threshold > Math.max(...values as number[])) continue;
    const nodes = corners.map(([i,j,k], n) => ({ p: project.point(g.longitude[x+i], g.latitude[y+j], g.depth_m[z+k]), v: values[n]! }));
    for (const ids of tetra) {
      const inside = ids.filter(i => nodes[i].v >= threshold), outside = ids.filter(i => nodes[i].v < threshold);
      if (inside.length === 0 || outside.length === 0) continue;
      if (inside.length === 1 || outside.length === 1) {
        const one = inside.length === 1 ? inside[0] : outside[0], other = inside.length === 1 ? outside : inside;
        add(vertex(nodes[one], nodes[other[0]]), vertex(nodes[one], nodes[other[1]]), vertex(nodes[one], nodes[other[2]]));
      } else {
        const a = vertex(nodes[inside[0]], nodes[outside[0]]), b = vertex(nodes[inside[0]], nodes[outside[1]]);
        const c = vertex(nodes[inside[1]], nodes[outside[0]]), d = vertex(nodes[inside[1]], nodes[outside[1]]);
        add(a,b,c); add(b,d,c);
      }
    }
  }
  return { positions, scalars };
}
