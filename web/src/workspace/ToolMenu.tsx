import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { Activity, ArrowUpRight, Box, Compass, FlaskConical, Globe2, MapPin, Radio, Search, Thermometer, Waves, X, type LucideIcon } from 'lucide-react';

export type ActivityId = 'ocean' | 'instruments' | 'comparison' | 'features' | 'evolution' | 'blackout' | 'expedition' | 'drift' | 'heat' | 'climate' | 'wider' | 'geography';
type Tool = { id: ActivityId; title: string; label: string; description: string; icon: LucideIcon; indian?: boolean; model?: boolean };
const groups: { name: string; tools: Tool[] }[] = [
  { name: 'Explore the ocean', tools: [
    { id: 'ocean', title: 'Ocean Explorer', label: 'Ocean explorer', description: 'Look through depth, space and time.', icon: Box },
    { id: 'features', title: 'Find structures', label: 'Open structure search', description: 'Find water that meets a condition.', icon: Search, model: true },
    { id: 'wider', title: 'More regions', label: 'Open wider ocean coverage', description: 'Choose a bounded area in wider sources.', icon: Globe2 },
    { id: 'geography', title: 'Data globe', label: 'Geographic context', description: 'Find model areas and measured profiles.', icon: MapPin },
  ] },
  { name: 'Compare the evidence', tools: [
    { id: 'instruments', title: 'Instruments', label: 'Open instruments', description: 'Inspect real sensor profiles or import data.', icon: Radio },
    { id: 'comparison', title: 'Model comparison', label: 'Compare', description: 'Compare eligible measurements with a model.', icon: Activity, indian: true },
    { id: 'heat', title: 'Heat & Depth', label: 'Open Heat and Depth Lab', description: 'Connect surface warmth and depth evidence.', icon: Thermometer, indian: true },
    { id: 'climate', title: 'Climate Event Lab', label: 'Open Climate Event Lab', description: 'Compare El Niño, La Niña and neutral cases.', icon: FlaskConical },
  ] },
  { name: 'Run an experiment', tools: [
    { id: 'drift', title: 'Drift Lab', label: 'Open Drift Lab', description: 'Release passive particles into model currents.', icon: Waves, indian: true },
    { id: 'expedition', title: 'Virtual Expedition', label: 'Open Virtual Expedition', description: 'Plan stations and test a virtual survey.', icon: Compass, indian: true },
    { id: 'evolution', title: 'Feature evolution', label: 'Open feature evolution', description: 'Follow threshold regions across snapshots.', icon: Activity, indian: true },
    { id: 'blackout', title: 'Observation blackout', label: 'Open observation blackout', description: 'See which evidence is lost without sensors.', icon: Radio, model: true },
  ] },
];
export const activityTitles = Object.fromEntries(groups.flatMap(g => g.tools.map(t => [t.id, t.title]))) as Record<ActivityId, string>;

export function ToolMenu({ open, onOpenChange, active, onChoose, hasModel, indian, unavailableTools = [] }: { open: boolean; onOpenChange: (open: boolean) => void; active: ActivityId; onChoose: (activity: ActivityId, caseId?: string) => void; hasModel: boolean; indian: boolean; unavailableTools?: string[] }) {
  const [needsCase,setNeedsCase]=useState<ActivityId|null>(null);
  function close(open:boolean){if(!open)setNeedsCase(null);onOpenChange(open);}
  return <Dialog.Root open={open} onOpenChange={close}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="tool-menu" onCloseAutoFocus={e => { e.preventDefault(); document.getElementById('workspace-tools')?.focus(); }}>
    <div className="tool-menu-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><Dialog.Title>{needsCase?`Choose a case for ${activityTitles[needsCase]}`:'What would you like to find out?'}</Dialog.Title><Dialog.Description>{needsCase?'This tool needs the separately checked Indian Ocean fields. Choosing a case resets the current case settings.':'Pick a tool. Settings stay in place while you switch within a case.'}</Dialog.Description></div><Dialog.Close asChild><button className="icon-button" aria-label="Close tools"><X size={22}/></button></Dialog.Close></div>
    {needsCase?<div className="tool-case-choice"><button className="context-button" onClick={()=>setNeedsCase(null)}>Back to tools</button>{[['bay-bengal-2024-01','Bay of Bengal'],['arabian-sea-2024-01','Arabian Sea']].map(([id,label])=><button key={id} className="tool-card" onClick={()=>{onChoose(needsCase,id);close(false);}}><MapPin size={22}/><span><strong>{label}</strong><small>7–10 January 2024 · historical model</small></span><ArrowUpRight size={18}/></button>)}</div>:<div className="tool-groups">{groups.map(group => <section key={group.name}><h3>{group.name}</h3>{group.tools.map(tool => {
      const unavailable = Boolean((tool.model || tool.indian) && !hasModel);
      const Icon = tool.icon;
      return <button key={tool.id} className="tool-card" aria-label={tool.label} aria-current={active === tool.id ? 'page' : undefined} disabled={unavailable} onClick={() => { if(tool.indian&&!indian||unavailableTools.includes(tool.id)){setNeedsCase(tool.id);return;}onChoose(tool.id);close(false); }}>
        <Icon size={21}/><span><strong>{tool.title}</strong><small>{unavailable ? 'Waiting for case data.' : tool.description}{(tool.indian&&!indian||unavailableTools.includes(tool.id))&&!unavailable&&<span className="tool-coverage">Opens with an Indian Ocean case</span>}</small></span><ArrowUpRight className="tool-arrow" size={16}/>
      </button>;
    })}</section>)}</div>}
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
