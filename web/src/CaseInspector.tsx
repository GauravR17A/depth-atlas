import { PublicationStatus } from './PublicationStatus';
import { useState, type RefObject } from 'react';
import { longitudeLabel, latitudeLabel } from './geography';
import { useQuery } from '@tanstack/react-query';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowUpRight, Database, X } from 'lucide-react';
import { getApi, parseObservation, parseSubset, type CaseManifest, type ProfileSummary, type ScientificVariable } from './contracts';

export function utcLabel(value: string) {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value)) + ' UTC';
}
export function caseTimeLabel(manifest:CaseManifest,value:string){return manifest.representations?.temporal_support?.kind==='calendar_month_mean'?new Date(value).toLocaleDateString('en-GB',{timeZone:'UTC',month:'long',year:'numeric'})+' monthly mean':utcLabel(value);}
export function caseDateRange(manifest: CaseManifest) {
  const label = (value: string) => new Date(value).toLocaleDateString('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'long', year: 'numeric' });
  const intervals=manifest.representations?.temporal_support?.intervals;
  const start=intervals?.[0]?.[0]??manifest.case.time_start,end=intervals?.at(-1)?.[1];
  return `${label(start)} to ${label(end?new Date(Date.parse(end)-86400000).toISOString():manifest.case.time_end)}`;
}
const number = (value: number | null | undefined, digits = 3) => value == null ? 'Missing' : value.toFixed(digits);

export function CaseSources({ manifest }: { manifest: CaseManifest }) {
  return <><PublicationStatus/><div className="source-entry"><span className="eyebrow">DATA ACCESS</span><h3>Use this case in your own tools</h3><p>{manifest.representations?.temporal_support?.kind==='calendar_month_mean'?'Bounded REST selections, original GODAS and Argo sources, and Climate CSV evidence are available. A Pacific NetCDF download and hosted THREDDS collection are not yet configured.':'Native-grid NetCDF, bounded API selections and declared service availability.'}</p><a href="/data-access">Use the data <ArrowUpRight size={14} /></a></div>{manifest.sources.map(source => <div className="source-entry" key={source.source_id}>
    <span className="eyebrow">{source.kind === 'observation' ? 'OBSERVATIONS' : 'MODEL ANALYSIS'}</span>
    <h3>{source.title}</h3><p>{source.provider}</p><p><strong>Historical: {caseDateRange(manifest)}</strong><br />Retrieved {new Date(source.retrieved_at).toLocaleDateString('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'long', year: 'numeric' })}</p>
    <p>{source.limitations[0]}</p><a href={source.source_url} target="_blank" rel="noreferrer">Source <ArrowUpRight size={14} /></a>{' · '}<a href={source.licence_url} target="_blank" rel="noreferrer">Data terms <ArrowUpRight size={14} /></a>
  </div>)}</>;
}

export function CaseProfiles({ manifest, inspect }: { manifest: CaseManifest; inspect: (profile: string, trigger: HTMLButtonElement) => void }) {
  return <div className="profile-directory"><p className="profile-intro">{manifest.profiles.length} historical Argo profiles with their original source metadata. Open a record to inspect its values and quality flags.</p>
    {manifest.profiles.map(profile => <button key={profile.id} className="profile-entry" onClick={event => inspect(profile.id, event.currentTarget)}><span>Argo {profile.platform}<ArrowUpRight size={14} /></span><small>{utcLabel(profile.time)}</small><small>{latitudeLabel(profile.latitude, 3)} · {longitudeLabel(profile.longitude, 3)}</small><small>{profile.data_mode === 'D' ? 'Delayed-mode adjusted' : profile.data_mode === 'A' ? 'Real-time adjusted' : 'Real-time unadjusted'}</small></button>)}
    <p className="profile-footnote">Use Instruments to inspect source quality and Compare to apply the declared matching rules. Overlap alone does not make a profile eligible.</p>
  </div>;
}

function ProfileRecord({ manifest, profile }: { manifest: CaseManifest; profile: ProfileSummary }) {
  const query = useQuery({ queryKey: ['profile', manifest.case.id, profile.id], queryFn: ({ signal }) => getApi(`/api/cases/${encodeURIComponent(manifest.case.id)}/profiles/${encodeURIComponent(profile.id)}`, parseObservation, signal) });
  if (query.isPending) return <p role="status">Loading the instrument record…</p>;
  if (query.isError) return <div role="alert"><p>{query.error.message}</p><button className="secondary-button" onClick={() => void query.refetch()}>Retry profile</button></div>;
  return <section className="profile-record"><h3>Argo {profile.platform} · cycle {profile.cycle}</h3><p>{utcLabel(profile.time)}<br />{latitudeLabel(profile.latitude, 4)}, {longitudeLabel(profile.longitude, 4)}</p>
    <p>{profile.eligible_samples} of {profile.samples} samples pass the declared QC filter. {profile.data_mode === 'D' ? 'Delayed-mode adjusted values are selected.' : 'The record retains its reported data mode.'}</p>
    <p className="method-note">Pressure is measured in dbar. Depth is calculated from pressure and latitude using TEOS-10, with no supplied dynamic-height correction. Temperature is in-situ; salinity is practical salinity.</p>
    <div className="record-table" tabIndex={0} role="region" aria-label="Argo profile samples"><table><caption>All source levels, in source order. QC columns: pressure / temperature / salinity.</caption><thead><tr><th>Pressure<br /><span>dbar</span></th><th>Depth<br /><span>m</span></th><th>Temp.<br /><span>°C</span></th><th>Salinity<br /><span>psu</span></th><th>QC</th><th>Use</th></tr></thead><tbody>{query.data.levels.map(level => <tr key={level.source_level_index}><td>{number(level.pressure_dbar, 1)}</td><td>{number(level.depth_m, 1)}</td><td>{number(level.temperature_c)}</td><td>{number(level.salinity_psu)}</td><td>{level.qc.PRES}/{level.qc.TEMP}/{level.qc.PSAL}</td><td>{level.eligible ? 'Eligible' : 'Excluded'}</td></tr>)}</tbody></table></div>
    <details className="method-details"><summary>Quality rules and original record</summary><p>{query.data.qc_policy}</p><p>{query.data.depth_method}</p><a href={profile.source_url} target="_blank" rel="noreferrer">Original Argo NetCDF file <ArrowUpRight size={14} /></a><p className="file-fingerprint">SHA-256: {profile.source_sha256}</p></details>
  </section>;
}

export function CaseInspector({ manifest, open, onOpenChange, initialProfile, returnFocus }: { manifest: CaseManifest; open: boolean; onOpenChange: (value: boolean) => void; initialProfile: string | null; returnFocus: RefObject<HTMLElement | null> }) {
  const [timeIndex, setTimeIndex] = useState(0);
  const [depthIndex, setDepthIndex] = useState(0);
  const [variable, setVariable] = useState<ScientificVariable>('temperature');
  const [recordId, setRecordId] = useState(initialProfile ?? 'model');
  const c = manifest.coordinates;
  const latitude = c.latitude[Math.floor(c.latitude.length / 2)];
  const longitude = c.longitude[Math.floor(c.longitude.length / 2)];
  const path = `/api/cases/${encodeURIComponent(manifest.case.id)}/subset?${new URLSearchParams({ variable, time_index: String(timeIndex), depth_index: String(depthIndex), representation: 'analytical', west: String(longitude), east: String(longitude), south: String(latitude), north: String(latitude) })}`;
  const sample = useQuery({ queryKey: ['model-sample', path], queryFn: ({ signal }) => getApi(path, parseSubset, signal), enabled: open && recordId === 'model' });
  const spec = manifest.variables.find(v => v.id === variable)!;
  const profile = manifest.profiles.find(p => p.id === recordId);
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content case-dialog" onCloseAutoFocus={event => { event.preventDefault(); returnFocus.current?.focus(); }}>
    <span className="eyebrow">HISTORICAL DATASET</span><Dialog.Title>{manifest.case.title}</Dialog.Title><Dialog.Description>Real model fields and instrument records. These are historical conditions, not live 2026 data.</Dialog.Description>
    <dl className="case-facts"><div><dt>Model</dt><dd>{manifest.case.source_label}</dd></div><div><dt>Coverage</dt><dd>{longitudeLabel(manifest.case.bounds[0])} to {longitudeLabel(manifest.case.bounds[2])} · {latitudeLabel(manifest.case.bounds[1])} to {latitudeLabel(manifest.case.bounds[3])}</dd></div><div><dt>Snapshots</dt><dd>{manifest.case.time_count} source timestamps; {caseDateRange(manifest)}</dd></div><div><dt>Depth coordinates</dt><dd>{manifest.case.depth_count}, from {manifest.case.depth_range_m[0]} to {manifest.case.depth_range_m[1]} m</dd></div></dl>
    <p className="method-note">{manifest.representations?.temporal_support?.kind==='calendar_month_mean'?'Source timestamps mark the first day of their calendar-month mean, not an instantaneous sample. ':''}Depth levels are irregular. Cells below the local seafloor or without values stay missing. The depth range does not promise usable data everywhere.</p>
    <div className="control-block"><label htmlFor="record-type">Inspect a record</label><select id="record-type" value={recordId} onChange={event => setRecordId(event.target.value)}><option value="model">Model grid sample</option>{manifest.profiles.map(p => <option key={p.id} value={p.id}>Argo {p.platform} · {p.time.slice(0,10)}</option>)}</select></div>
    {profile ? <ProfileRecord key={profile.id} manifest={manifest} profile={profile} /> : <section className="model-sample"><h3>Model grid sample</h3><p>Native grid point at {latitudeLabel(latitude)}, {longitudeLabel(longitude)}. No interpolation.</p><div className="sample-controls"><div className="control-block"><label htmlFor="sample-variable">Sample variable</label><select id="sample-variable" value={variable} onChange={e => setVariable(e.target.value as ScientificVariable)}>{manifest.variables.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}</select></div><div className="control-block"><label htmlFor="sample-time">Sample timestamp (UTC)</label><select id="sample-time" value={timeIndex} onChange={e => setTimeIndex(Number(e.target.value))}>{c.times.map((t,i) => <option key={t} value={i}>{caseTimeLabel(manifest,t)}</option>)}</select></div><div className="control-block"><label htmlFor="sample-depth">Sample depth (m)</label><select id="sample-depth" value={depthIndex} onChange={e => setDepthIndex(Number(e.target.value))}>{c.depth_m.map((z,i) => <option key={z} value={i}>{z} m</option>)}</select></div></div>
      <div className="sample-value" aria-live="polite">{sample.isPending ? <span>Loading sample…</span> : sample.isError ? <><p role="alert">{sample.error.message}</p><button className="secondary-button" onClick={() => void sample.refetch()}>Retry sample</button></> : <><span>{spec.label} · {sample.data.depth_m[0]} m</span><strong>{sample.data.values[0] === null ? 'No value at this depth' : `${number(sample.data.values[0])} ${sample.data.units}`}</strong><small>{caseTimeLabel(manifest,sample.data.time)} · model analysis</small></>}</div><p className="method-note">{spec.definition} Displayed numbers are rounded to three decimal places; the analytical API preserves decoded values.</p>
    </section>}
    <details className="method-details"><summary>Sources and limits</summary><CaseSources manifest={manifest} /><ul>{manifest.limitations.map(item => <li key={item}>{item}</li>)}</ul><p>Ocean analyses can assimilate observations. Agreement with Argo is not automatically independent validation.</p></details>
    <Dialog.Close asChild><button className="secondary-button case-close">Return to workspace</button></Dialog.Close><Dialog.Close asChild><button className="icon-button dialog-close" aria-label="Close dataset inspector"><X size={20} /></button></Dialog.Close>
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}

export function CaseCard({ manifest, inspect }: { manifest: CaseManifest; inspect: (trigger: HTMLButtonElement) => void }) {
  return <section className="dataset-empty dataset-ready" aria-label="Ocean dataset status"><div className="empty-icon"><Database size={23} /></div><div><span className="eyebrow">HISTORICAL CASE</span><h3>{caseDateRange(manifest)}</h3><p>{manifest.case.time_count} model snapshots · {manifest.case.depth_count} depth levels · {manifest.case.profile_count} Argo profiles</p><p>{manifest.case.source_label}. Inspect source values and available observation quality flags.</p></div><button className="secondary-button" onClick={event => inspect(event.currentTarget)}>Inspect dataset <ArrowUpRight size={16} /></button></section>;
}
