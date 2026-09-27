import { useMemo,useState } from 'react';
import { longitudeContext } from '../geography';
import { geoMercator,geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { GeometryObject,Topology } from 'topojson-specification';
import landTopology from 'world-atlas/land-110m.json';
import type { InstrumentSummary,Measurement } from './contracts';

const topology=landTopology as unknown as Topology<{land:GeometryObject}>;
const land=feature(topology,topology.objects.land);
export function InstrumentMap({profiles,selected,onSelect,sample}:{profiles:InstrumentSummary[];selected:string;onSelect:(id:string)=>void;sample?:Measurement}){
  const [detail,setDetail]=useState(false);
  const glider=profiles.some(p=>p.instrument==='glider');
  const projection=useMemo(()=>{
    const xy=profiles.flatMap(p=>p.track.length?p.track:[[p.longitude,p.latitude]]),longitudes=longitudeContext(xy.map(p=>p[0])),cx=longitudes.center,cy=xy.reduce((n,p)=>n+p[1],0)/Math.max(1,xy.length);
    // Minimum regional span keeps a single station in geographic context. Clamp Mercator near poles.
    const lonSpan=Math.max(detail&&glider?.002:14,longitudes.halfSpan*2.8),latSpan=Math.max(detail&&glider?.002:9,...xy.map(p=>Math.abs(p[1]-cy)*2.8));
    return geoMercator().rotate([-cx,0]).center([0,Math.max(-75,Math.min(75,cy))]).scale(Math.min(650/(lonSpan*Math.PI/180),320/(latSpan*Math.PI/180/Math.max(.25,Math.cos(cy*Math.PI/180))))).translate([360,195]);
  },[profiles,detail,glider]);
  const path=geoPath(projection),spot=sample?projection([sample.longitude,sample.latitude]):null;
  return <div className="instrument-map">{glider&&<div className="instrument-map-tools"><button aria-pressed={!detail} onClick={()=>setDetail(false)}>Region</button><button aria-pressed={detail} onClick={()=>setDetail(true)}>Track detail</button></div>}<svg viewBox="0 0 720 390" aria-label="Observed instrument locations" role="group">
    <defs><clipPath id="instrument-map-clip"><rect width="720" height="390"/></clipPath></defs>
    <g clipPath="url(#instrument-map-clip)"><rect width="720" height="390" fill="#0a202b"/><path d={path(land)??''} fill="#263f48" stroke="#72919c" strokeWidth=".6"/>
      {profiles.map(p=>{const pos=projection([p.longitude,p.latitude]);if(!pos)return null;return <g key={p.id}>
        {p.track.length>1&&<path d={path({type:'LineString',coordinates:p.track})??''} fill="none" stroke={p.id===selected?'#b2e7d4':'#7496a5'} strokeWidth={p.id===selected?2:1} />}
        <g role="button" tabIndex={0} aria-label={`${p.title}, ${p.time}`} aria-pressed={p.id===selected} onClick={()=>onSelect(p.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(p.id);}}} className="instrument-map-point" transform={`translate(${pos[0]},${pos[1]})`}>
          <title>{p.title} · {p.time}</title><circle r="15" fill="transparent"/><circle r={p.id===selected?7:5} stroke={p.id===selected?'#e0fff3':'#95bdc4'} fill={p.id===selected?'#2f897d':'#123440'} strokeWidth="2"/>
        </g>
      </g>;})}
      {spot&&<path d={`M${spot[0]-6},${spot[1]}h12M${spot[0]},${spot[1]-6}v12`} stroke="#ffd09f" strokeWidth="2" pointerEvents="none"/>}
    </g><text x="16" y="373" fill="#a0bbc5" fontSize="12">Natural Earth coastlines · WGS84 locations</text>
  </svg><p>Markers show profile locations. Tracks follow the source sample order. The cross marks the selected sample.</p></div>;
}
