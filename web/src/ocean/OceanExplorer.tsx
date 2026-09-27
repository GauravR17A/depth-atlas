import { longitudeLabel, latitudeLabel, longitudeOnAxis } from '../geography';
import { useLearningTool, modelSource } from '../learning/bridge';
import type { OceanRecipe,SaveDraft } from '../investigations/contracts';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Pause, Play, RotateCcw, ChevronLeft, ChevronRight, Minus, Plus, SlidersHorizontal, Box, Layers3, Slice, Waves, Info } from 'lucide-react';
import { type CaseManifest } from '../contracts';
import { fieldOptions, profileOptions, type FieldData } from './data';
import { variables, type Variable } from '../store';
import { utcLabel,caseTimeLabel } from '../CaseInspector';
import { BasicView } from './BasicView';
import { nearest, palettes, rangeError, depthWindow, coverage, type Paint, type Palette, type Point, type ViewMode } from './grid';
import type { OceanScene, SceneOptions } from './scene';
import './ocean.css';
import type { Measurement } from '../instruments/contracts';
import type { LocatedInstrument } from '../instruments/context';
import type { MatchRow } from '../evidence/contracts';

const modes:Record<ViewMode,string>={volume:'Volume',slice:'Depth slice',section:'Section',iso:'Isosurface',currents:'Current vectors'};
const defaults:Record<Variable,{min:number;max:number;iso:number}>={temperature:{min:0,max:30,iso:20},salinity:{min:30,max:36,iso:34},currents:{min:0,max:1,iso:.2},horizontal_kinetic_energy:{min:0,max:.3,iso:.08}};
type DisplayFrame = FieldData & { variable: Variable; time: number; mode: ViewMode; paint: Paint; iso: number };
export function OceanExplorer({manifest,variable,onVariable,time,onTime:setTime,active=true,prefetch=true,instruments,revealInstruments=0,onInstrument,linkedSample,linkedComparison,restore,onSave,onNativeSelection}:{onNativeSelection?:()=>void;manifest:CaseManifest;variable:Variable;onVariable:(value:Variable)=>void;time:number;onTime:(time:number)=>void;active?:boolean;prefetch?:boolean;instruments?:LocatedInstrument[];revealInstruments?:number;onInstrument?:(id?:string)=>void;linkedSample?:{sample:Measurement;key:number};linkedComparison?:{row:MatchRow;key:number};restore?:OceanRecipe;onSave?:(draft:SaveDraft)=>void}){
  const caseDefaults=useMemo(()=>{
    const result={...defaults};
    for(const key of ['temperature','salinity'] as const){const range=manifest.representations?.display?.variable_ranges?.[key];if(range&&Number.isFinite(range.min)&&Number.isFinite(range.max)&&range.min<range.max)result[key]={...range,iso:(range.min+range.max)/2};}
    return result;
  },[manifest]);
  const monthlyCase=manifest.representations?.temporal_support?.kind==='calendar_month_mean',defaultExaggeration=monthlyCase?6000:200;
  const initialDepth=Math.min(19,manifest.coordinates.depth_m.length-1),initialSection=Math.min(19,manifest.display_coordinates.latitude.length-1);
  const supportsCurrents=manifest.case.variables.includes('eastward_velocity')&&manifest.case.variables.includes('northward_velocity');
  const [showInstruments,setShowInstruments]=useState(restore?.show_instruments??false);
  useEffect(()=>{if(revealInstruments)setShowInstruments(true);},[revealInstruments]);
  const [linkNotice,setLinkNotice]=useState('');
  const observationMarkers=useMemo(()=>showInstruments?(instruments??[]).map(p=>({id:p.id,label:`${p.imported?'Imported: ':''}${p.title}, ${p.marker.time?utcLabel(p.marker.time):'track location; open profile for sample time'}`,position:[longitudeOnAxis(p.marker.longitude,manifest.coordinates.longitude),p.marker.latitude,0] as Point})):[],[showInstruments,instruments,manifest]);
  const [mode,setMode]=useState<ViewMode>(restore?.view??'volume'),[depth,setDepth]=useState(restore?.depth_index??initialDepth),[section,setSection]=useState(restore?.section_index??initialSection);
  const [paint,setPaint]=useState<Paint>(restore?.paint??{...caseDefaults[variable],log:false,palette:'thermal',opacity:1}),[iso,setIso]=useState(restore?.iso??caseDefaults[variable].iso),[exaggeration,setExaggeration]=useState(restore?.exaggeration??defaultExaggeration);
  const [windowDepth,setWindowDepth]=useState<number>(restore?.window_depth??1000),[cutaway,setCutaway]=useState(restore?.cutaway??false);
  const [quality,setQuality]=useState<'auto'|'balanced'|'basic'>(restore?.quality??'auto'),[failure,setFailure]=useState(''),[retry,setRetry]=useState(0),[playing,setPlaying]=useState(false);
  const [reducedMotion,setReducedMotion]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [point,setPoint]=useState<[number,number,number]>(()=>restore?.point??[Math.floor(manifest.coordinates.longitude.length/2),Math.floor(manifest.coordinates.latitude.length/2),initialDepth]);
  const [geometryCount,setGeometryCount]=useState<number|null>(null),[renderReady,setRenderReady]=useState(false);
  const host=useRef<HTMLDivElement>(null),engine=useRef<OceanScene|null>(null),optionsRef=useRef<SceneOptions|null>(null);
  const isCurrent=variable==='currents';
  const client=useQueryClient();
  const [paintOwner,setPaintOwner]=useState(variable);
  const [lastFrame,setLastFrame]=useState<DisplayFrame|null>(null);
  const query=useQuery({...fieldOptions(manifest,variable,time),enabled:active});
  const pending=query.isPending, dataError=query.error;
  const basic=quality==='basic'||Boolean(failure);
  const rangeProblem=paintOwner===variable?rangeError(paint):null;
  const validPaint=useMemo(()=>paintOwner!==variable||rangeProblem?{...paint,min:caseDefaults[variable].min,max:caseDefaults[variable].max,log:false}:paint,[paintOwner,variable,rangeProblem,paint,caseDefaults]);
  const readyFrame=useMemo<DisplayFrame|null>(()=>query.data&&!dataError?{...query.data,variable,time,mode,paint:validPaint,iso:paintOwner===variable?iso:caseDefaults[variable].iso}:null,[query.data,dataError,variable,time,mode,validPaint,iso,paintOwner,caseDefaults]);
  useEffect(()=>{if(readyFrame)setLastFrame(readyFrame);},[readyFrame]);
  const frame=readyFrame??lastFrame;
  const data=frame?.data??null;
  const windowed=useMemo(()=>data?depthWindow(data,windowDepth):null,[data,windowDepth]);
  const dataCoverage=useMemo(()=>data?coverage(data):null,[data]);
  const shownVariable=frame?.variable??variable,shownMode=frame?.mode??mode,shownTime=frame?.time??time;
  const shownPaint=frame?.paint??validPaint;
  const sample=useQuery({...profileOptions(manifest,variable,time,point,query.data?.data.manifest_sha256),enabled:active&&!pending&&!dataError});
  // Warm only the next time step, after the visible field and native reading.
  // Other variables are fetched on demand. Stop unused work on a tool/selection
  // change, but preserve a prefetched query if the user has now selected it.
  useEffect(()=>{
    const connection=(navigator as Navigator & {connection?:{saveData?:boolean;effectiveType?:string}}).connection;
    if(!active||!prefetch||!readyFrame||!sample.data||sample.isFetching||time+1>=manifest.coordinates.times.length||document.hidden||connection?.saveData||['slow-2g','2g'].includes(connection?.effectiveType??''))return;
    const options=fieldOptions(manifest,variable,time+1);
    const timer=setTimeout(()=>{void client.prefetchQuery({...options,retry:false});},playing?200:1200);
    return()=>{
      clearTimeout(timer);
      queueMicrotask(()=>{
        const query=client.getQueryCache().find({queryKey:options.queryKey,exact:true});
        if(query?.getObserversCount()===0)void client.cancelQueries({queryKey:options.queryKey,exact:true});
      });
    };
  },[client,manifest,variable,time,Boolean(readyFrame),active,prefetch,Boolean(sample.data),sample.isFetching,playing]);
  const picked=useMemo(()=>[manifest.coordinates.longitude[point[0]],manifest.coordinates.latitude[point[1]],manifest.coordinates.depth_m[point[2]]] as Point,[manifest,point]);
  const nativeListener=useRef(onNativeSelection);nativeListener.current=onNativeSelection;
  const pick=useCallback((p:Point)=>{
    setLinkNotice('Model selection changed. The observation keeps its source depth and position. Select a source sample to relink it.');nativeListener.current?.();
    const z=nearest(manifest.coordinates.depth_m,p[2]);
    setPoint([nearest(manifest.coordinates.longitude,p[0]),nearest(manifest.coordinates.latitude,p[1]),z]);setDepth(z);
  },[manifest]);
  const previousVariable=useRef(variable);
  useEffect(()=>{if(restore&&previousVariable.current===variable)return;previousVariable.current=variable;setPaintOwner(variable);setPaint(p=>({...p,min:caseDefaults[variable].min,max:caseDefaults[variable].max,log:false}));setIso(caseDefaults[variable].iso);if(isCurrent)setMode('currents');else setMode(m=>m==='currents'?'volume':m);setPlaying(false);},[variable,isCurrent,caseDefaults]);
  useEffect(()=>{const mq=matchMedia('(prefers-reduced-motion: reduce)');const change=()=>{setReducedMotion(mq.matches);if(mq.matches)setPlaying(false);};mq.addEventListener('change',change);return()=>mq.removeEventListener('change',change);},[]);
  useEffect(()=>{if(!playing||pending)return;if(dataError||time===manifest.coordinates.times.length-1){setPlaying(false);return;}const timer=setTimeout(()=>setTime(time+1),1200);return()=>clearTimeout(timer);},[playing,pending,dataError,time,manifest,setTime]);
  useEffect(()=>{if(data&&section>=data.latitude.length)setSection(Math.floor(data.latitude.length/2));},[data,section]);
  const available=Boolean(frame);
  useEffect(()=>{
    if(basic||!available||!host.current)return;
    let cancelled=false;setRenderReady(false);
    import('./scene').then(({OceanScene})=>{
      if(cancelled||!host.current)return;
      try{engine.current=new OceanScene(host.current,pick,reason=>{setFailure(reason);setPlaying(false);},stats=>{setGeometryCount(stats.vertices);setRenderReady(true);});if(optionsRef.current)engine.current.update(optionsRef.current);}
      catch(error){setFailure(error instanceof Error?error.message:'3D is unavailable. Basic view is available.');}
    }).catch(()=>setFailure('The 3D renderer could not be loaded. Basic view is available.'));
    return()=>{cancelled=true;engine.current?.dispose();engine.current=null;};
  },[basic,available,retry,pick]);
  const sceneOptions=useMemo<SceneOptions|null>(()=>windowed&&frame?{data:windowed,east:frame.east,north:frame.north,mode:shownMode,paint:shownPaint,depthIndex:Math.min(depth,windowed.depth_m.length-1),sectionIndex:Math.min(section,windowed.latitude.length-1),iso:frame.iso,exaggeration,quality:quality==='basic'?'auto':quality,probe:picked,cutaway,reducedMotion,active,pickEnabled:!pending&&!dataError}:null,[windowed,cutaway,frame?.east,frame?.north,shownMode,shownPaint,depth,section,frame?.iso,exaggeration,quality,picked,reducedMotion,active,pending,dataError]);
  useEffect(()=>{if(!sceneOptions)return;const options={...sceneOptions,observations:observationMarkers,onInstrument};optionsRef.current=options;try{engine.current?.update(options);}catch(error){setFailure(error instanceof Error?error.message:'The view could not be drawn. Basic view is available.');}},[sceneOptions,observationMarkers,onInstrument]);
  const unit=shownVariable==='currents'?'m/s':shownVariable==='horizontal_kinetic_energy'?'m²/s²':manifest.variables.find(v=>v.id===shownVariable)!.units;
  const sampleData=sample.data?.data;
  const probeMissing=sampleData?.values[point[2]]===null;
  const probeLoading=!dataError&&(pending||sample.isPending);
  const probeError=sample.error;
  const probeValue=sampleData?.values[point[2]];
  useEffect(()=>{if(!active)setPlaying(false);},[active]);
  useEffect(()=>{
    if(!active||!windowed||reducedMotion)return;
    const animation=host.current?.animate([{opacity:.72},{opacity:1}],{duration:180,easing:'ease-out'});
    return()=>animation?.cancel();
  },[windowed,shownMode,reducedMotion,active]);
  const currentDepth=manifest.coordinates.depth_m[depth];
  const setView=(view:ViewMode)=>{setPlaying(false);if(view==='currents'){onVariable('currents');setMode(view);}else{if(isCurrent)onVariable('temperature');setMode(view);}};
  const changeDepth=(z:number)=>{
    setLinkNotice('');nativeListener.current?.();
    setDepth(z);setPoint(p=>[p[0],p[1],z]);
    if(manifest.coordinates.depth_m[z]>windowDepth){setWindowDepth(5000);setExaggeration(50);}
  };
  const changeWindow=(maximum:number)=>{
    setWindowDepth(maximum);setExaggeration(maximum===1000?defaultExaggeration:50);
    if(currentDepth>maximum){const z=nearest(manifest.coordinates.depth_m,maximum);setDepth(z);setPoint(p=>[p[0],p[1],z]);}
  };
  useEffect(()=>{
    if(!linkedSample||linkedSample.sample.depth_m===null)return;
    const p=linkedSample.sample,z=nearest(manifest.coordinates.depth_m,p.depth_m!);
    setDepth(z);setPoint([nearest(manifest.coordinates.longitude,longitudeOnAxis(p.longitude,manifest.coordinates.longitude)),nearest(manifest.coordinates.latitude,p.latitude),z]);setPlaying(false);
    if(manifest.coordinates.depth_m[z]>1000){setWindowDepth(5000);setExaggeration(50);}
    setLinkNotice(`Observation depth ${p.depth_m!.toFixed(2)} m linked to the nearest model level, ${manifest.coordinates.depth_m[z].toLocaleString()} m, and grid point. Observation time: ${utcLabel(p.time)}. The model retains its own timestamp; no comparison has been calculated.`);
  },[linkedSample,manifest]);
  useEffect(()=>{
    const row=linkedComparison?.row;
    if(!row?.accepted||row.depth_m===null||row.model_latitude===null||row.model_longitude===null)return;
    const z=nearest(manifest.coordinates.depth_m,row.depth_m);
    setDepth(z);setPoint([nearest(manifest.coordinates.longitude,row.model_longitude),nearest(manifest.coordinates.latitude,row.model_latitude),z]);setPlaying(false);
    if(manifest.coordinates.depth_m[z]>1000){setWindowDepth(5000);setExaggeration(50);}
    setLinkNotice(`Comparison depth: ${row.depth_m.toFixed(2)} m. Its model value was interpolated between ${row.lower_depth_m} and ${row.upper_depth_m} m. This probe shows the nearest native level, ${manifest.coordinates.depth_m[z]} m, at the same model column and selected timestamp.`);
  },[linkedComparison,manifest]);
  useEffect(()=>{setLinkNotice('');},[time,variable]);
  useEffect(()=>{if(!linkedSample&&!linkedComparison)setLinkNotice('');},[linkedSample,linkedComparison]);
  const quantity=shownVariable==='currents'?'Horizontal current speed':shownVariable==='horizontal_kinetic_energy'?'Horizontal kinetic energy':(monthlyCase?manifest.variables.find(item=>item.id===shownVariable)?.label??variables[shownVariable].label:variables[shownVariable].label);
  const requestedQuantity=isCurrent?'currents':variable;
  const icons={volume:Box,slice:Layers3,section:Slice,iso:Layers3,currents:Waves};
  const [moreViews,setMoreViews]=useState(false);
  const viewsMenu=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!moreViews)return;
    function closeOnEscape(event:KeyboardEvent){if(event.key==='Escape'){setMoreViews(false);viewsMenu.current?.querySelector('button')?.focus();}}
    function closeOutside(event:PointerEvent){if(event.target instanceof Node&&!viewsMenu.current?.contains(event.target))setMoreViews(false);}
    document.addEventListener('keydown',closeOnEscape);document.addEventListener('pointerdown',closeOutside);
    return ()=>{document.removeEventListener('keydown',closeOnEscape);document.removeEventListener('pointerdown',closeOutside);};
  },[moreViews]);
  const instructions=shownMode==='volume'?(basic?'The vertical section shows how values change with depth.':cutaway?'The opening reveals depth layers, not missing water. Click a coloured face to inspect it.':'Open the cutaway to see depth layers. Click a face to inspect a source value.'):
    shownMode==='slice'?'Each colour shows the value at the selected depth. Change depth to explore another layer.':
    shownMode==='section'?'Read from the surface downwards. Click the section to inspect a location and depth.':
    shownMode==='iso'?(basic?'Basic shows a vertical section. Choose Balanced 3D to view an equal-value surface.':`This surface connects locations with the same value: ${frame?.iso??iso} ${unit}. Change the threshold to explore.`):
    'Equal-length arrows show horizontal direction. Colour shows speed; these are not particle paths.';
  const fieldLegend=shownVariable==='temperature'?['Cooler','Warmer']:shownVariable==='salinity'?['Less saline','More saline']:shownVariable==='horizontal_kinetic_energy'?['Lower energy','Higher energy']:['Slower','Faster'];
  const emptyDepths=dataCoverage?.empty.filter(d=>d<=windowDepth)??[];
  const settingsElement=useRef<HTMLDetailsElement>(null);
  const tutorialStop=useRef<number|null>(null);
  useEffect(()=>{if(playing&&tutorialStop.current!==null&&time>=tutorialStop.current){tutorialStop.current=null;setPlaying(false);}},[playing,time]);
  useLearningTool('ocean',active,{
    tool:'ocean',caseId:manifest.case.id,status:dataError||probeError?'error':probeLoading||playing&&tutorialStop.current!==null?'loading':probeValue===undefined?'empty':'ready',
    title:quantity,kind:shownVariable==='horizontal_kinetic_energy'?'derived':'model',
    facts:[{label:'Selected native value',value:probeValue??null,unit},{label:'Depth',value:picked[2],unit:'m'},{label:'Model time (UTC)',value:manifest.coordinates.times[time]},{label:'Longitude',value:picked[0],unit:'degrees east'},{label:'Latitude',value:picked[1],unit:'degrees north'}],
    parameters:{variable,time_index:time,depth_m:picked[2],view:mode,cutaway,palette:paint.palette,opacity:paint.opacity,exaggeration,show_instruments:showInstruments,graphics:basic?'basic':'3d'},
    sources:[modelSource(manifest.case.id),...(sampleData?(variable==='currents'?['eastward_velocity','northward_velocity']:[variable]).map(v=>({label:`Native ${v.replaceAll('_',' ')} values`,href:`/api/cases/${encodeURIComponent(manifest.case.id)}/subset?variable=${v}&time_index=${time}&representation=analytical&operation=volume&west=${picked[0]}&east=${picked[0]}&south=${picked[1]}&north=${picked[1]}`})):[])],
    limits:[monthlyCase?'Monthly potential temperature is an average, not an instantaneous measurement.':'Historical model estimate, not a live measurement or a forecast.',probeMissing?'This source sample is missing. It is not zero.':'Colours encode the selected variable, not the natural colour of seawater.',`Depth is stretched ${exaggeration} times for visibility. Values do not change.`],message:(dataError??probeError)?.message,
  },(command,signal)=>{
    if(pending)return false;
    if(dataError)void query.refetch();
    if(probeError)void sample.refetch();
    setPlaying(false);
    if(command.action==='overview'){onVariable('temperature');setView('volume');setCutaway(false);setTime(0);setShowInstruments(false);}
    else if(command.action==='cutaway'){setView('volume');setCutaway(true);}
    else if(command.action==='depth'){const value=Number(command.value??100);const index=manifest.coordinates.depth_m.indexOf(value);if(index<0)throw new Error('That exact depth is not supplied by this case. Choose an available native depth.');changeDepth(index);}
    else if(command.action==='query_depth'){
      const [v,z]=String(command.value).split(':');const index=manifest.coordinates.depth_m.indexOf(Number(z));
      if(!['temperature','salinity'].includes(v)||!manifest.case.variables.includes(v as 'temperature'|'salinity')||index<0)throw new Error('That variable or exact depth is unavailable in this case.');
      setView('slice');onVariable(v as Variable);changeDepth(index);
    }
    else if(command.action==='slice')setView('slice');
    else if(command.action==='section')setView('section');
    else if(command.action==='time'){const index=Number(command.value??1);if(!Number.isInteger(index)||!manifest.coordinates.times[index])throw new Error('This model timestamp is unavailable.');setTime(index);}
    else if(command.action==='play_once'){
      if(reducedMotion){setTime(Math.min(1,manifest.coordinates.times.length-1));return true;}
      setTime(0);tutorialStop.current=Math.min(2,manifest.coordinates.times.length-1);setPlaying(true);
      signal.addEventListener('abort',()=>{tutorialStop.current=null;setPlaying(false);},{once:true});
    }
    else if(command.action==='salinity'){if(!manifest.case.variables.includes('salinity'))throw new Error('This case does not supply salinity.');onVariable('salinity');}
    else if(command.action==='currents'){if(!supportsCurrents)throw new Error('This case does not supply current vectors.');setView('currents');}
    else if(command.action==='iso'){onVariable('temperature');setView('iso');setIso(20);}
    else if(command.action==='display'){setView('volume');setCutaway(true);setPaint(p=>({...p,palette:'mono',opacity:.75}));setExaggeration(500);if(settingsElement.current)settingsElement.current.open=true;}
    else if(command.action==='overlay'){onVariable('temperature');setView('volume');setCutaway(false);setShowInstruments(true);if(settingsElement.current)settingsElement.current.open=false;}
    else if(command.action==='sources'){setView('volume');setCutaway(true);}
    else if(command.action==='save'){
      if(!readyFrame||sample.isFetching||!sample.data)return false;
      if(rangeProblem)throw new Error('Correct the colour range before saving this view.');
      if(!onSave)throw new Error('Saving is unavailable in this workspace.');
      onSave({expected_model_sha256:query.data!.data.manifest_sha256,recipe:{mode:'ocean',case_id:manifest.case.id,variable,time_index:time,view:mode,depth_index:depth,section_index:section,point,paint:{min:paint.min,max:paint.max,log:paint.log,palette:paint.palette,opacity:paint.opacity},iso,exaggeration,window_depth:windowDepth as 1000|5000,cutaway,quality,show_instruments:showInstruments}});
    }
    else if(command.action==='inspect'){}
    else throw new Error('This ocean action is not supported.');
    return true;
  });
  return <section className="ocean-explorer" aria-label="Scientific ocean explorer">
    <div className="ocean-heading">
      <div><span className="eyebrow">{manifest.case.region_id.replaceAll('-',' ').toUpperCase()} / HISTORICAL MODEL</span><h2>{quantity} beneath the surface</h2><p>{manifest.case.source_label} <span aria-hidden="true">·</span> {caseTimeLabel(manifest,manifest.coordinates.times[shownTime])}</p></div>
      <div className="ocean-heading-actions"><span className="ocean-render-status" role="status">{pending?(frame?'Updating field':'Loading field'):dataError?'Field unavailable':basic?'Basic 2D':renderReady?'Interactive 3D':'Preparing 3D'}</span><button className="ocean-start" onClick={()=>{onVariable('temperature');setMode('volume');setCutaway(false);changeWindow(1000);changeDepth(initialDepth);setPaint({...caseDefaults.temperature,log:false,palette:'thermal',opacity:1});setTime(0);setPlaying(false);setSection(initialSection);setPoint([Math.floor(manifest.coordinates.longitude.length/2),Math.floor(manifest.coordinates.latitude.length/2),initialDepth]);engine.current?.reset();}}>Reset exploration <RotateCcw size={14}/></button>{onSave&&<div className="save-analysis"><button className="secondary-button" disabled={!readyFrame||sample.isFetching||!sample.data||Boolean(rangeProblem)} onClick={()=>onSave({expected_model_sha256:query.data!.data.manifest_sha256,recipe:{mode:"ocean",case_id:manifest.case.id,variable,time_index:time,view:mode,depth_index:depth,section_index:section,point,paint:{min:paint.min,max:paint.max,log:paint.log,palette:paint.palette,opacity:paint.opacity},iso,exaggeration,window_depth:windowDepth as 1000|5000,cutaway,quality,show_instruments:showInstruments}})}>Save investigation</button></div>}</div>
    </div>
    {manifest.representations?.temporal_support?.kind==='calendar_month_mean'&&<p className="case-availability-note">{manifest.variables.find(item=>item.id===variable)?.definition} Source timestamps identify monthly mean fields, not instantaneous conditions.</p>}

    <div className="ocean-view-tabs" aria-label="Scientific view">{(['volume','slice','section'] as ViewMode[]).map(id=>{
      const Icon=icons[id];return <button key={id} aria-label={modes[id]} aria-pressed={mode===id} onClick={()=>{setView(id);setMoreViews(false);}}><Icon size={17}/><span>{id==='volume'?'3D volume':modes[id]}</span></button>;
    })}<div className="more-views" ref={viewsMenu}><button aria-label="More views" aria-expanded={moreViews} aria-controls={moreViews?'extra-ocean-views':undefined} aria-pressed={mode==='iso'||mode==='currents'} onClick={()=>setMoreViews(v=>!v)}>{mode==='iso'||mode==='currents'?modes[mode]:'More views'}<ChevronRight size={14}/></button>{moreViews&&<div className="extra-views" id="extra-ocean-views">{(['iso',...(supportsCurrents?['currents']:[])] as ViewMode[]).map(id=><button key={id} aria-label={modes[id]} onClick={()=>{setView(id);setMoreViews(false);viewsMenu.current?.querySelector('button')?.focus();}}>{modes[id]}<small>{id==='iso'?'Water with the same value':'Direction and speed'}</small></button>)}</div>}</div></div>
    <div className="ocean-instruction"><Info size={16}/><p>{instructions}</p><span>{reducedMotion?'Manual time selection':monthlyCase?`${manifest.case.time_count} monthly means`:`${manifest.case.time_count} snapshots · 12 h apart`}</span></div>
    {shownVariable==='horizontal_kinetic_energy'&&<p className="ocean-notice">Derived field: (u² + v²) / 2, in m²/s². Energy per unit mass from horizontal flow only. This excludes vertical velocity and is not eddy kinetic energy.</p>}
    {failure&&<div className="ocean-notice" role="status">{failure} <button onClick={()=>{setFailure('');setRetry(n=>n+1);}}>Retry 3D</button></div>}
    {rangeProblem&&<p className="ocean-notice" role="alert">{rangeProblem} Showing the default linear range until corrected.</p>}
    {linkNotice&&<p aria-label="Linked model depth" className="ocean-notice" role="status">{linkNotice}</p>}

    <div className="ocean-stage">
      <div className="ocean-canvas-column">
        <div className="ocean-scene-toolbar"><span>{manifest.coordinates.depth_m[0]===0?"Surface":`${manifest.coordinates.depth_m[0]} m`} to {Math.min(windowDepth,manifest.coordinates.depth_m.at(-1)!).toLocaleString()} m</span><div className="ocean-scene-actions">{shownMode==='volume'&&!basic&&<button className="cutaway-toggle" aria-label="Cutaway" aria-pressed={cutaway} onClick={()=>setCutaway(v=>!v)}><Slice size={16}/>{cutaway?'Close cutaway':'Open cutaway'}</button>}<div className="ocean-camera"><button title="Rotate left" aria-label="Rotate ocean left" disabled={basic} onClick={()=>engine.current?.rotate(-1)}><ChevronLeft size={17}/></button><button title="Rotate right" aria-label="Rotate ocean right" disabled={basic} onClick={()=>engine.current?.rotate(1)}><ChevronRight size={17}/></button><button title="Zoom in" aria-label="Zoom ocean in" disabled={basic} onClick={()=>engine.current?.zoom(.85)}><Plus size={17}/></button><button title="Zoom out" aria-label="Zoom ocean out" disabled={basic} onClick={()=>engine.current?.zoom(1.15)}><Minus size={17}/></button><button title="Reset camera" aria-label="Reset ocean camera" disabled={basic} onClick={()=>engine.current?.reset()}><RotateCcw size={17}/></button></div></div></div>
        <div className={`ocean-viewport ${pending||dataError?'is-updating':''}`} aria-busy={pending} data-shown-variable={shownVariable} data-shown-time={manifest.coordinates.times[shownTime]}>
          <div className={`ocean-webgl ${basic||!frame?'ocean-hidden':''}`} ref={host}/>
          {basic&&windowed&&<BasicView data={windowed} east={frame?.east} north={frame?.north} mode={shownMode} depthIndex={Math.min(depth,windowed.depth_m.length-1)} sectionIndex={Math.min(section,windowed.latitude.length-1)} paint={shownPaint} onPick={pick}/>}
          {frame&&(pending||dataError)&&<div className={`ocean-update ${dataError?'update-error':''}`} role={dataError?'alert':'status'}><span className="update-track" aria-hidden="true"/><strong>{dataError?'Could not load selection':`Preparing ${requestedQuantity}`}</strong><span>Showing {quantity.toLowerCase()} · {caseTimeLabel(manifest,manifest.coordinates.times[shownTime])}</span>{dataError&&<><span>{dataError.message}</span><button className="secondary-button" onClick={()=>void query.refetch()}>Retry ocean field</button></>}</div>}
          {pending&&!frame&&<div className="ocean-state" role="status"><span className="loading-line"/><strong>Loading the ocean field</strong><p>Reading the selected historical snapshot.</p></div>}
          {dataError&&!frame&&<div className="ocean-state" role="alert"><strong>Ocean field unavailable</strong><p>{dataError.message}</p><button className="secondary-button" onClick={()=>{void query.refetch();}}>Retry ocean field</button></div>}
          {data&&!pending&&!dataError&&!basic&&geometryCount===0&&mode!=='volume'&&<div className="ocean-empty-label">{mode==='iso'?'No isosurface at this value':'No valid cells at this depth'}<small>{mode==='iso'?'Try a value within the legend range.':'Choose a shallower depth to return to the data.'}</small></div>}
          <div className="ocean-scene-note">{basic?(mode==='volume'||mode==='iso'?'Basic view shows a vertical section.':'Physical coordinate axes.'):`Depth stretched ${exaggeration}× for visibility · drag to rotate`}</div>
        </div>
    <div className="ocean-primary-controls">
      <label>Depth shown<select aria-label="Depth window" value={windowDepth} onChange={e=>changeWindow(Number(e.target.value))}><option value="1000">{manifest.coordinates.depth_m.at(-1)!<=1000?`Available column · ${manifest.coordinates.depth_m.at(-1)!.toLocaleString()} m`:"Upper 1,000 m"}</option>{manifest.coordinates.depth_m.at(-1)!>1000&&<option value="5000">Full column · {manifest.coordinates.depth_m.at(-1)!.toLocaleString()} m</option>}</select></label>
      <label>{mode==='slice'||mode==='currents'?'Layer depth':'Inspection depth'}<select aria-label="Explorer depth" value={depth} onChange={e=>changeDepth(Number(e.target.value))}>{manifest.coordinates.depth_m.map((d,i)=><option key={d} value={i}>{d===0?'Surface · 0 m':`${d.toLocaleString()} m`}</option>)}</select></label>
      {mode==='section'&&data&&<label>Section latitude<select aria-label="Section latitude" value={section} onChange={e=>setSection(Number(e.target.value))}>{data.latitude.map((lat,i)=><option key={lat} value={i}>{lat.toFixed(2)}° N</option>)}</select></label>}
      {mode==='iso'&&<label>Equal-value surface ({unit})<input aria-label="Isosurface value" disabled={basic} type="number" step="0.1" value={iso} onChange={e=>{const value=e.target.valueAsNumber;if(Number.isFinite(value))setIso(value);}}/></label>}
      <div className="ocean-time"><button aria-label={playing?'Pause ocean playback':'Play ocean playback'} title={playing?'Pause':'Play available times'} disabled={pending||Boolean(dataError)||reducedMotion} onClick={()=>{if(!playing&&time===manifest.coordinates.times.length-1)setTime(0);setPlaying(p=>!p);}}>{playing?<Pause size={18}/>:<Play size={18}/>}</button><label>{monthlyCase?"Calendar month":"Time · UTC"}<select aria-label="Ocean timestamp" value={time} onChange={e=>{setPlaying(false);setTime(Number(e.target.value));}}>{manifest.coordinates.times.map((t,i)=><option key={t} value={i}>{caseTimeLabel(manifest,t)}</option>)}</select></label></div>
    </div>
        <div className="ocean-coverage"><span className="missing-swatch"/><p>{emptyDepths.length?`No model samples at ${emptyDepths.map(d=>d.toLocaleString()).join(' or ')} m. Hatched areas have missing data.`:'Hatching marks missing samples. It never means colder water.'}</p></div>
      </div>
      <aside className="ocean-reading" aria-label="Read the scientific view">
        <div className="ocean-legend"><span className="eyebrow">COLOUR KEY</span><h3>{quantity} <span>{unit}</span></h3><div className="legend-scale"><div style={{background:`linear-gradient(to right, ${palettes[shownPaint.palette].join(',')})`}}/><div className="legend-ticks"><span>{shownPaint.min}</span><span>{shownPaint.log?'Log scale':'Linear scale'}</span><span>{shownPaint.max}</span></div></div><div className="legend-meaning"><span>{fieldLegend[0]}</span><span>{fieldLegend[1]}</span></div><p>Colours show values, not natural water colour.</p></div>
        <div className="ocean-probe"><span className="eyebrow">SELECTED SOURCE POINT</span><output className="probe-value" aria-live="polite" aria-label="Native model value">{probeLoading?'Loading value':dataError?'Waiting for field':probeError?'Value unavailable':probeMissing?'No value at this depth':probeValue!=null&&Number.isFinite(probeValue)?`${probeValue.toFixed(3)} ${unit}`:'No value'}<small>{picked[2].toLocaleString()} m below the surface</small>{isCurrent&&!pending&&sample.data?.east&&sample.data.north&&<small>East {sample.data.east.values[point[2]]?.toFixed(3)??'missing'} / North {sample.data.north.values[point[2]]?.toFixed(3)??'missing'} m/s</small>}{probeError&&<button onClick={()=>{void sample.refetch();}}>Retry value</button>}</output><p>{longitudeLabel(picked[0],3)} · {latitudeLabel(picked[1],3)}<br/>Original model grid, no interpolation.</p><details className="probe-location"><summary>Choose coordinates</summary><div className="probe-coordinates"><label>Longitude<select aria-label="Probe longitude" value={point[0]} onChange={e=>setPoint(p=>[Number(e.target.value),p[1],p[2]])}>{manifest.coordinates.longitude.map((x,i)=><option key={x} value={i}>{longitudeLabel(x,3)}</option>)}</select></label><label>Latitude<select aria-label="Probe latitude" value={point[1]} onChange={e=>setPoint(p=>[p[0],Number(e.target.value),p[2]])}>{manifest.coordinates.latitude.map((x,i)=><option key={x} value={i}>{latitudeLabel(x,3)}</option>)}</select></label></div></details></div>

      </aside>
    </div>

    {Boolean(instruments?.length)&&<div className="instrument-layer-control"><label><input type="checkbox" checked={showInstruments} onChange={e=>setShowInstruments(e.target.checked)} aria-label="Instrument locations" title="Hide locations to inspect the ocean field behind the markers."/> Instrument locations</label><span>{instruments!.length} profile locations · {instruments!.filter(p=>p.imported).length} imported. Dates differ.</span><button onClick={()=>onInstrument?.()}>Inspect observations</button>{basic&&showInstruments&&<div className="basic-instrument-list" aria-label="Instrument locations in Basic view">{instruments!.map(p=><button key={p.id} onClick={()=>onInstrument?.(p.id)}>{p.imported?'Imported: ':''}{p.title} · {latitudeLabel(p.marker.latitude,3)}, {longitudeLabel(p.marker.longitude,3)}</button>)}</div>}</div>}
    <details className="ocean-settings" ref={settingsElement}><summary><SlidersHorizontal size={15}/> Colour, depth and display settings</summary><div className="ocean-display-bar"><p>{basic?'2D keeps the same source values available.':`Depth is exaggerated ${exaggeration} times; values and units stay unchanged.`}</p><label>Graphics<select aria-label="Graphics quality" value={quality} onChange={e=>{setQuality(e.target.value as typeof quality);setFailure('');}}><option value="auto">Auto</option><option value="balanced">Balanced 3D</option><option value="basic">Basic 2D</option></select></label></div><div className="ocean-settings-grid">
      <label>Palette<select aria-label="Colour palette" value={paint.palette} onChange={e=>setPaint(p=>({...p,palette:e.target.value as Palette}))}><option value="thermal">Ocean thermal</option><option value="teal">Teal</option><option value="mono">Monochrome</option></select></label>
      <label>Minimum ({unit})<input aria-label="Colour minimum" type="number" step="0.1" value={Number.isFinite(paint.min)?paint.min:''} onChange={e=>setPaint(p=>({...p,min:e.target.valueAsNumber}))}/></label>
      <label>Maximum ({unit})<input aria-label="Colour maximum" type="number" step="0.1" value={Number.isFinite(paint.max)?paint.max:''} onChange={e=>setPaint(p=>({...p,max:e.target.valueAsNumber}))}/></label>
      <label>Scale<select aria-label="Colour scale" value={paint.log?'log':'linear'} onChange={e=>setPaint(p=>({...p,log:e.target.value==='log'}))}><option value="linear">Linear</option><option value="log">Logarithmic</option></select></label>
      <label>Layer opacity {Math.round(paint.opacity*100)}%<input aria-label="Layer opacity" type="range" min="0.05" max="1" step="0.05" value={paint.opacity} onChange={e=>setPaint(p=>({...p,opacity:Number(e.target.value)}))}/></label>
      <label>Vertical exaggeration {exaggeration}×<input aria-label="Vertical exaggeration" type="range" min="1" max={monthlyCase?12000:250} step="1" value={exaggeration} onChange={e=>setExaggeration(Number(e.target.value))} disabled={basic}/></label>
    </div><p>The upper-ocean view selects supplied levels up to 1,000 m, bounded by actual case coverage. Full column keeps all {manifest.coordinates.depth_m.length} supplied depth coordinates. The horizontal display grid is reduced; numerical inspection always reads the native analytical grid. A cutaway removes a quarter for visibility, not because water is missing there.</p><p>{isCurrent?'Arrows show horizontal velocity, not particle paths. Direction arrows have equal lengths: 0.35 scene units in 3D and 14 CSS pixels in Basic. Colour and inspected values give speed. ':''}Log scale hides non-positive values. Isosurfaces use a linear tetrahedral approximation. Cells with missing corners are excluded and cross-section gaps are hatched. Volume colours blend along the viewing ray. No temporal interpolation is applied.</p></details>
  </section>;
}
