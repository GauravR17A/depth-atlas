import { InvestigationBuilder } from './workspace/InvestigationBuilder';
import type { SharedSample } from './workspace/selection';
import './workspace/connected.css';
import type { ImportSources } from './instruments/imported';
import { EvolutionWorkspace } from './evolution/EvolutionWorkspace';
import { BlackoutWorkspace } from './blackout/BlackoutWorkspace';
import type { EvolutionAnalysis } from './evolution/contracts';
import type { BlackoutAnalysis } from './blackout/contracts';
import { ClimateWorkspace } from './climate/ClimateWorkspace';
import type { ClimateAnalysis } from './climate/contracts';
import { InvestigationPanel } from './investigations/InvestigationPanel';
import type { Investigation,SaveDraft,Recipe,ComparisonRecipe } from './investigations/contracts';
import { GuidedJourney } from './guides/GuidedJourney';
import type { Comparison } from './evidence/contracts';
import { Component, lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQuery,useQueryClient } from '@tanstack/react-query';
import * as Dialog from '@radix-ui/react-dialog';
import { Bookmark, Activity, ArrowUpRight, BookOpen, Database, Globe2, Layers3, LoaderCircle, MapPin, Navigation, PanelRightClose, Radio, RefreshCw, SlidersHorizontal, LayoutGrid, X } from 'lucide-react';
import { appVersion, ApiError, getApi, parseCatalog, parseHealth, parseCase, type CaseManifest, type Region } from './contracts';
import { CaseInspector, CaseProfiles, CaseSources } from './CaseInspector';
import { EvidenceWorkspace } from './evidence/EvidenceWorkspace';
import { FeatureWorkspace } from './features/FeatureWorkspace';
import { ExpeditionWorkspace } from './expedition/ExpeditionWorkspace';
import { DriftWorkspace } from './drift/DriftWorkspace';
import { HeatWorkspace } from './heat/HeatWorkspace';
import type { HeatAnalysis } from './heat/contracts';
import type { DriftResult } from './drift/contracts';
import type { MatchRow } from './evidence/contracts';
import { OceanExplorer } from './ocean/OceanExplorer';
import { OceanGlobe } from './discovery/OceanGlobe';
import { mergeImported } from './instruments/batch';
import type { ImportedSource } from './instruments/imported';
import { InstrumentWorkspace } from './instruments/InstrumentWorkspace';
import { inModel,locateInstruments } from './instruments/context';
import { parseInstrumentCatalog,type InstrumentProfile,type Measurement } from './instruments/contracts';
import { useWorkspace, variables, type Variable } from './store';

import { LearningExperience } from './learning/LearningExperience';
import { ExplanationPanel } from './learning/ExplanationPanel';
import { useLearning, type LearningAction } from './learning/bridge';
import { ToolMenu, activityTitles, type ActivityId } from './workspace/ToolMenu';

const WiderWorkspace=lazy(()=>import('./wider/WiderWorkspace').then(module=>({default:module.WiderWorkspace})));

class SceneBoundary extends Component<{ children: ReactNode; title?: string; message?: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="scene-failure" role="status"><Globe2 /><h3>{this.props.title ?? 'Geographic preview unavailable'}</h3><p>{this.props.message ?? 'You can still select a region and inspect the data status.'}</p></div> : this.props.children;
  }
}

function Evidence({ region, manifest, inspect, tab, setTab, close }: { region?: Region; manifest?: CaseManifest; inspect: (profile: string, trigger: HTMLButtonElement) => void; tab: 'profiles' | 'sources'; setTab: (tab: 'profiles' | 'sources') => void; close: () => void }) {
  return <aside className="evidence-panel" aria-label="Evidence inspector">
    <div className="panel-title"><div><Radio size={17} /><h2>Evidence inspector</h2></div><button className="icon-button" aria-label="Close evidence inspector" onClick={close}><PanelRightClose size={18} /></button></div>
    <div className="evidence-switch" aria-label="Evidence view">
      <button aria-pressed={tab === 'profiles'} onClick={() => setTab('profiles')}>Profiles</button>
      <button aria-pressed={tab === 'sources'} onClick={() => setTab('sources')}>Sources</button>
    </div>
    {tab === 'profiles' ? <div className="evidence-content">{manifest ? <CaseProfiles manifest={manifest} inspect={inspect} /> : <>
      <div className="empty-profile"><Activity size={32} strokeWidth={1} /><h3>No profiles connected</h3><p>Instrument observations will appear here alongside the model.</p></div>
      <div className="instrument-list"><h3>Planned instruments</h3>{['Argo floats', 'Gliders', 'Ship CTD', 'BGC profiles'].map((name) => <div key={name}><span className="instrument-dash" /><span>{name}</span><span className="muted">Not loaded</span></div>)}</div>
      <div className="evidence-footnote"><MapPin size={16} /><p>{region?.name ?? 'Select a region'}<br /><span>No observation coverage established.</span></p></div></>}
    </div> : <div className="evidence-content source-content">
      <div className="source-entry"><span className="eyebrow">GEOGRAPHIC CONTEXT</span><h3>Natural Earth coastlines</h3><p>Public-domain land geometry, packaged by world-atlas at 1:110 million scale.</p><a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noreferrer">Source & terms <ArrowUpRight size={14} /></a></div>
      {manifest ? <CaseSources manifest={manifest} /> : <><div className="source-entry"><span className="eyebrow">OCEAN MODEL</span><h3>Not connected</h3><p>No model fields, dates or depth levels are loaded. The map is a geographic preview.</p></div>
      <div className="source-entry"><span className="eyebrow">OBSERVATIONS</span><h3>Not connected</h3><p>Source, timestamps, variables and quality flags will accompany every supported profile.</p></div></>}
    </div>}
  </aside>;
}

export function App() {
  const state = useWorkspace();
  const queryClient=useQueryClient();
  function clearImportedCache(){
    const filters={predicate:(q:{queryKey:readonly unknown[]})=>String(q.queryKey[0]).startsWith('evidence-')&&q.queryKey.at(-1)!=='library'};
    void queryClient.cancelQueries(filters);queryClient.removeQueries(filters);
  }
  const [selectedCaseId,setSelectedCaseId]=useState("bay-bengal-2024-01");
  const [savedOpen,setSavedOpen]=useState(false),[saveDraft,setSaveDraft]=useState<SaveDraft|null>(null),[restored,setRestored]=useState<Investigation|null>(null),[restoreKey,setRestoreKey]=useState(0),[replayNotice,setReplayNotice]=useState('');
  const [comparisonPreset,setComparisonPreset]=useState<ComparisonRecipe>();
  const [comparisonRevision,setComparisonRevision]=useState(0);
  const [guidedRecipe,setGuidedRecipe]=useState<Recipe|null>(null);
  const recipe=restored?.replay.recipe??guidedRecipe;
  function applyGuide(r:Recipe,regionId:string){
    setComparisonPreset(undefined);
    setWiderVisible(false);setRestored(null);setGuidedRecipe(r);setRestoreKey(n=>n+1);state.setRegion(regionId);setSelectedCaseId(r.case_id);setLinkedSample(undefined);setLinkedComparison(undefined);setReplayNotice('');
    setInstrumentsVisible(false);setComparisonVisible(r.mode==='comparison');setFeaturesVisible(r.mode==='features');setExpeditionVisible(r.mode==='expedition');setDriftVisible(r.mode==='drift');setHeatVisible(r.mode==='heat');setClimateVisible(r.mode==='climate');setEvolutionVisible(r.mode==='evolution');setBlackoutVisible(r.mode==='blackout');setOceanVisible(true);state.setVariable('temperature');
    if(r.mode==='ocean')setModelTimeIndex(r.time_index);
    if(r.mode==='comparison'){setModelTimeIndex(r.settings.time_index);setSelectedInstrument(r.profile_id);}
    if(r.mode==='features')setModelTimeIndex(r.query.time_index);
    if(r.mode==='evolution')setModelTimeIndex(r.query.start_index);
    if(r.mode==='blackout')setModelTimeIndex(r.query.settings.time_index);
  }
  function saveInvestigation(draft:SaveDraft){setSaveDraft(draft);setSavedOpen(true);}
  function restoreInvestigation(record:Investigation){
    setComparisonPreset(undefined);
    setSelection(undefined);setSelectionNotice('');setBuilderOpen(false);
    if(record.replay.import_source&&record.imported_profiles){clearImportedCache();setImportedProfiles(record.imported_profiles);setImportSources(Object.fromEntries(record.imported_profiles.map(p=>[p.id,record.replay.import_source!])));setInstrumentRevision(n=>n+1);}
    setWiderVisible(false);setJourneyVisible(false);const r=record.replay.recipe;setGuidedRecipe(null);setRestored(record);setRestoreKey(n=>n+1);state.setRegion(record.case.region_id);setSelectedCaseId(r.case_id);setLinkedSample(undefined);setLinkedComparison(undefined);
    setInstrumentsVisible(r.mode==='instrument');setComparisonVisible(r.mode==='comparison');setFeaturesVisible(r.mode==='features');setExpeditionVisible(r.mode==='expedition');setDriftVisible(r.mode==='drift');setHeatVisible(r.mode==='heat');setClimateVisible(r.mode==='climate');setEvolutionVisible(r.mode==='evolution');setBlackoutVisible(r.mode==='blackout');setOceanVisible(true);
    if(r.mode==='ocean'){state.setVariable(r.variable);setModelTimeIndex(r.time_index);}
    if(r.mode==='comparison'){state.setVariable(r.settings.variable);setModelTimeIndex(r.settings.time_index);setSelectedInstrument(r.profile_id);}
    if(r.mode==='features')setModelTimeIndex(r.query.time_index);
    if(r.mode==='evolution')setModelTimeIndex(r.query.start_index);
    if(r.mode==='blackout')setModelTimeIndex(r.query.settings.time_index);
    if(r.mode==='instrument'){setSelectedInstrument(r.profile_id);if(r.model_time_index!==undefined)setModelTimeIndex(r.model_time_index);}
    if(r.mode==='expedition'){state.setVariable(r.query.variable);setModelTimeIndex(r.survey?.time_index??0);}
    if(r.mode==='drift'){state.setVariable('currents');setModelTimeIndex(r.query.start_time_index);}
    if(r.mode==='heat'){state.setVariable('temperature');setModelTimeIndex(r.query.model_time_index);}
    setReplayNotice(`Opened ${record.replay.title}. Recalculation matched the saved sources, settings and numerical results before opening.`);
  }
  function changeRegion(id:string){setComparisonPreset(undefined);state.setRegion(id);const next=catalog.data?.cases.find(item=>item.region_id===id);setSelectedCaseId(next?.id??" ");if(next&&!next.variables.includes("salinity")&&state.variable!=="temperature")state.setVariable("temperature");setRestored(null);setGuidedRecipe(null);setSaveDraft(null);setRestoreKey(n=>n+1);setModelTimeIndex(0);setSelectedInstrument('');setSelection(undefined);setSelectionNotice('');setComparisonReady(false);setBuilderStep(0);setBuilderSaved(null);setLinkedSample(undefined);setLinkedComparison(undefined);setReplayNotice('');setInstrumentsVisible(false);setComparisonVisible(false);setFeaturesVisible(false);setExpeditionVisible(false);setDriftVisible(false);setHeatVisible(false);setClimateVisible(false);setEvolutionVisible(false);setBlackoutVisible(false);setOceanVisible(true);}
  const [widerVisible,setWiderVisible]=useState(false),[widerMounted,setWiderMounted]=useState(false);
  const [oceanVisible, setOceanVisible] = useState(false);
  const [instrumentsVisible,setInstrumentsVisible]=useState(false);
  const [comparisonVisible,setComparisonVisible]=useState(false);
  const [featuresVisible,setFeaturesVisible]=useState(false);
  const [expeditionVisible,setExpeditionVisible]=useState(false);
  const [driftVisible,setDriftVisible]=useState(false);
  const [heatVisible,setHeatVisible]=useState(false);
  const [climateVisible,setClimateVisible]=useState(false);
  const [evolutionVisible,setEvolutionVisible]=useState(false);
  const [blackoutVisible,setBlackoutVisible]=useState(false);
  const [modelTimeIndex,setModelTimeIndex]=useState(0);
  const [linkedComparison,setLinkedComparison]=useState<{row:MatchRow;key:number}|undefined>();
  const [selectedInstrument,setSelectedInstrument]=useState('');
  const [importedProfiles,setImportedProfiles]=useState<InstrumentProfile[]>([]);
  const [importSources,setImportSources]=useState<ImportSources>({});
  const [instrumentRevision,setInstrumentRevision]=useState(0);
  const [selection,setSelection]=useState<SharedSample>();
  const [selectionNotice,setSelectionNotice]=useState('');
  const [comparisonContext,setComparisonContext]=useState(true);
  const [comparisonReady,setComparisonReady]=useState(false);
  const [comparisonDraft,setComparisonDraft]=useState<SaveDraft|null>(null);
  const learningSnapshot=useLearning(s=>s.snapshot);
  const [builderOpen,setBuilderOpen]=useState(false);
  const [builderStep,setBuilderStep]=useState(0);
  const [builderSaved,setBuilderSaved]=useState<string|null>(null);
  function selectInstrument(id:string){if(id!==selectedInstrument){setSelection(undefined);setLinkedSample(undefined);setLinkedComparison(undefined);setSelectionNotice('');}setSelectedInstrument(id);}
  function selectSample(profile:InstrumentProfile,sample:Measurement,variable:string){
    setSelectedInstrument(profile.id);setSelection({profileId:profile.id,sampleIndex:sample.index,variable,origin:'profile'});setLinkedComparison(undefined);
    if(variable==='temperature'||variable==='salinity')state.setVariable(variable);
    const eligible=Boolean(manifest&&sample.coordinate_eligible&&inModel(manifest,sample)&&sample.depth_m!==null&&sample.depth_m>=manifest.coordinates.depth_m[0]&&sample.depth_m<=manifest.coordinates.depth_m.at(-1)!);
    setLinkedSample(eligible?{sample,key:Date.now()}:undefined);
    setSelectionNotice(`Source sample #${sample.index}, ${sample.depth_m??'missing'} m, ${sample.time}. ${eligible?'Model probe shows the nearest native depth and position. No numerical pair is implied.':'Outside this model or unsupported coordinates/depth. No model probe link.'}`);
  }
  function selectComparison(comparison:Comparison,row:MatchRow){
    setSelectedInstrument(comparison.profile.id);setSelection({profileId:comparison.profile.id,sampleIndex:row.sample_index,variable:comparison.settings.variable,origin:'comparison'});setLinkedSample(undefined);
    setLinkedComparison(row.accepted?{row,key:Date.now()}:undefined);
    setSelectionNotice(`Source sample #${row.sample_index}, ${row.depth_m??'missing'} m, ${row.observation_time}. Model: ${comparison.model_time}. ${row.accepted?'Eligible pair. The probe snaps to a native level; the residual uses depth interpolation.':`Not paired: ${row.reason.replaceAll('_',' ')}. The model probe is not linked to this reading.`}`);
  }
  function changeModelTime(next:number){if(next!==modelTimeIndex){setLinkedComparison(undefined);setLinkedSample(undefined);if(selection)setSelectionNotice('Model snapshot changed. The source reading keeps its original time, depth and position. A new match must pass the displayed rules.');}setModelTimeIndex(next);}
  function changeVariable(next:Variable){if(next!==state.variable){setLinkedComparison(undefined);setLinkedSample(undefined);if(selection)setSelectionNotice('Model variable changed. No new observation pair is claimed until the comparison is checked.');}state.setVariable(next);}
  const [linkedSample,setLinkedSample]=useState<{sample:Measurement;key:number}|undefined>();
  function openInstrument(id?:string){setOceanVisible(true);setInstrumentRevision(n=>n+1);if(id)selectInstrument(id);setInstrumentsVisible(true);setComparisonVisible(false);setFeaturesVisible(false);setExpeditionVisible(false);setDriftVisible(false);setHeatVisible(false);setClimateVisible(false);setEvolutionVisible(false);setBlackoutVisible(false);}
  function openComparison(id?:string){setOceanVisible(true);if(id)selectInstrument(id);if(!['temperature','salinity'].includes(state.variable))state.setVariable('temperature');setComparisonVisible(true);setInstrumentsVisible(false);setFeaturesVisible(false);setExpeditionVisible(false);setDriftVisible(false);setHeatVisible(false);setClimateVisible(false);setEvolutionVisible(false);setBlackoutVisible(false);}
  const [guideOpen, setGuideOpen] = useState(()=>!location.hash.startsWith('#investigation='));
  const [explanationOpen,setExplanationOpen]=useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [journeyVisible, setJourneyVisible] = useState(false);
  const guideTrigger = useRef<HTMLButtonElement>(null);
  const [evidenceTab, setEvidenceTab] = useState<'profiles' | 'sources'>('profiles');
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => getApi('/api/health', parseHealth, signal), refetchInterval: query => query.state.error instanceof ApiError && query.state.error.kind !== 'service' ? false : 30_000, refetchOnWindowFocus: true });
  const catalog = useQuery({ queryKey: ['catalog'], queryFn: ({ signal }) => getApi('/api/catalog', parseCatalog, signal), refetchInterval: query => query.state.error instanceof ApiError && query.state.error.kind !== 'service' ? false : 30_000, refetchOnWindowFocus: true });
  const region = catalog.data?.regions.find((item) => item.id === state.regionId) ?? catalog.data?.regions[0];
  const selectedCase = catalog.data?.cases.find(item => item.id === selectedCaseId && item.region_id === region?.id) ?? catalog.data?.cases.find(item => item.region_id === region?.id);
  const regionalLabs=selectedCase?.variables.includes("salinity")&&selectedCase.variables.includes("eastward_velocity")&&selectedCase.variables.includes("northward_velocity");
  const supportedVariables=Object.entries(variables).filter(([id])=>!selectedCase||((id==="currents"||id==="horizontal_kinetic_energy")?regionalLabs:selectedCase.variables.includes(id as "temperature"|"salinity")));
  const instrumentQuery=useQuery({queryKey:['instrument-catalog',appVersion,selectedCase?.id??'bay-bengal-2024-01'],queryFn:({signal})=>getApi(`/api/instruments?case_id=${encodeURIComponent(selectedCase?.id??'bay-bengal-2024-01')}`,parseInstrumentCatalog,signal),staleTime:Infinity});
  const caseQuery = useQuery({ queryKey: ['case', selectedCase?.id], queryFn: ({ signal }) => getApi(`/api/cases/${encodeURIComponent(selectedCase!.id)}`, parseCase, signal), enabled: Boolean(selectedCase) });
  const manifest = selectedCase && !catalog.isError ? caseQuery.data : undefined;
  const sceneInstruments=useMemo(()=>locateInstruments(manifest,[...(instrumentQuery.data?.profiles??[]),...importedProfiles]),[manifest,instrumentQuery.data,importedProfiles]);
  const [inspector, setInspector] = useState<{ open: boolean; profile: string | null; key: number }>({ open: false, profile: null, key: 0 });
  const caseTrigger = useRef<HTMLElement | null>(null);
  function inspect(profile: string | null = null, trigger?: HTMLButtonElement) { caseTrigger.current = state.evidenceOpen ? document.getElementById('workspace-sources') : trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null); if(state.evidenceOpen)state.toggleEvidence(); setInspector(current => ({ open: true, profile, key: current.key + 1 })); }
  const serviceFailed = health.isError || catalog.isError;
  const servicePending = health.isPending || catalog.isPending;
  function showSources() {
    setEvidenceTab('sources');
    if (!state.evidenceOpen) state.toggleEvidence();
  }
  function refresh() { void health.refetch(); void catalog.refetch(); }
  const currentError = [catalog.error, health.error].find(error => error instanceof ApiError && error.kind === 'update') ?? catalog.error ?? health.error;
  const updateAvailable = currentError instanceof ApiError && currentError.kind === 'update';
  const invalidResponse = currentError instanceof ApiError && currentError.kind === 'response';
  const reloadRequired = updateAvailable || invalidResponse;
  const statusLabel = updateAvailable ? 'Update available' : invalidResponse ? 'Data unavailable' : serviceFailed ? 'Service unavailable' : servicePending ? 'Connecting' : 'Service connected';

  const activity:ActivityId=widerVisible?'wider':instrumentsVisible?'instruments':comparisonVisible?'comparison':featuresVisible?'features':expeditionVisible?'expedition':driftVisible?'drift':heatVisible?'heat':climateVisible?'climate':evolutionVisible?'evolution':blackoutVisible?'blackout':oceanVisible?'ocean':'geography';
  useEffect(()=>{useLearning.getState().activate(activity);},[activity]);
  function openActivity(next:ActivityId,caseId?:string){
    if(caseId&&caseId!==selectedCase?.id){const selected=catalog.data?.cases.find(c=>c.id===caseId);if(!selected)return;changeRegion(selected.region_id);setSelectedCaseId(caseId);}
    setWiderVisible(next==='wider');if(next==='wider')setWiderMounted(true);
    setOceanVisible(next!=='geography');setInstrumentsVisible(next==='instruments');setComparisonVisible(next==='comparison');setFeaturesVisible(next==='features');setExpeditionVisible(next==='expedition');setDriftVisible(next==='drift');setHeatVisible(next==='heat');setClimateVisible(next==='climate');setEvolutionVisible(next==='evolution');setBlackoutVisible(next==='blackout');
    if(next==='comparison'&&!['temperature','salinity'].includes(state.variable))state.setVariable('temperature');
    if(state.evidenceOpen)state.toggleEvidence();
  }
  function selectCase(id:string){
    const selected=catalog.data?.cases.find(c=>c.id===id);if(!selected)return;
    const previous=activity;changeRegion(selected.region_id);setSelectedCaseId(selected.id);
    const needsCurrents=['comparison','expedition','drift','heat','evolution'].includes(previous);
    if(catalog.data?.unavailable_tools?.[selected.id]?.includes(previous)||needsCurrents&&!selected.variables.includes('eastward_velocity')){setReplayNotice('This tool needs data that the selected case does not supply. Ocean Explorer is open for this case.');return;}
    openActivity(previous);
  }
  function openLocatedProfile(id:string,caseId?:string,example?:{profiles:InstrumentProfile[];source:ImportedSource}){
    if(example){const merged=mergeImported(importedProfiles,example.profiles,importSources,example.source);setImportedProfiles(merged.profiles);setImportSources(merged.sources);setInstrumentRevision(n=>n+1);}
    openActivity('instruments',caseId);selectInstrument(id);setInstrumentRevision(n=>n+1);focusLocatedWorkspace();
  }
  function focusLocatedWorkspace(){requestAnimationFrame(()=>document.getElementById('ocean-workspace')?.focus());}
  function learningAction(action:LearningAction){
    setBuilderOpen(false);
    setJourneyVisible(false);setToolsOpen(false);setSavedOpen(false);setInspector(current=>({...current,open:false}));
    openActivity(action.tool,action.caseId);
    if(action.action==='builder_start'){setBuilderOpen(true);setBuilderStep(0);return useLearning.getState().issue({...action,action:'overview'});}
    if(action.action==='builder_compare'){setBuilderOpen(true);setBuilderStep(3);return useLearning.getState().issue({...action,action:'compare'});}
    return useLearning.getState().issue(action);
  }

  return <div className="app-shell focused-workspace">
    <a className="skip-link" href="#ocean-workspace">Skip to ocean workspace</a>
    <header className="topbar">
      <a className="brand" href="/" aria-label="Depth Atlas home"><span className="brand-symbol"><Navigation size={23} fill="currentColor" strokeWidth={1.3} /></span><span>Depth<span className="brand-light">Atlas</span></span></a>
      <button id="workspace-tools" className="workspace-tool-trigger" onClick={()=>setToolsOpen(true)} aria-haspopup="dialog" aria-expanded={toolsOpen}><LayoutGrid size={18}/><span>Tools</span></button>
      <span className="current-activity">{activityTitles[activity]}</span>
      <div className="topbar-actions"><button className="guide-button" aria-label="Explain current result" onClick={()=>setExplanationOpen(true)}><BookOpen size={17}/><span>Explain</span></button><button className="guide-button saved-toolbar-button" aria-label="Open saved investigations" onClick={()=>{setSaveDraft(null);setSavedOpen(true);}}><Bookmark size={17}/><span>Saved</span></button><button className="guide-button" aria-label="Quick guide" onClick={(event)=>{guideTrigger.current=event.currentTarget;setGuideOpen(true);}}><BookOpen size={17}/><span>Guide</span></button></div>
    </header>
    <div className={`main-layout ${widerVisible?"wider-mode":""} ${instrumentsVisible||comparisonVisible||featuresVisible||expeditionVisible||driftVisible||heatVisible||climateVisible||evolutionVisible||blackoutVisible?"instrument-mode":""}`}>
      <main id="ocean-workspace" className={`workspace ${state.evidenceOpen ? '' : 'evidence-hidden'}`} tabIndex={-1}>
        <h1 className="sr-only">{activityTitles[activity]}</h1>
        <div className="wider-container" hidden={!widerVisible}>{widerMounted&&<SceneBoundary title="Regional tools could not load" message="Other tools remain available. Reload the workspace to get the current regional files."><Suspense fallback={<p role="status">Opening regional tools...</p>}><WiderWorkspace active={widerVisible}/></Suspense></SceneBoundary>}</div>
        {activity!=='geography'&&!widerVisible&&!climateVisible&&<div className="workspace-context" aria-label="Current study">
          <label className="study-selector" htmlFor="study-case"><MapPin size={16}/><span>Study case</span><select id="study-case" aria-label="Study case" disabled={!selectedCase} value={selectedCase?.id??''} onChange={e=>selectCase(e.target.value)}>{!selectedCase&&<option value="">{serviceFailed?'Cases unavailable':'Loading cases...'}</option>}{catalog.data?.cases.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}</select></label>
          {activity==='ocean'&&<label className="variable-selector" htmlFor="variable"><span>Variable</span><select id="variable" aria-label="Variable" value={state.variable} onChange={e=>state.setVariable(e.target.value as Variable)}>{supportedVariables.map(([key,v])=><option key={key} value={key}>{v.label}</option>)}</select></label>}
          <div className="context-actions"><button className="context-button globe-shortcut" aria-label="Find data on globe" aria-pressed={false} onClick={()=>openActivity('geography')}><Globe2 size={17}/><span>Find on globe</span></button><button className="context-button" aria-expanded={builderOpen} onClick={()=>{setBuilderOpen(v=>!v);setJourneyVisible(false);}}>Build investigation</button><button id="workspace-sources" className="context-button" onClick={showSources}><Database size={15}/>Sources</button>{regionalLabs&&<button id="guided-case-trigger" className="context-button" aria-expanded={journeyVisible} onClick={()=>{setBuilderOpen(false);setJourneyVisible(v=>!v);}}><BookOpen size={15}/>Guided case</button>}</div>
        </div>}
        {activity!=='geography'&&manifest&&!regionalLabs&&!widerVisible&&!climateVisible&&<p className="case-availability-note">Monthly potential-temperature fields. Use Tools for climate comparisons and supported analyses.</p>}
        {manifest&&builderOpen&&<InvestigationBuilder step={builderStep} onStep={(step,tool)=>{setBuilderStep(step);openActivity(tool);}} activity={activity} ready={builderStep===0?Boolean(manifest):builderStep>=3?comparisonReady:Boolean(learningSnapshot?.caseId===manifest.case.id&&learningSnapshot.tool===activity&&learningSnapshot.status==='ready')} canCompare={Boolean(regionalLabs)} saved={Boolean(builderSaved&&builderSaved===JSON.stringify(comparisonDraft))} onSave={()=>{if(comparisonDraft)saveInvestigation(comparisonDraft);}} onClose={()=>setBuilderOpen(false)} onGuide={()=>{setBuilderOpen(false);setJourneyVisible(true);}}/>}
        {manifest&&regionalLabs&&journeyVisible&&<GuidedJourney caseId={manifest.case.id} initialOpen onApply={applyGuide} onExit={()=>{setGuidedRecipe(null);setJourneyVisible(false);document.getElementById('guided-case-trigger')?.focus();}}/>}
        {replayNotice&&<div className="replay-notice" role="status"><span>{replayNotice}</span><button className="icon-button" aria-label="Dismiss replay notice" onClick={()=>setReplayNotice('')}><X size={16}/></button></div>}
        {serviceFailed && <div className="service-alert" role="alert"><div><strong>{updateAvailable ? 'This workspace has been updated.' : invalidResponse ? 'The response could not be verified.' : 'We could not reach the ocean service.'}</strong><p>{currentError?.message ?? 'Please try again.'}</p>{currentError instanceof ApiError && currentError.requestId && <small>Reference: {currentError.requestId}</small>}</div><button onClick={reloadRequired ? () => window.location.reload() : refresh} className="secondary-button" disabled={!reloadRequired && (health.isFetching || catalog.isFetching)}><RefreshCw size={15} />{reloadRequired ? "Reload workspace" : "Try again"}</button></div>}
        {(instrumentsVisible||comparisonVisible)&&selectionNotice&&<p className="linked-selection" role="status" aria-label="Linked source selection">{selectionNotice}</p>}
        {comparisonVisible&&<div className="connected-toolbar"><button className="secondary-button" aria-pressed={comparisonContext} onClick={()=>setComparisonContext(v=>!v)}>{comparisonContext?'Expand comparison':'Show model beside comparison'}</button><a href="#comparison-results">Read comparison results</a></div>}
        <div className={instrumentsVisible||comparisonVisible&&comparisonContext?"observation-model-layout connected-layout":"exploration-layout"}>
          {manifest && <div className="model-context-pane" role="region" aria-label="Ocean model context" tabIndex={0} hidden={!oceanVisible||comparisonVisible&&!comparisonContext||featuresVisible||expeditionVisible||driftVisible||heatVisible||climateVisible||evolutionVisible||blackoutVisible}><OceanExplorer prefetch={activity==='ocean'} key={`${manifest.case.id}-${restoreKey}`} restore={recipe?.mode==='ocean'?recipe:undefined} onSave={saveInvestigation} manifest={manifest} variable={state.variable} onVariable={changeVariable} time={modelTimeIndex} onTime={changeModelTime} active={!widerVisible&&oceanVisible&&(!comparisonVisible||comparisonContext)&&!featuresVisible&&!expeditionVisible&&!driftVisible&&!heatVisible&&!climateVisible&&!evolutionVisible&&!blackoutVisible} instruments={sceneInstruments} revealInstruments={instrumentRevision} onInstrument={openInstrument} onNativeSelection={()=>{setLinkedSample(undefined);setLinkedComparison(undefined);setSelectionNotice(selection?'Model position or depth changed. The source reading is retained. Select it again to relink; this probe is not a new observation match.':'');}} linkedSample={linkedSample} linkedComparison={linkedComparison}/></div>}
          <div hidden={!instrumentsVisible}><p className="model-context-hint">Scroll within the model panel for depth and time controls.</p><InstrumentWorkspace key={`instrument-${restoreKey}`} restore={recipe?.mode==='instrument'?recipe:undefined} onSave={saveInvestigation} catalog={instrumentQuery.data} catalogError={instrumentQuery.error} retryCatalog={()=>void instrumentQuery.refetch()} selected={selectedInstrument} onSelect={selectInstrument} selection={selection} onSampleSelection={selectSample} imports={importedProfiles} importSources={importSources} onImport={(profiles,source)=>{setImportSources(old=>({...old,...Object.fromEntries(profiles.map(p=>[p.id,source]))}));setImportedProfiles(old=>[...old.filter(p=>!profiles.some(n=>n.id===p.id)),...profiles]);setInstrumentRevision(n=>n+1);}} onClear={()=>{clearImportedCache();setSaveDraft(null);setRestored(old=>old?.replay.import_source?null:old);setImportedProfiles([]);setImportSources({});setSelectedInstrument('');setSelection(undefined);setSelectionNotice('');setLinkedSample(undefined);setLinkedComparison(undefined);}} manifest={manifest} modelTime={manifest?.coordinates.times[modelTimeIndex]} onClose={()=>setInstrumentsVisible(false)} onCompare={openComparison} onDepth={sample=>{setLinkedComparison(undefined);setLinkedSample({sample,key:Date.now()});setComparisonVisible(false);setFeaturesVisible(false);setExpeditionVisible(false);setDriftVisible(false);setHeatVisible(false);setClimateVisible(false);setEvolutionVisible(false);setBlackoutVisible(false);setOceanVisible(true);}} active={instrumentsVisible&&!widerVisible}/></div>
        {manifest&&regionalLabs&&<div hidden={!comparisonVisible}><EvidenceWorkspace onDraft={setComparisonDraft} selection={selection} onSampleSelection={selectComparison} onReady={setComparisonReady} imports={importedProfiles} importSources={importSources} key={`comparison-${manifest.case.id}-${restoreKey}-${comparisonRevision}`} restore={comparisonPreset??(recipe?.mode==='comparison'?recipe:undefined)} referenceResult={comparisonPreset?undefined:restored?.results.find(m=>m.module==='reference_comparison')?.output as Comparison|undefined} onSave={saveInvestigation} manifest={manifest} catalog={instrumentQuery.data} selected={selectedInstrument} onSelect={selectInstrument} timeIndex={modelTimeIndex} onTime={changeModelTime} variable={state.variable==='salinity'?'salinity':'temperature'} onVariable={changeVariable} active={comparisonVisible&&!widerVisible} onObservation={openInstrument} onModel={row=>{setLinkedSample(undefined);setLinkedComparison({row,key:Date.now()});setComparisonContext(true);setOceanVisible(true);document.querySelector<HTMLElement>('[aria-label="Ocean model context"]')?.focus();}}/></div>}
        </div>
        {manifest&&<div hidden={!featuresVisible}><FeatureWorkspace importSources={importSources} onSupportCompare={(row,settings)=>{setComparisonPreset({mode:'comparison',case_id:manifest.case.id,profile_id:row.profile_id,settings,sample_index:0,view:'comparison',rank:'nearest',baseline:null});setComparisonRevision(n=>n+1);setSelectedInstrument(row.profile_id);setSelection({profileId:row.profile_id,sampleIndex:row.sample_index,variable:settings.variable,origin:'support'});state.setVariable(settings.variable);setModelTimeIndex(settings.time_index);openComparison();}} key={`features-${manifest.case.id}-${restoreKey}`} restore={recipe?.mode==='features'?recipe:undefined} onSave={saveInvestigation} manifest={manifest} timeIndex={modelTimeIndex} onTime={changeModelTime} active={featuresVisible&&!widerVisible} onObservation={openInstrument}/></div>}
        {manifest&&regionalLabs&&<div hidden={!evolutionVisible}><EvolutionWorkspace key={`evolution-${manifest.case.id}-${restoreKey}`} manifest={manifest} active={evolutionVisible&&!widerVisible} restore={recipe?.mode==='evolution'?recipe:undefined} restoredAnalysis={restored?.replay.recipe.mode==='evolution'?restored.results.find(module=>module.module==='evolution_analysis')?.output as EvolutionAnalysis:undefined} onSave={saveInvestigation} onObservation={openInstrument} onCase={caseId=>{const selected=catalog.data?.cases.find(item=>item.id===caseId);if(selected){changeRegion(selected.region_id);setSelectedCaseId(caseId);setEvolutionVisible(true);}}}/></div>}
        {manifest&&<div hidden={!blackoutVisible}><BlackoutWorkspace key={`blackout-${manifest.case.id}-${restoreKey}`} manifest={manifest} active={blackoutVisible&&!widerVisible} restore={recipe?.mode==='blackout'?recipe:undefined} restoredAnalysis={restored?.replay.recipe.mode==='blackout'?restored.results.find(module=>module.module==='blackout_analysis')?.output as BlackoutAnalysis:undefined} onSave={saveInvestigation} onObservation={openInstrument}/></div>}
        {manifest&&regionalLabs&&<div hidden={!expeditionVisible}><ExpeditionWorkspace key={`expedition-${manifest.case.id}-${restoreKey}`} manifest={manifest} timeIndex={modelTimeIndex} onTime={changeModelTime} active={expeditionVisible&&!widerVisible} restore={recipe?.mode==='expedition'?recipe:undefined} onSave={saveInvestigation}/></div>}
        {manifest&&regionalLabs&&<div hidden={!driftVisible}><DriftWorkspace key={`drift-${manifest.case.id}-${restoreKey}`} manifest={manifest} active={driftVisible&&!widerVisible} restore={recipe?.mode==='drift'?recipe:undefined} restoredRuns={restored?.replay.recipe.mode==='drift'?[restored.results.find(m=>m.module==='drift_run')?.output as DriftResult??null,restored.results.find(m=>m.module==='reference_drift_run')?.output as DriftResult??null]:undefined} onSave={saveInvestigation}/></div>}
        {manifest&&regionalLabs&&<div hidden={!heatVisible}><HeatWorkspace key={`heat-${manifest.case.id}-${restoreKey}`} manifest={manifest} active={heatVisible&&!widerVisible} restore={recipe?.mode==='heat'?recipe:undefined} restoredAnalysis={restored?.replay.recipe.mode==='heat'?restored.results.find(m=>m.module==='heat_analysis')?.output as HeatAnalysis:undefined} onSave={saveInvestigation} onObservation={openInstrument}/></div>}
        <div hidden={!climateVisible}><ClimateWorkspace key={`climate-${restoreKey}`} active={climateVisible&&!widerVisible} restore={recipe?.mode==='climate'?recipe:undefined} restoredAnalysis={restored?.replay.recipe.mode==='climate'?restored.results.find(module=>module.module==='climate_analysis')?.output as ClimateAnalysis:undefined} onSave={saveInvestigation} onContext={caseId=>{const selected=catalog.data?.cases.find(item=>item.id===caseId);if(selected){state.setRegion(selected.region_id);setSelectedCaseId(caseId);state.setVariable('temperature');setModelTimeIndex(0);}}} onOpenCase={(caseId,profileId)=>{const selected=catalog.data?.cases.find(item=>item.id===caseId);if(selected){changeRegion(selected.region_id);setSelectedCaseId(caseId);if(profileId){setSelectedInstrument(profileId);setInstrumentsVisible(true);}}}}/></div>
        {activity==='geography'&&catalog.isPending&&<p className="dataset-empty" role="status">Loading available model areas...</p>}
        {activity==='geography'&&catalog.data&&<SceneBoundary title="The data globe could not open" message="The case selector and Instruments remain available."><OceanGlobe catalog={catalog.data} instruments={instrumentQuery.data} instrumentError={instrumentQuery.error} retryInstruments={()=>void instrumentQuery.refetch()} imports={importedProfiles} selectedCaseId={selectedCase?.id} onModel={id=>{openActivity('ocean',id);focusLocatedWorkspace();}} onProfile={openLocatedProfile} onWider={()=>{openActivity('wider');focusLocatedWorkspace();}}/></SceneBoundary>}
        {activity!=='geography'&&!instrumentsVisible&&!comparisonVisible&&!featuresVisible&&!expeditionVisible&&!driftVisible&&!heatVisible&&!climateVisible&&!evolutionVisible&&!blackoutVisible&&(manifest ? <div className="case-source-strip"><span><Database size={14}/>{manifest.case.source_label} <span>Historical model</span></span><button className="context-button" onClick={e=>inspect(null,e.currentTarget)}>Case details <ArrowUpRight size={14}/></button></div> : selectedCase ? <section className="dataset-empty" aria-label="Ocean dataset status"><div><h3>{caseQuery.isError ? "Dataset metadata unavailable" : "Loading historical dataset"}</h3>{caseQuery.isError && <p role="alert">{caseQuery.error.message}</p>}</div>{caseQuery.isError && <button className="secondary-button" onClick={() => void caseQuery.refetch()}>Retry dataset</button>}</section> : <section className="dataset-empty" aria-label="Ocean dataset status"><div className="empty-icon"><Layers3 size={23} /></div><div><h3>No ocean model connected</h3><p>Depth, time and instrument controls need verified ocean datasets.</p></div><button className="secondary-button" onClick={showSources}>Data status <ArrowUpRight size={16} /></button></section>)}

      </main>
      <Dialog.Root open={state.evidenceOpen} onOpenChange={open=>{if(open!==state.evidenceOpen)state.toggleEvidence();}}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="source-drawer" onCloseAutoFocus={e=>{e.preventDefault();document.getElementById('workspace-sources')?.focus();}}><Dialog.Title className="sr-only">Sources and observations</Dialog.Title><Dialog.Description className="sr-only">Source records, dates and observation profiles for the current case.</Dialog.Description><Evidence region={region} manifest={manifest} inspect={inspect} tab={evidenceTab} setTab={setEvidenceTab} close={state.toggleEvidence}/></Dialog.Content></Dialog.Portal></Dialog.Root>
    </div>
    <footer className="statusbar"><span><span className={`service-status ${serviceFailed?'status-error':''}`} role="status">{servicePending?<LoaderCircle className="spin" size={12}/>:<span className={`status-dot ${serviceFailed?'error':''}`}/>}<span>{statusLabel}</span></span><SlidersHorizontal size={13} />Ocean workspace <span className="footer-separator">/</span> {activity==='geography'?"Dates listed with each dataset":widerVisible?"Bounded wider-source requests":evolutionVisible?"Historical structure correspondence":blackoutVisible?"Observation evidence exclusions":climateVisible?"Historical climate comparisons":heatVisible?"Historical surface events and depth evidence":driftVisible?"Historical passive tracers":expeditionVisible?"Historical sampling sandbox":featuresVisible?"Native structure queries":comparisonVisible?"Historical model comparisons":instrumentsVisible?"Historical observations":selectedCase ? `Historical data: ${selectedCase.time_start.slice(0,7)}` : "No case for this region"}</span><nav className="legal-links" aria-label="Site information"><a href="/about">About Us</a><a href="/data-access">Use the data</a><a href="/privacy">Privacy Policy</a><a href="/terms">Terms & Conditions</a></nav><span>Seifuku <span className="footer-separator">/</span> v{appVersion}</span></footer>
    {manifest && <CaseInspector key={`${manifest.case.id}-${inspector.key}`} manifest={manifest} open={inspector.open} onOpenChange={open => setInspector(current => ({ ...current, open }))} initialProfile={inspector.profile} returnFocus={caseTrigger} />}
    <InvestigationPanel onSaved={record=>{if(builderOpen&&record.replay.recipe.mode==='comparison')setBuilderSaved(JSON.stringify(comparisonDraft));}} open={savedOpen} setOpen={setSavedOpen} draft={saveDraft} onRestore={restoreInvestigation}/>
    <ToolMenu open={toolsOpen} onOpenChange={setToolsOpen} active={activity} onChoose={openActivity} hasModel={Boolean(manifest)} indian={Boolean(regionalLabs)} unavailableTools={catalog.data?.unavailable_tools?.[selectedCase?.id??'']??[]}/>
    <LearningExperience welcomeOpen={guideOpen} sourcesReady={Boolean(catalog.data)} onCloseWelcome={()=>setGuideOpen(false)} onAction={learningAction} onExplain={()=>setExplanationOpen(true)} onOpenTools={()=>setToolsOpen(true)}/>
    <ExplanationPanel open={explanationOpen} onClose={()=>setExplanationOpen(false)} manifest={manifest} onAction={learningAction}/>

  </div>;
}
