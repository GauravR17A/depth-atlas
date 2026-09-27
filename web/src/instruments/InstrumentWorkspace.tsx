import { selectedOffset,type SharedSample } from '../workspace/selection';
import type { ImportSources, ImportedSource } from './imported';
import { longitudeLabel, latitudeLabel } from '../geography';
import { useLearningTool, modelSource } from '../learning/bridge';
import type { InstrumentRecipe,SaveDraft } from '../investigations/contracts';
import { useEffect,useMemo,useState,useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight,FileUp,MapPin,RefreshCw,Radio,ChevronLeft,ChevronRight } from 'lucide-react';
import { getApi,type CaseManifest } from '../contracts';
import { utcLabel } from '../CaseInspector';
import { parseInstrument,safeSource,type InstrumentCatalog,type InstrumentProfile,type Measurement } from './contracts';
import { InstrumentMap } from './InstrumentMap';
import { ProfileChart } from './ProfileChart';
import { ImportReviewPanel, useImportReview } from './ImportReview';
import { inModel, locateInstruments, overlapsModelTime } from './context';
export { inModel } from './context';
import './instruments.css';

const kind={argo:'Argo float',glider:'Glider',ctd:'Ship CTD',bgc:'BGC Argo'};
const value=(v:number|null|undefined,digits=3)=>v===null||v===undefined?'Missing':v.toLocaleString('en-US',{maximumFractionDigits:digits});
const sampleTime=(s:string)=>s.replace('T',' ').replace('Z',' UTC');


export function InstrumentWorkspace({catalog,catalogError,retryCatalog,selected,onSelect,imports,importSources,onImport,onClear,manifest,onDepth,onCompare,active,restore,onSave,modelTime,onClose,selection,onSampleSelection}:{selection?:SharedSample;onSampleSelection?:(profile:InstrumentProfile,sample:Measurement,variable:string)=>void;catalog?:InstrumentCatalog;catalogError?:Error|null;retryCatalog:()=>void;selected:string;onSelect:(id:string)=>void;imports:InstrumentProfile[];importSources:ImportSources;onImport:(profiles:InstrumentProfile[],source:ImportedSource)=>void;onClear:()=>void;manifest?:CaseManifest;onDepth:(sample:Measurement)=>void;onCompare:(id:string)=>void;active:boolean;restore?:InstrumentRecipe;modelTime?:string;onClose?:()=>void;onSave?:(draft:SaveDraft)=>void}){
  const profiles=useMemo(()=>{const map=new Map((catalog?.profiles??[]).map(p=>[p.id,p]));for(const p of imports)map.set(p.id,p);return [...map.values()];},[catalog,imports]);
  const current=profiles.find(p=>p.id===selected)??profiles.find(p=>inModel(manifest,p))??profiles[0];
  const local=imports.find(p=>p.id===current?.id);
  const query=useQuery({queryKey:['instrument',current?.id],queryFn:({signal})=>getApi(`/api/instruments/profiles/${encodeURIComponent(current!.id)}`,parseInstrument,signal),enabled:active&&Boolean(current)&&!local,staleTime:Infinity,gcTime:600000});
  const profile=local??query.data;
  const [variable,setVariable]=useState(restore?.variable??'temperature'),[index,setIndex]=useState(restore?.sample_index??0),[excluded,setExcluded]=useState(restore?.show_excluded??false),[uploadOpen,setUploadOpen]=useState(false);
  const importState=useImportReview(imports,onImport,onSelect,importSources);
  const {upload,uploading,uploadError,uploadMessage,setUploadError}=importState;
  const chosen=profile?.parameters[variable]?variable:profile?.parameters.chlorophyll?'chlorophyll':profile?.instrument==='bgc'&&profile.parameters.oxygen?'oxygen':Object.keys(profile?.parameters??{})[0]??'temperature';
  const restoredProfile=useRef(restore?.profile_id);
  useEffect(()=>{if(!profile)return;if(restoredProfile.current===profile.id)return;restoredProfile.current=undefined;setIndex(0);setExcluded(false);setVariable(profile?.parameters.chlorophyll?'chlorophyll':profile?.instrument==='bgc'&&profile.parameters.oxygen?'oxygen':'temperature');},[profile?.id]);
  const collection=current?.collection??'';
  const sameCollection=useMemo(()=>profiles.filter(p=>p.collection===collection),[profiles,collection]);
  const effectiveIndex=selectedOffset(selection,profile?.id,profile?.levels.map(l=>l.index)??[],index);
  useEffect(()=>{if(selection?.profileId===profile?.id&&profile?.parameters[selection!.variable])setVariable(selection!.variable);},[selection,profile?.id]);
  function chooseSample(i:number){setIndex(i);if(profile)onSampleSelection?.(profile,profile.levels[i],chosen);}
  const sample=profile?.levels[effectiveIndex],reading=sample?.readings[chosen];
  const parameter=profile?.parameters[chosen];
  const [reviewLesson,setReviewLesson]=useState(false);
  function saveProfile(){if(!profile||!manifest||!onSave)return false;onSave({...(local?{import_source:importSources[profile.id]}:{}),expected_profile_sha256:profile.source_sha256,recipe:{mode:'instrument',case_id:manifest.case.id,profile_id:profile.id,variable:chosen,sample_index:effectiveIndex,show_excluded:excluded,model_time_index:Math.max(0,manifest.coordinates.times.indexOf(modelTime??manifest.coordinates.times[0]))}});return true;}

  useLearningTool('instruments',active,{
    tool:'instruments',caseId:manifest?.case.id??'',status:uploadError||query.error||catalogError?'error':uploading||query.isFetching||!profile?'loading':'ready',title:local?'Imported source profile':'Instrument reading',kind:'observation',
    facts:reviewLesson?[{label:'Ready files',value:importState.queue.filter(e=>e.status==='ready').length},{label:'Reviewed source samples',value:importState.queue.reduce((n,e)=>n+(e.review?.result?.profiles.reduce((v,p)=>v+p.samples,0)??0),0)}]:[{label:'Reading',value:reading?.accepted?reading.value:null,unit:parameter?.units},{label:'Sample depth',value:sample?.depth_m??null,unit:'m'},{label:'Observation time (UTC)',value:sample?.time??null},{label:'Instrument',value:profile?.instrument??null},{label:'Source samples',value:profile?.samples??null},{label:'Quality',value:reading?.accepted?'Accepted':reading?.reason??'Unavailable'}],
    parameters:{profile_id:profile?.id??null,variable:chosen,source_sample:sample?.index??null,imported:Boolean(local),format:uploadMessage},
    sources:profile?[{label:'Original observation source',href:safeSource(profile.source_url)??'#'},...(!local?[{label:'Parsed readings and quality flags',href:`/api/instruments/profiles/${encodeURIComponent(profile.id)}`}]:[])]:manifest?[modelSource(manifest.case.id)]:[],
    limits:[profile?.qc_policy??'Source quality flags are retained.',inModel(manifest,profile??{latitude:NaN,longitude:NaN})?'A sensor reading has its own location and time. It is not automatically a valid model comparison.':'This observation is outside the current model area; no local model match is claimed.',...(local?['Imported observations stay in this tab until reload or clearing.']:[])],message:uploadError||query.error?.message||catalogError?.message,
  },async(command,signal)=>{
    if(!catalog){if(catalogError)retryCatalog();return false;}
    if(query.error)void query.refetch();
    setReviewLesson(['import_preview','import_batch'].includes(command.action));
    if(command.action==='save')return saveProfile();
    if(command.action==='profile'){
      const picked=catalog.profiles.find(p=>p.instrument==='argo'&&inModel(manifest,p))??catalog.profiles[0];
      if(!picked)throw new Error('No original observation is available for this lesson.');
      setUploadError('');onSelect(picked.id);setVariable('temperature');setIndex(0);setUploadOpen(false);return true;
    }
    if(command.action==='import_batch'){
      const examples=[catalog.examples.find(e=>e.name.endsWith('.csv')),catalog.examples.find(e=>e.name==='SR1902594_034.nc')];
      if(examples.some(e=>!e))throw new Error('The two public examples are unavailable.');setUploadOpen(true);
      const files:File[]=[];for(const example of examples){const r=await fetch(`/api/instruments/examples/${encodeURIComponent(example!.name)}`,{signal});if(!r.ok)throw new Error('A public example could not load.');files.push(new File([await r.blob()],example!.name));}
      if(signal.aborted)return false;await importState.uploadBatch(files,signal);return !signal.aborted;
    }
    if(['import_csv','import_netcdf','import_preview','import_chlorophyll'].includes(command.action)){
      const extension=['import_csv','import_preview'].includes(command.action)?'.csv':'.nc';
      const example=catalog.examples.find(e=>command.action==='import_chlorophyll'?e.name==='SR1902594_034.nc':e.name.endsWith(extension));
      if(!example)throw new Error('No verified example file is available in that format.');
      setUploadOpen(true);
      const response=await fetch(`/api/instruments/examples/${encodeURIComponent(example.name)}`,{signal});
      if(!response.ok)throw new Error('The example source file could not be loaded.');
      const blob=await response.blob();if(signal.aborted)return false;
      await upload(new File([blob],example.name),signal,command.action!=='import_preview');if(!signal.aborted&&command.action==='import_chlorophyll')setVariable('chlorophyll');return !signal.aborted;
    }
    if(command.action==='inspect')return true;
    throw new Error('This instrument action is not supported.');
  });
  return <section className="instrument-workspace" aria-label="Instruments and profiles">
    <header className="instrument-heading"><div><span className="eyebrow">OBSERVATIONS / SOURCE RECORDS</span><h2>Instrument profile</h2><p>Choose a reading. Keep the model beside it.</p></div><button className="secondary-button" aria-expanded={uploadOpen} onClick={()=>setUploadOpen(v=>!v)}><FileUp size={16}/>Import observations</button>{onSave&&<div className="save-analysis"><button className="secondary-button" disabled={!profile||(Boolean(local)&&!importSources[profile.id])||!manifest||query.isFetching} onClick={()=>profile&&manifest&&onSave({...(local?{import_source:importSources[profile.id]}:{}),expected_profile_sha256:profile.source_sha256,recipe:{mode:"instrument",case_id:manifest.case.id,profile_id:profile.id,variable:chosen,sample_index:effectiveIndex,show_excluded:excluded,model_time_index:Math.max(0,manifest.coordinates.times.indexOf(modelTime??manifest.coordinates.times[0]))}})}>Save investigation</button>{local&&<span className="field-hint">Saving includes the original file. Reopening reparses it and checks its checksum.</span>}</div>}{onClose&&<button className="context-button" onClick={onClose}>Close profile</button>}</header>

    {uploadOpen&&<ImportReviewPanel state={importState} catalog={catalog} imports={imports} onClear={onClear}/>}
    {catalogError&&<div role="alert" className="instrument-error"><p>{catalogError.message}</p><button className="secondary-button" onClick={retryCatalog}><RefreshCw size={15}/>Retry observations</button></div>}
    {!catalog&&!catalogError&&<p role="status">Loading observation catalogue...</p>}
    {current&&<><div className="instrument-selection"><label>Observation collection<select aria-label="Observation collection" value={collection} onChange={e=>{const first=profiles.find(p=>p.collection===e.target.value);if(first)onSelect(first.id);}}>{[...new Set(profiles.map(p=>p.collection))].map(c=><option key={c}>{c}</option>)}</select></label><label>Instrument profile<select aria-label="Instrument profile" value={current.id} onChange={e=>onSelect(e.target.value)}>{sameCollection.map(p=><option key={p.id} value={p.id}>{kind[p.instrument]} {p.platform} · {utcLabel(p.time)}</option>)}</select></label></div>
      <div className="observation-context"><Radio size={17}/><p>{locateInstruments(manifest,[profile??current]).length?overlapsModelTime(manifest,current)?'This profile overlaps the model area and its time range. This does not establish an eligible numerical match.':'This profile enters the model area, but is outside its time range. No simultaneous comparison is available.':'No eligible sample is inside this model area. This collection is outside the selected model domain or has unsupported coordinates; no local model match is claimed.'}</p></div>
      {manifest&&<div className="profile-model-times" aria-label="Observation and model dates"><span><strong>Observation sample</strong>{utcLabel(sample?.time??current.time)}</span><span><strong>Model</strong>{utcLabel(modelTime??manifest.coordinates.times[0])}</span></div>}
      <div className="instrument-layout"><details className="instrument-location"><summary>Location, track and source</summary><div className="instrument-section-title"><MapPin size={16}/><h3>Where it was measured</h3></div><InstrumentMap profiles={sameCollection} selected={current.id} onSelect={onSelect} sample={sample}/><dl className="instrument-facts"><div><dt>Instrument</dt><dd>{kind[current.instrument]}</dd></div><div><dt>First sample UTC</dt><dd>{utcLabel(current.time)}</dd></div><div><dt>Last sample UTC</dt><dd>{utcLabel(current.time_end)}</dd></div><div><dt>Position</dt><dd>{latitudeLabel(current.latitude,5)}, {longitudeLabel(current.longitude,5)}</dd></div><div><dt>Original samples</dt><dd>{current.samples}</dd></div></dl>
        {profile&&<details className="source-details"><summary>Source, methods and limitations</summary>{safeSource(profile.source_url)&&<a href={safeSource(profile.source_url)} target="_blank" rel="noreferrer">Open original data source</a>}<p>{profile.source_file}</p><p>{profile.depth_method}</p><p>{profile.qc_policy}</p><ul>{profile.warnings.map(w=><li key={w}>{w}</li>)}</ul><p className="source-hash">SHA-256: {profile.source_sha256}</p><details><summary>Source metadata</summary><pre>{JSON.stringify(profile.metadata,null,2)}</pre></details></details>}
      </details><div className="instrument-readings" aria-busy={!profile&&!query.isError}>
        {!profile&&(query.isError?<div role="alert"><p>{query.error.message}</p><button className="secondary-button" onClick={()=>void query.refetch()}>Retry profile</button></div>:<p role="status">Reading the selected source profile...</p>)}
        {profile&&parameter&&sample&&reading&&<><div className="profile-controls"><label>Measured variable<select aria-label="Profile variable" value={chosen} onChange={e=>{setVariable(e.target.value);if(profile&&sample)onSampleSelection?.(profile,sample,e.target.value);}}>{Object.entries(profile.parameters).map(([key,p])=><option key={key} value={key}>{p.label} ({p.units})</option>)}</select></label><label className="excluded-toggle"><input type="checkbox" checked={excluded} onChange={e=>setExcluded(e.target.checked)}/>Show excluded values</label></div>
          {chosen==='chlorophyll'&&<p className="instrument-warning">Observed chlorophyll estimate from the source. The current model has no chlorophyll field. Fluorescence and chlorophyll are different quantities; source adjustments and QC remain visible.</p>}<p className="curve-key"><span className="accepted-line"/> {parameter.accepted_count} accepted / {profile.samples} samples <span className="excluded-key">× excluded</span></p>
          {parameter.accepted_count===0&&<p role="status" className="instrument-warning">No values pass this variable's displayed policy. {excluded?'Excluded readings are shown for inspection.':'Enable excluded values to inspect the readings and reasons.'}</p>}
          <ProfileChart profile={profile} variable={chosen} index={effectiveIndex} onSample={chooseSample} excluded={excluded}/>
          <div className="observation-sample-controls"><button className="icon-button" aria-label="Previous observation sample" disabled={effectiveIndex===0} onClick={()=>chooseSample(Math.max(0,effectiveIndex-1))}><ChevronLeft size={17}/></button><label>Source sample<select aria-label="Observation sample" value={effectiveIndex} onChange={e=>chooseSample(Number(e.target.value))}>{profile.levels.map((l,i)=><option value={i} key={l.index}>#{l.index} · {value(l.depth_m,1)} m{l.readings[chosen].accepted?'':' · excluded'}</option>)}</select></label><button className="icon-button" aria-label="Next observation sample" disabled={effectiveIndex>=profile.samples-1} onClick={()=>chooseSample(Math.min(profile.samples-1,effectiveIndex+1))}><ChevronRight size={17}/></button></div>
          <div className="observation-value" aria-label="Observed sample value"><span>{parameter.label}</span><strong>{value(reading.value)} {parameter.units}</strong><p>{value(sample.depth_m,2)} m · {value(sample.pressure_dbar,2)} dbar</p><p className={reading.accepted?'accepted-text':'excluded-text'}>{reading.accepted?'Accepted':'Excluded'} · {parameter.qc_scheme.toUpperCase()} {reading.qc||'missing'} · {parameter.mode}</p><p>{reading.reason}</p></div>
          <dl className="instrument-facts"><div><dt>Sample time UTC</dt><dd>{sampleTime(sample.time)}</dd></div><div><dt>Sample position</dt><dd>{latitudeLabel(sample.latitude,6)}, {longitudeLabel(sample.longitude,6)}</dd></div><div><dt>Source field</dt><dd>{parameter.source_field}</dd></div></dl>
          <details className="sample-details"><summary>Raw, adjusted and coordinate details</summary><p>{parameter.definition}</p><p>{sample.coordinate_status}</p><dl className="instrument-facts"><div><dt>Raw value / QC</dt><dd>{value(reading.raw)} / {reading.raw_qc||'not supplied'}</dd></div><div><dt>Adjusted value / QC</dt><dd>{value(reading.adjusted)} / {reading.adjusted_qc||'not supplied'}</dd></div><div><dt>Adjusted error</dt><dd>{value(reading.adjusted_error)}</dd></div></dl><p>Missing adjustments stay missing. Error estimates use the parameter's units and are not a confidence score.</p></details>
          <button className="secondary-button depth-link" disabled={!inModel(manifest,sample)||!sample.coordinate_eligible||sample.depth_m===null||sample.depth_m>(manifest?.coordinates.depth_m.at(-1)??0)||sample.depth_m<(manifest?.coordinates.depth_m[0]??0)} onClick={()=>{onSampleSelection?.(profile,sample,chosen);onDepth(sample);}}>View nearest model depth <ArrowRight size={15}/></button>{manifest?.case.variables.includes('salinity')&&<button className="secondary-button depth-link" onClick={()=>{onSampleSelection?.(profile,sample,chosen);onCompare(current.id);}}>Compare with model <ArrowRight size={15}/></button>}{local&&<p className="depth-link-note">Compare sends the original file and mapping to the service again. Only eligible temperature or salinity samples are paired; chlorophyll has no matching model field.</p>}<p className="depth-link-note">Links eligible depth and position only. The model retains its own timestamp. {manifest?.case.variables.includes('salinity')?'Use Compare with model to calculate eligible pairs with explicit space, time and quality settings.':'This monthly potential-temperature field is not directly compared with instantaneous in-situ observations.'}</p>
        </>}
      </div></div></>}
  </section>;
}
