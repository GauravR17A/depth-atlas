import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeft, ArrowRight, Compass, GitBranch, Globe2, Layers3, Radio, Route, Thermometer, Waves, X, Leaf, FileInput, ListChecks, ScanSearch, Download, RefreshCw } from 'lucide-react';
import { featureTours, type FeatureTourId } from './featureTours';
import type { TutorialMode } from './lessons';

const icons = {chlorophyll:Leaf,imports:FileInput,builder:ListChecks,support:ScanSearch,offline:Download,publication:RefreshCw,drift:Route,climate:Waves,heat:Thermometer,structures:Layers3,expedition:Compass,evolution:GitBranch,blackout:Radio,wider:Globe2};
export function FeatureTourPicker({mode,onMode,onSelect,onBack,onAll}:{mode:TutorialMode;onMode:(mode:TutorialMode)=>void;onSelect:(id:FeatureTourId)=>void;onBack:()=>void;onAll:()=>void}) {
  const [page,setPage]=useState(0);
  const pages=Math.ceil(featureTours.length/2);
  return <Dialog.Root open onOpenChange={open=>{if(!open)onBack();}}><Dialog.Portal>
    <Dialog.Overlay className="dialog-overlay intro-overlay"/>
    <Dialog.Content className="feature-tour-picker" aria-labelledby="feature-tour-title" onOpenAutoFocus={event=>{event.preventDefault();document.getElementById('feature-tour-title')?.focus();}} onCloseAutoFocus={event=>event.preventDefault()}>
      <div className="learn-topline"><span>BEYOND THE BASICS</span><button className="icon-button" aria-label="Close extra feature tutorials" onClick={onBack}><X size={18}/></button></div>
      <Dialog.Title id="feature-tour-title" tabIndex={-1}>What will you try next?</Dialog.Title>
      <Dialog.Description>{featureTours.length} guided features. Choose one below, or browse the next pair.</Dialog.Description>
      <label className="feature-tour-mode">Tutorial style <select aria-label="Extra feature tutorial style" value={mode} onChange={event=>onMode(event.target.value as TutorialMode)}><option value="basic">Basic: actions and results</option><option value="deep">In-depth: concepts and methods too</option></select></label>
      <nav className="feature-tour-pagination" aria-label="Browse extra features"><button className="secondary-button" disabled={page===0} onClick={()=>setPage(p=>p-1)}><ArrowLeft size={15}/> Back</button><span role="status">{page+1} / {pages}<small>Features {page*2+1}-{Math.min(page*2+2,featureTours.length)} of {featureTours.length}</small></span><button className="primary-button tutorial-next-glow" disabled={page===pages-1} onClick={()=>setPage(p=>p+1)}>More features <ArrowRight size={18}/></button></nav>
      <div className="feature-tour-cards" aria-label="Extra features">
        {featureTours.slice(page*2,page*2+2).map(tour=>{const Icon=icons[tour.id];return <button key={tour.id} className="feature-tour-card" aria-label={`Start ${tour.title} tutorial`} onClick={()=>onSelect(tour.id)}>
          <span className="feature-tour-card-top"><Icon size={25} aria-hidden="true"/><span>{tour.kind}</span></span>
          <strong>{tour.title}</strong><span className="feature-tour-question">{tour.question}</span><span className="feature-tour-description">{tour.description}</span>
          <span className="feature-tour-card-footer">{tour.lessonIds.length} guided {tour.lessonIds.length===1?'step':'steps'}<span>Show me <ArrowRight size={16}/></span></span>
        </button>;})}
      </div>
      <div className="feature-tour-footer"><button className="learn-text-button" onClick={onBack}>Back to guide</button><button className="learn-text-button" onClick={onAll}>Tour all extra features <ArrowRight size={15}/></button></div>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
