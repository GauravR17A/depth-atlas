import { useState, type RefObject } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeft, ArrowRight, Bookmark, Box, MousePointer2, Radio, Waves } from 'lucide-react';

const slides = [
  { title: 'Look below the surface.', text: 'Explore ocean temperature, salt and currents. Turn the 3D view to see how they change with depth.' },
  { title: 'One question. One tool.', text: 'Use Tools to explore the water, compare measurements or run an experiment. Open only what you need.' },
  { title: 'Your first discovery.', text: 'Open the cutaway, then click the water to read a value. Change the depth or date to explore further.' },
];

function DepthDiagram() {
  return <svg className="intro-depth" viewBox="0 0 500 245" role="img" aria-label="Illustration of an ocean column with a cutaway revealing layers below the surface">
    <g stroke="#81b8bf" strokeWidth="1.5" strokeLinejoin="round">
      <path d="M100 75 255 24 394 77 240 132Z" fill="#367b87"/>
      <path d="M100 75 240 132 240 222 100 165Z" fill="#183d55"/>
      <path d="M240 132 394 77 394 167 240 222Z" fill="#1d536a"/>
      <path d="M100 104 240 160 394 107M100 134 240 191 394 137" fill="none" stroke="#427589"/>
      <path d="M198 89 255 69 307 89 252 110Z" fill="#dbb270"/>
      <path d="M198 89 252 110 252 199 198 178Z" fill="#377f91"/>
      <path d="M252 110 307 89 307 178 252 199Z" fill="#22546e"/>
      <path d="M198 113 252 134 307 113" fill="none" stroke="#dbb270" strokeWidth="7"/>
      <path d="M198 143 252 164 307 143" fill="none" stroke="#6baca9" strokeWidth="7"/>
    </g>
    <g fill="#c4dce3" fontSize="13" fontFamily="system-ui"><text x="345" y="32">Surface</text><text x="405" y="143">Depth</text><text x="20" y="229">Illustration, not a dataset</text></g>
    <path d="M407 88v32m-5-6 5 7 5-7" stroke="#91dfca" fill="none" strokeWidth="2"/>
  </svg>;
}

function ToolDiagram() {
  return <div className="intro-paths" aria-label="Three ways to use Depth Atlas">
    <div><Box/><strong>Explore</strong><span>See below the surface</span></div>
    <div><Radio/><strong>Compare</strong><span>Check real measurements</span></div>
    <div><Waves/><strong>Experiment</strong><span>Follow simulated particles</span></div>
  </div>;
}

function StartDiagram() {
  return <div className="intro-start" aria-label="Open the cutaway, inspect a value, save your investigation">
    <div><span>1</span><Box/><strong>Open cutaway</strong></div><ArrowRight className="intro-link"/>
    <div><span>2</span><MousePointer2/><strong>Click to inspect</strong></div><ArrowRight className="intro-link"/>
    <div><span>3</span><Bookmark/><strong>Save your finding</strong></div>
  </div>;
}

export function Introduction({ onClose, returnFocus }: { onClose: () => void; returnFocus: RefObject<HTMLButtonElement | null> }) {
  const [step, setStep] = useState(0);
  const slide = slides[step];
  return <Dialog.Root open onOpenChange={open => { if (!open) onClose(); }}><Dialog.Portal>
    <Dialog.Overlay className="dialog-overlay intro-overlay"/>
    <Dialog.Content className="intro-dialog" onOpenAutoFocus={event => { event.preventDefault(); document.getElementById('intro-next')?.focus(); }} onCloseAutoFocus={event => { event.preventDefault(); (returnFocus.current ?? document.getElementById('study-case'))?.focus(); }}>
      <div className="intro-top"><span>DEPTH ATLAS</span><button onClick={onClose} className="intro-skip">Skip introduction <ArrowRight size={15}/></button></div>
      <div className="intro-visual" key={step}>{step === 0 ? <DepthDiagram/> : step === 1 ? <ToolDiagram/> : <StartDiagram/>}</div>
      <div className="intro-copy" aria-live="polite"><Dialog.Title>{slide.title}</Dialog.Title><Dialog.Description>{slide.text}</Dialog.Description></div>
      <p className="intro-context">Historical data. Model fields, observations and simulations are labelled separately.</p>
      <div className="intro-bottom"><div className="intro-progress" aria-label={`Introduction step ${step + 1} of ${slides.length}`}>
        {slides.map((s, index) => <span key={s.title} className={index === step ? 'current' : ''}/>)}<span>{step + 1} / {slides.length}</span>
      </div><div className="intro-actions">{step > 0 && <button className="secondary-button" aria-label="Back" onClick={() => setStep(s => s - 1)}><ArrowLeft size={16}/><span>Back</span></button>}
        <button id="intro-next" className="primary-button" onClick={() => step === slides.length - 1 ? onClose() : setStep(s => s + 1)}>{step === slides.length - 1 ? 'Start exploring' : 'Next'}<ArrowRight size={17}/></button></div></div>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
