import type { CaseManifest } from '../contracts';
import type { LearningAction, LearningSnapshot } from './bridge';

export const glossary: Record<string,string> = {
  model:'A model is a calculation on a grid. It estimates ocean conditions using physical equations and available inputs. A model value is not itself a sensor reading.',
  observation:'An observation is a sensor measurement with its own location, depth, time and quality flags. Only compatible observations can be compared with a model.',
  temperature:'Temperature describes how warm the water is. Read its unit and definition: in-situ temperature and potential temperature are different quantities.',
  salinity:'Salinity describes salt content. Practical salinity is conductivity-based. A source reporting grams per kilogram has a different definition; those labels cannot be swapped.',
  depth:'Depth increases downwards from the surface. Source levels can be unevenly spaced. A display stretch helps you see them without changing the actual depth.',
  pressure:'Pressure increases with the weight of water above a sensor. Decibars are pressure units, not metres. Any conversion needs a declared physical method and location.',
  current:'A current is moving water. Eastward and northward components define horizontal direction and speed. Current arrows are not particle tracks.',
  'colour key':'The colour key maps numbers to colours. Changing the palette or range changes the drawing, not the source values. A logarithmic scale requires positive limits.',
  cutaway:'A cutaway opens a part of the drawing to reveal internal layers. It does not remove water or edit the source data.',
  slice:'A depth slice shows one horizontal layer. A vertical section shows a side view along a line, with depth increasing downwards.',
  isosurface:'An isosurface joins places with an equal value in a rendered field. The crossings are interpolated. It is not an observed physical wall.',
  'quality flags':'Quality flags describe the source provider’s assessment of readings or coordinates. Different sources have different schemes. Rejected values are not silently promoted to accepted data.',
  residual:'A residual here is model minus observation. A positive value means the model is higher. It is calculated only for eligible pairs; an excluded pair has no valid residual.',
  assimilation:'Assimilation incorporates observations into a model analysis. A later comparison with those observations may be useful, but it is not independent validation.',
  interpolation:'Interpolation estimates a value between available samples. This comparison allows vertical interpolation only between eligible adjacent depths inside the stated gap limit.',
  anomaly:'An anomaly is a value minus a stated reference average. A negative anomaly means below that reference, not necessarily below zero degrees.',
  baseline:'A baseline is the reference used for a comparison. Climate and marine-heatwave tools use explicitly different reference periods and methods. Always check the selected tool.',
  'el nino':'El Niño describes a warm phase of tropical Pacific climate variability. The app uses pinned official surface indices to label its selected historical seasons, alongside separate subsurface model fields.',
  'la nina':'La Niña describes a cold phase of tropical Pacific climate variability. The app demonstrates selected historical seasons; it does not forecast when the next phase will occur.',
  iod:'The Indian Ocean Dipole describes a pattern of temperature contrast in the tropical Indian Ocean. Agency event assessments and numerical DMI values remain separately identified here.',
  'mixed layer':'The mixed layer is a near-surface region identified using a stated density or temperature-change criterion. The displayed criterion and reference depth matter; different definitions can give different depths.',
  stratification:'Stratification describes how water density changes vertically. The signed buoyancy-frequency-squared diagnostic can distinguish stable and unstable conditions under its declared assumptions.',
  'heat content':'This app’s column diagnostic integrates potential enthalpy relative to its stated zero reference over supported depths. It is not automatically an anomaly or a surface heatwave measurement.',
  drift:'Drift Lab integrates fixed-depth passive particles through historical horizontal model currents. It omits windage, sinking, diffusion and swimming. Its spread is not a real-world probability.',
  evolution:'Feature evolution connects threshold regions by native-volume overlap. Splits, merges and gaps remain explicit. A connected shape is not proof that the same water moved.',
  blackout:'Observation blackout excludes selected profiles from the comparison evidence. It leaves the ocean model and original quality flags unchanged; it does not rerun assimilation.',
  expedition:'Virtual Expedition plans and samples a supplied model. Its samples are simulated. Equal-budget reconstruction experiments do not establish operational forecast improvement.',
  netcdf:'NetCDF stores scientific arrays and metadata together. Supported adapters interpret their coordinates, units and source variables. A different layout may need another adapter.',
  csv:'CSV is a text table. A supported schema needs columns and metadata for the values, positions, times and quality flags. Arbitrary spreadsheets cannot be interpreted safely by guessing.',
  cf:'CF Conventions give scientific NetCDF files a common way to describe variables and coordinates. The app checks supported metadata and rejects incompatible definitions.',
  opendap:'OPeNDAP lets a server return requested parts of scientific data. The browser uses this app’s lightweight API; server compatibility and institutional installation are separate requirements.',
  wms:'OGC WMS serves georeferenced map images. An image can show a field, but it is not a substitute for the numerical source values.',
  wcs:'OGC WCS serves numerical coverages with their coordinates. Data access describes this project’s tested subset and its limits.',
  uncertainty:'Uncertainty depends on its source and definition. A producer’s ML uncertainty, missing-data coverage, sensitivity spread and real-world probability are different things.',
  missing:'Missing means unavailable or masked, never zero. The source may mark land, seabed, failed measurements or unsupported calculations.',
};
export type RequestPlan =
  | {kind:'explain'} | {kind:'definition';term:string;text:string}
  | {kind:'plan';label:string;parameters:Record<string,string|number>;action:LearningAction}
  | {kind:'unsupported';message:string};
export function interpretRequest(input:string,manifest?:CaseManifest):RequestPlan {
  if(input.length>300)return {kind:'unsupported',message:'Keep requests within 300 characters. Choose one supported question or action.'};
  const text=input.trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[?.!]+$/,'').replace(/\s+/g,' ');
  if(['explain this','explain this result','what am i seeing','explain the result'].includes(text))return {kind:'explain'};
  const term=text.replace(/^(what is|what are|explain|define) (a |an |the )?/,'');
  if(Object.hasOwn(glossary,term))return {kind:'definition',term,text:glossary[term]};
  const match=/^(?:show|inspect) (temperature|salinity) at (\d+(?:\.\d+)?) (?:m|metres|meters)$/.exec(text);
  if(match){
    if(!manifest)return {kind:'unsupported',message:'Load a supported study case before preparing a depth query.'};
    const variable=match[1],depth=Number(match[2]);
    if(!manifest.case.variables.includes(variable as 'temperature'|'salinity'))return {kind:'unsupported',message:'That variable is not supplied by this study case.'};
    if(!manifest.coordinates.depth_m.includes(depth))return {kind:'unsupported',message:'That exact depth is not supplied. Choose a native depth from Inspection depth; no value will be invented or silently rounded.'};
    return {kind:'plan',label:`Inspect ${variable} at ${depth} m`,parameters:{case_id:manifest.case.id,variable,depth_m:depth},action:{tool:'ocean',action:'query_depth',value:`${variable}:${depth}`,caseId:manifest.case.id}};
  }
  if(['open cutaway','show depth slice','show current vectors'].includes(text)){
    if(!manifest)return {kind:'unsupported',message:'Load a study case first.'};
    if(text==='show current vectors'&&!manifest.case.variables.includes('eastward_velocity'))return {kind:'unsupported',message:'This case does not supply horizontal current vectors.'};
    return {kind:'plan',label:text,parameters:{case_id:manifest.case.id,action:text},action:{tool:'ocean',action:text==='open cutaway'?'cutaway':text==='show depth slice'?'slice':'currents',caseId:manifest.case.id}};
  }
  return {kind:'unsupported',message:'I cannot establish that from the supported requests. I can explain the current result, define a listed concept, or prepare a native-depth/view action. I do not invent measurements, change sources, predict hazards or answer arbitrary ocean forecasts.'};
}
export function explainSnapshot(snapshot:LearningSnapshot|null):{title:string;body:string;available:boolean} {
  if(!snapshot)return {title:'No current result',body:'Open a tool and let its data finish loading. There is no result to explain yet.',available:false};
  if(snapshot.status!=='ready')return {title:snapshot.status==='loading'?'Waiting for the result':'No completed result',body:snapshot.message??'This selection has not produced a completed result. No values or conclusions will be filled in.',available:false};
  const bodies:Record<LearningSnapshot['kind'],string>={
    model:'These are values from the selected historical model source. Read the variable, unit, location and date together. They are not live sensor measurements.',
    observation:'These readings come from an instrument, with original time, location and quality information. An unavailable reading has no accepted numerical value.',
    comparison:'This compares compatible model and sensor samples under the displayed matching rules. Model minus observation is the residual. Missing or excluded pairs do not produce valid residuals.',
    derived:'These results were calculated from the stated source data and applied parameters. Their interpretation depends on the method and limitations shown below.',
    simulation:'This is an experiment using model fields. It is not a new measurement. The applied settings determine the result, and its limitations remain part of the explanation.',
    source:'This identifies the data and access method. It does not establish live coverage or operational deployment.',
  };
  return {title:snapshot.title,body:bodies[snapshot.kind],available:true};
}
