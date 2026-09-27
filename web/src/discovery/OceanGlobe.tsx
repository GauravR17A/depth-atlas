import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { geoDistance,geoEquirectangular,geoGraticule10,geoOrthographic,geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { GeometryObject,Topology } from 'topojson-specification';
import landTopology from 'world-atlas/land-110m.json';
import { ArrowRight,ChevronLeft,ChevronRight,Globe2,LoaderCircle,Minus,Plus,RotateCcw } from 'lucide-react';
import { appVersion,getApi,type Catalog,type CaseSummary } from '../contracts';
import type { InstrumentCatalog,InstrumentProfile } from '../instruments/contracts';
import { parseInstrumentCatalog,safeSource } from '../instruments/contracts';
import type { ImportedSource } from '../instruments/imported';
import { latitudeLabel,longitudeLabel,normalizedLongitude } from '../geography';
import { useLearningTool } from '../learning/bridge';
import { caseCenter,footprint,locateObservations,modelContexts,type LocatedObservation } from './data';
import { readPublicExample } from './example';
import './globe.css';
import { PublicationStatus,type Publication } from '../PublicationStatus';

const topology=landTopology as unknown as Topology<{land:GeometryObject}>,land=feature(topology,topology.objects.land),graticule=geoGraticule10();
const kind={argo:'Argo float',bgc:'BGC float',glider:'Glider',ctd:'Ship CTD'};
const date=(s:string)=>s.replace('T',' ').replace('Z',' UTC');
type Lens='models'|'observations'|'chlorophyll';
type Props={catalog:Catalog;instruments?:InstrumentCatalog;instrumentError?:Error|null;retryInstruments:()=>void;imports:InstrumentProfile[];selectedCaseId?:string;onModel:(id:string)=>void;onProfile:(id:string,caseId?:string,example?:{profiles:InstrumentProfile[];source:ImportedSource})=>void;onWider:()=>void};

export function OceanGlobe({catalog,instruments,instrumentError,retryInstruments,imports,selectedCaseId,onModel,onProfile,onWider}:Props){
  const initial=catalog.cases.find(c=>c.id===selectedCaseId)??catalog.cases[0];
  const [publicationOpen,setPublicationOpen]=useState(false),[publication,setPublication]=useState<Publication>(),[publicationError,setPublicationError]=useState(''),[publicationRequest,setPublicationRequest]=useState(0);
  const [lens,setLens]=useState<Lens>('models'),[modelId,setModelId]=useState(initial?.id??''),[profileId,setProfileId]=useState('');
  const [center,setCenter]=useState<[number,number]>(initial?caseCenter(initial):[80,12]),[view,setView]=useState<'globe'|'map'>('globe'),[zoom,setZoom]=useState(1);
  const [example,setExample]=useState<Awaited<ReturnType<typeof readPublicExample>>>(),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const controller=useRef<AbortController|null>(null),drag=useRef<{x:number;y:number;center:[number,number]}|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const libraries=useQueries({queries:catalog.cases.map(c=>({queryKey:['instrument-catalog',appVersion,c.id],queryFn:({signal}:{signal:AbortSignal})=>getApi(`/api/instruments?case_id=${encodeURIComponent(c.id)}`,parseInstrumentCatalog,signal),enabled:lens!=='models',staleTime:Infinity}))});
  const profiles=[...new Map([...(instruments?.profiles??[]),...libraries.flatMap(q=>q.data?.profiles??[]),...(example?.profiles??[]),...imports].map(p=>[p.id,p])).values()];
  const observations=useMemo(()=>locateObservations(profiles,lens==='chlorophyll'?'chlorophyll':undefined),[profiles,lens]);
  const selected=observations.find(p=>p.profile.id===profileId)??observations[0];
  const model=catalog.cases.find(c=>c.id===modelId)??initial;
  const contexts=selected?modelContexts(catalog.cases,selected):[];
  const areaLabels=catalog.regions.flatMap(r=>{const c=catalog.cases.find(c=>c.region_id===r.id&&c.id===modelId)??catalog.cases.find(c=>c.region_id===r.id);return c?[{name:r.name,model:c}]:[];});
  const projection=useMemo(()=>view==='globe'?geoOrthographic().rotate([-center[0],-center[1]]).translate([380,300]).scale(255*zoom).precision(.3):geoEquirectangular().rotate([-center[0],0]).translate([380,300]).scale(118*zoom).precision(.3),[view,center,zoom]);
  const path=geoPath(projection);
  function focusModel(c:CaseSummary){setModelId(c.id);setCenter(caseCenter(c));setZoom(1);}
  function focusProfile(p:LocatedObservation){setProfileId(p.profile.id);setCenter(p.position);setZoom(1);}
  async function loadExample(signal?:AbortSignal,tutorial=false){
    if(example){const point=locateObservations(example.profiles,'chlorophyll')[0];if(point)focusProfile(point);return true;}
    const source=instruments?.examples.find(e=>e.name==='SR1902594_034.nc');
    if(!source){if(!instruments){if(instrumentError)retryInstruments();return false;}const message='No source-checked chlorophyll example is available. You can import a supported BGC file in Instruments.';setError(message);if(tutorial)throw new Error(message);return false;}
    controller.current?.abort();const request=new AbortController();controller.current=request;
    const timer=setTimeout(()=>request.abort(),45000);setLoading(true);setError('');
    try{
      const result=await readPublicExample(source,signal?AbortSignal.any([signal,request.signal]):request.signal);
      if(request.signal.aborted||signal?.aborted)return false;
      const point=locateObservations(result.profiles,'chlorophyll')[0];if(!point)throw new Error('This example contains no located chlorophyll measurements.');
      setExample(result);focusProfile(point);return true;
    }catch(e){if(signal?.aborted)return false;if(controller.current===request)setError(request.signal.aborted?'Loading stopped. Existing observations are kept. Retry when ready.':e instanceof Error?e.message:'The source could not load.');if(tutorial)throw e;return false;}
    finally{clearTimeout(timer);if(controller.current===request)setLoading(false);}
  }
  function chooseLens(next:Lens){controller.current?.abort();controller.current=null;setLoading(false);setError('');setLens(next);if(next==='models'&&model)focusModel(model);else{const p=locateObservations(profiles,next==='chlorophyll'?'chlorophyll':undefined)[0];if(p)focusProfile(p);}}
  const focusItem=lens==='models'?model:selected?.profile;
  useLearningTool('geography',true,{tool:'geography',caseId:selectedCaseId??'',status:error||publicationOpen&&publicationError?'error':loading||publicationOpen&&!publication?'loading':focusItem?'ready':'empty',title:'Find the data on Earth',kind:'source',facts:publicationOpen?[{label:'Application',value:publication?.app_version??null},{label:'Publication checked',value:publication?.serving?.checked_at??null}]:lens==='models'?[{label:'Model area',value:model?.title??null},{label:'Source',value:model?.source_label??null}]:[{label:'Instrument',value:selected?kind[selected.profile.instrument]:null},{label:'Observed (UTC)',value:selected?.time??null}],parameters:{view,lens},sources:[{label:'Model catalogue',href:'/api/catalog'}],limits:['Outlines show model domains, not sensor coverage. Observation dots have their own dates. A location or time overlap does not establish an eligible comparison.'],message:error||(publicationOpen?publicationError:'')},async(command,signal)=>{
    if(command.action==='publication'){setError('');setPublication(undefined);setPublicationError('');setPublicationRequest(command.id);setPublicationOpen(true);return true;}
    setPublicationOpen(false);
    if(command.action==='locate'){setLens('models');const c=catalog.cases.find(c=>c.id===command.caseId)??initial;if(c)focusModel(c);return Boolean(c);}
    if(command.action==='chlorophyll'){setLens('chlorophyll');return loadExample(signal,true);}
    if(command.action==='sensors'){setLens('observations');const p=locateObservations(profiles)[0];if(p)focusProfile(p);return Boolean(p);}
    throw new Error('This globe action is not supported.');
  });
  function openProfile(){if(!selected)return;setError('');try{onProfile(selected.profile.id,contexts[0]?.model.id,example?.profiles.some(p=>p.id===selected.profile.id)&&!imports.some(p=>p.id===selected.profile.id)?example:undefined);}catch(e){setError(e instanceof Error?e.message:'The profile could not open.');}}
  return <section className="ocean-globe" aria-label="Ocean data globe">
    <header className="globe-heading"><div><span className="eyebrow">LOCATE THE DATA</span><h2>Where shall we look?</h2><p>Find a model area or a measured profile. Then open it at depth.</p></div><button className="secondary-button" onClick={()=>model&&onModel(model.id)}>Open 3D ocean <ArrowRight size={16}/></button></header>
    <div className="globe-lenses" role="group" aria-label="Find on globe">{([['models','Model areas'],['observations','Instrument locations'],['chlorophyll','Chlorophyll observations']] as const).map(([id,label])=><button key={id} aria-pressed={lens===id} onClick={()=>chooseLens(id)}>{label}</button>)}</div>
    <div className="globe-layout">
      <div className="globe-figure">
        <div className="globe-view-controls" aria-label="Globe projection"><button aria-pressed={view==='globe'} onClick={()=>setView('globe')}>Globe</button><button aria-pressed={view==='map'} onClick={()=>setView('map')}>Map</button></div>
        <svg viewBox="0 0 760 600" role="group" aria-label="Interactive data locations" className="data-globe" onPointerDown={e=>{if((e.target as Element).closest('[data-pick]'))return;drag.current={x:e.clientX,y:e.clientY,center};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!drag.current)return;const d=drag.current,k=280/e.currentTarget.getBoundingClientRect().width;setCenter([normalizedLongitude(d.center[0]-(e.clientX-d.x)*k),Math.max(-75,Math.min(75,d.center[1]+(e.clientY-d.y)*k))]);}} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
          <title>Model domains and original observation positions</title>
          <defs><radialGradient id="data-ocean"><stop stopColor="#1c4b5e"/><stop offset="1" stopColor="#081c2a"/></radialGradient><clipPath id="data-sphere"><path d={path({type:'Sphere'})??''}/></clipPath></defs>
          <g clipPath="url(#data-sphere)"><path d={path({type:'Sphere'})??''} fill="url(#data-ocean)" stroke="#416877"/><path d={path(graticule)??''} fill="none" stroke="#789aaa" strokeOpacity=".19" strokeWidth=".65"/><path d={path(land)??''} fill="#34505b" stroke="#73919a" strokeWidth=".6"/>
            {catalog.cases.map(c=>{const outline=path(footprint(c.bounds));return outline?<path key={c.id} data-pick role="button" tabIndex={lens==='models'?0:-1} aria-label={`Locate ${c.title}`} aria-pressed={model?.id===c.id&&lens==='models'} onClick={()=>{setLens('models');focusModel(c);}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setLens('models');focusModel(c);}}} d={outline} fill={c.id===model?.id?'#8fe2d1':'#97b5c3'} fillOpacity={lens==='models'&&c.id===model?.id?'.24':'.05'} stroke={c.id===model?.id?'#a8f4df':'#6c969f'} strokeWidth={c.id===model?.id?2:1} />:null;})}
            {lens==='models'&&areaLabels.map(item=>{const position=caseCenter(item.model);if(view==='globe'&&geoDistance(center,position)>1.4)return null;const point=projection(position);return point&&<g key={item.model.region_id} data-pick role="button" tabIndex={0} aria-label={`Find ${item.name} data`} transform={`translate(${point[0]},${point[1]})`} onClick={()=>focusModel(item.model)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focusModel(item.model);}}}><circle r="15" fill="#0a202a" fillOpacity=".3"/><circle r="4" fill="#bcffea"/><text textAnchor="middle" y="-23" fill="#e0f8f2" stroke="#09202c" strokeWidth="3" paintOrder="stroke" fontSize="15">{item.name}</text></g>;})}
            {lens!=='models'&&observations.map(p=>{if(view==='globe'&&geoDistance(center,p.position)>Math.PI/2-.02)return null;const point=projection(p.position);return point&&<g key={p.profile.id} data-pick role="button" tabIndex={0} aria-label={`Locate ${kind[p.profile.instrument]} ${p.profile.platform}, ${p.time}`} aria-pressed={p.profile.id===selected?.profile.id} onClick={()=>focusProfile(p)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();focusProfile(p);}}} transform={`translate(${point[0]},${point[1]})`}><circle r="12" fill="transparent"/><circle r={p.profile.id===selected?.profile.id?8:4} fill={lens==='chlorophyll'?'#bbdf9a':'#ffd09e'} stroke="#0d2632" strokeWidth="2"/>{p.profile.id===selected?.profile.id&&<circle r="13" fill="none" stroke={lens==='chlorophyll'?'#bbdf9a':'#ffd09e'} strokeWidth="1.3"/>}</g>;})}
          </g>
        </svg>
        <div className="globe-navigation" aria-label="Globe navigation"><button className="icon-button" aria-label="Rotate globe west" onClick={()=>setCenter(([lon,lat])=>[normalizedLongitude(lon-30),lat])}><ChevronLeft size={18}/></button><button className="icon-button" aria-label="Rotate globe east" onClick={()=>setCenter(([lon,lat])=>[normalizedLongitude(lon+30),lat])}><ChevronRight size={18}/></button><button className="icon-button" aria-label="Zoom data globe in" disabled={zoom>=1.8} onClick={()=>setZoom(z=>Math.min(1.8,z+.2))}><Plus size={18}/></button><button className="icon-button" aria-label="Zoom data globe out" disabled={zoom<=.8} onClick={()=>setZoom(z=>Math.max(.8,z-.2))}><Minus size={18}/></button><button className="icon-button" aria-label="Reset data globe" onClick={()=>{setZoom(1);setCenter(lens==='models'&&model?caseCenter(model):selected?.position??[80,12]);}}><RotateCcw size={17}/></button></div>
        <p className="globe-legend"><span className="globe-area-key"/> Model extent{lens!=='models'&&<><span className={`globe-dot-key ${lens}`}/> Measured location</>}</p><p className="globe-caption">Drag to rotate. Outlines mark available model areas, not ocean-wide coverage.<br/>Natural Earth coastlines, 1:110m. Historical datasets.</p>
      </div>
      <div className="globe-detail" aria-label="Located data details">
        {lens==='models'&&model?<><label>Available model case<select aria-label="Globe model case" value={model.id} onChange={e=>focusModel(catalog.cases.find(c=>c.id===e.target.value)!)}>{catalog.cases.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}</select></label><span className="eyebrow">MODEL DOMAIN</span><h3>{model.title}</h3><p>{model.source_label}</p><dl><div><dt>Data dates</dt><dd>{date(model.time_start)}<br/>{date(model.time_end)}</dd></div><div><dt>Water column</dt><dd>{model.depth_range_m[0].toLocaleString()} to {model.depth_range_m[1].toLocaleString()} m</dd></div><div><dt>Fields</dt><dd>{model.variables.map(v=>({temperature:'Temperature',salinity:'Salinity',eastward_velocity:'Eastward current',northward_velocity:'Northward current'})[v]).join(', ')}</dd></div></dl><button className="primary-button" onClick={()=>onModel(model.id)}>Open this 3D ocean <ArrowRight size={17}/></button><p className="globe-note">The outline is the grid extent. Land, seabed and missing cells stay masked in the scientific view.</p></>:<>
          {lens==='chlorophyll'&&<div className="globe-chlorophyll"><span className="eyebrow">MEASURED CHLOROPHYLL</span><h3>Find readings, then look below</h3><p>Dots locate source profiles containing chlorophyll. They do not map bloom extent or regional concentration.</p>{!example&&!imports.some(p=>p.source_file==='SR1902594_034.nc')&&<button className="secondary-button" disabled={loading||!instruments} onClick={()=>void loadExample()}>{loading?<><LoaderCircle className="spin" size={16}/>Reading public BGC source...</>:'Load public chlorophyll profile'}</button>}{loading&&<button className="context-button" onClick={()=>controller.current?.abort()}>Cancel source loading</button>}</div>}
          <p className="globe-note">Source profiles from the available cases and this tab's imports. Each record keeps its own date.</p>
          {libraries.some(q=>q.isFetching)&&<p role="status">Checking other case libraries...</p>}
          {libraries.some(q=>q.isError)&&<p role="alert">Some case locations could not load. Visible records are retained. <button className="context-button" onClick={()=>libraries.filter(q=>q.isError).forEach(q=>void q.refetch())}>Retry missing locations</button></p>}
          {!instruments&&!instrumentError&&<p role="status">Loading original instrument locations...</p>}{instrumentError&&<p role="alert">{instrumentError.message}<button onClick={retryInstruments}>Retry locations</button></p>}
          {selected?<><label>Available observation<select aria-label="Globe observation" value={selected.profile.id} onChange={e=>focusProfile(observations.find(p=>p.profile.id===e.target.value)!)}>{observations.map(p=><option key={p.profile.id} value={p.profile.id}>{kind[p.profile.instrument]} {p.profile.platform} | {p.time.slice(0,10)}</option>)}</select></label><h3>{kind[selected.profile.instrument]} {selected.profile.platform}</h3><dl><div><dt>Observed</dt><dd>{date(selected.time)}</dd></div><div><dt>Position</dt><dd>{latitudeLabel(selected.position[1],4)}, {longitudeLabel(selected.position[0],4)}</dd></div><div><dt>Measured variables</dt><dd>{Object.values(selected.profile.parameters).map(p=>p.label).join(', ')}</dd></div></dl><p className="globe-context">{contexts.length?`${contexts[0].model.title}: ${contexts[0].timeOverlap?'area and timestamp overlap':'area overlaps; timestamp differs'}. Matching rules still decide numerical comparisons.`:'No loaded model case covers this marker. You can still inspect the original profile.'}</p><button className="primary-button" onClick={openProfile}>Open measured profile <ArrowRight size={17}/></button>{safeSource(selected.profile.source_url)&&<a href={safeSource(selected.profile.source_url)} target="_blank" rel="noreferrer">Original observation source</a>}<details><summary>What does this location mean?</summary><p>{selected.positionMeaning}</p><p>Profiles and model outlines can have different dates. A dot is not a confidence score. Chlorophyll has no matching model field in these cases.</p></details></>:<p role="status">{lens==='chlorophyll'?'No chlorophyll profiles loaded yet. Load the public example or import your supported BGC file.':'No located observations are available.'}</p>}
        </>}
        {error&&<p role="alert" className="globe-error">{error}</p>}
        <PublicationStatus expanded={publicationOpen} requestId={publicationRequest} onChecked={setPublication} onError={setPublicationError}/>
        <div className="globe-next"><Globe2 size={18}/><div><strong>Looking outside these cases?</strong><button className="learn-text-button" onClick={onWider}>Explore wider source regions <ArrowRight size={15}/></button></div></div>
      </div>
    </div>
  </section>;
}
