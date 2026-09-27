import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTourAnchor } from './useTourAnchor';
import { useControlGlow } from './useControlGlow';
import { ToolsHandoff } from './ToolsHandoff';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeft, ArrowRight, BookOpen, Check, Compass, Crosshair, GraduationCap, HelpCircle, Layers3, LoaderCircle, Play, RotateCcw, X } from 'lucide-react';
import { coreCount, lessons, type TutorialMode } from './lessons';
import { featureTours, tourSteps, type FeatureTourId } from './featureTours';
import { FeatureTourPicker } from './FeatureTourPicker';
import { factText, useLearning, type LearningAction } from './bridge';
import './learning.css';

function OceanSketch(){return <svg viewBox="0 0 460 180" role="img" aria-label="Illustration of an ocean model, a sensor profile and a result, not a dataset">
  <path d="M25 55 118 18 210 55 118 98Z" fill="#577f8b" stroke="#9bd2ce"/><path d="M25 55v72l93 39V98M118 166l92-39V55" fill="#173e50" stroke="#76b9be"/>
  <path d="m26 82 92 39 92-39m-184 25 92 39 92-39" fill="none" stroke="#4b98a1"/>
  <path d="M160 54v83" stroke="#f1ba80" strokeWidth="3" strokeDasharray="4 4"/><circle cx="160" cy="52" r="6" fill="#f1ba80"/>
  <path d="M244 30v120h165" stroke="#76969f" fill="none"/><path d="m263 41 65 20-18 20 54 24 10 26" fill="none" stroke="#9ce5d1" strokeWidth="3"/>
  <g fill="#bed8df" fontSize="12"><text x="26" y="15">Model</text><text x="248" y="18">Sensor profile</text><text x="266" y="171">Read the result</text></g>
</svg>;}
export function LearningExperience({welcomeOpen,sourcesReady,onCloseWelcome,onAction,onExplain,onOpenTools}:{welcomeOpen:boolean;sourcesReady:boolean;onCloseWelcome:()=>void;onAction:(action:LearningAction)=>number;onExplain:()=>void;onOpenTools:()=>void}){
  const [mode,setMode]=useState<TutorialMode>('basic'),[step,setStep]=useState<number|null>(null),[run,setRun]=useState(0),[paused,setPaused]=useState(false),[page,setPage]=useState(0),[answer,setAnswer]=useState<number|null>(null),[boundary,setBoundary]=useState(false),[finished,setFinished]=useState(false),[slow,setSlow]=useState(false);
  const [toolsHint,setToolsHint]=useState(false);
  const [pickerOpen,setPickerOpen]=useState(false),[featureId,setFeatureId]=useState<FeatureTourId|null>(null);
  const feature=featureTours.find(tour=>tour.id===featureId);
  const sequence=feature?tourSteps(feature):lessons.map((_,i)=>i);
  const overlayOpen=welcomeOpen||pickerOpen;
  const snapshot=useLearning(s=>s.snapshot),command=useLearning(s=>s.command),commandError=useLearning(s=>s.commandError),activeTool=useLearning(s=>s.activeTool);
  const heading=useRef<HTMLHeadingElement>(null),lastApplied=useRef(''),issued=useRef(0),coach=useRef<HTMLElement>(null);
  const lesson=step===null?null:lessons[step];
  const ownsResult=Boolean(lesson&&snapshot?.tool===lesson.action.tool&&snapshot.commandId===issued.current&&command?.id===issued.current);
  const ready=ownsResult&&snapshot?.status==='ready';
  const error=commandError||(snapshot?.tool===lesson?.action.tool&&snapshot?.status==='error'?snapshot.message??'This source result could not be loaded.':'');
  const running=step!==null&&!finished;
  const {placement,modal,relocate}=useTourAnchor(coach,lesson&&!boundary&&!finished?lesson.target:'',`${step}:${run}:${ready}`,Boolean((running&&!paused||finished)&&!overlayOpen));
  useControlGlow(lesson?.target??'',running&&!paused&&!overlayOpen&&!boundary&&!modal);
  const saveHost=modal?.querySelector<HTMLElement>('[data-tutorial-save-guide]');
  function closeSave(){document.querySelector<HTMLButtonElement>('[aria-label="Close saved investigations"]')?.click();}
  function stop(){const completed=finished||boundary;setToolsHint(completed);closeSave();useLearning.getState().cancel();setStep(null);setPaused(false);setBoundary(false);setFinished(false);setPickerOpen(false);setFeatureId(null);onCloseWelcome();requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>(completed?'#workspace-tools':'[aria-label="Quick guide"]')?.focus());}
  function startAt(index:number,id:FeatureTourId|null=null){setToolsHint(false);setFeatureId(id);setPickerOpen(false);setFinished(false);setBoundary(false);setPaused(false);setStep(index);setRun(n=>n+1);onCloseWelcome();}
  function start(){startAt(0);}
  function showFeatures(){closeSave();useLearning.getState().cancel();setPickerOpen(true);}
  function closeFeatures(){setPickerOpen(false);setRun(n=>n+1);requestAnimationFrame(()=>{if(welcomeOpen)document.getElementById('start-learning')?.focus();else coach.current?.querySelector<HTMLButtonElement>('[data-feature-picker]')?.focus();});}
  useEffect(()=>{
    document.body.classList.toggle('tutorial-running',running&&!paused&&!overlayOpen);
    return()=>document.body.classList.remove('tutorial-running');
  },[running,paused,overlayOpen]);
  useEffect(()=>{
    if(step===null||paused||boundary||finished||overlayOpen||!sourcesReady)return;
    const identity=`${step}:${run}`;if(lastApplied.current===identity)return;lastApplied.current=identity;
    setPage(0);setAnswer(null);setSlow(false);
    const action=lessons[step].action;
    issued.current=onAction({...action,caseId:action.caseId??(action.tool==='climate'||action.tool==='wider'?undefined:'bay-bengal-2024-01')});
    requestAnimationFrame(()=>heading.current?.focus({preventScroll:true}));
  },[step,run,paused,boundary,finished,overlayOpen,sourcesReady,onAction]);
  useEffect(()=>{if(!running||paused||ready)return;const timer=setTimeout(()=>setSlow(true),15000);return()=>clearTimeout(timer);},[running,paused,ready,step,run]);
  useEffect(()=>{const current=useLearning.getState().command;if(running&&!paused&&issued.current&&current&&current.id!==issued.current)setPaused(true);},[command,running,paused]);
  useEffect(()=>{const current=useLearning.getState();if(running&&!paused&&issued.current&&!current.command&&current.activeTool!==lesson?.action.tool)setPaused(true);},[activeTool,command,running,paused,lesson]);
  useEffect(()=>()=>useLearning.getState().cancel(),[]);
  function next(){
    if(step===null)return;
    if(feature){const position=sequence.indexOf(step);if(position===sequence.length-1){setFinished(true);useLearning.getState().cancel();}else setStep(sequence[position+1]);return;}
    if(step===coreCount-1&&!boundary){setBoundary(true);return;}
    if(step===lessons.length-1){setFinished(true);useLearning.getState().cancel();return;}
    setBoundary(false);setStep(step+1);
  }
  function practice(){useLearning.getState().cancel();setPaused(true);}
  const progress=step===null?0:feature?`${sequence.indexOf(step)+1} / ${sequence.length}`:step<coreCount?`${step+1} / ${coreCount}`:`${step-coreCount+1} / ${lessons.length-coreCount}`;
  return <>
    <Dialog.Root open={welcomeOpen&&!pickerOpen} onOpenChange={open=>{if(!open)stop();}}><Dialog.Portal><Dialog.Overlay className="dialog-overlay intro-overlay"/><Dialog.Content className="learning-welcome" onOpenAutoFocus={event=>{event.preventDefault();document.getElementById('start-learning')?.focus();}} onCloseAutoFocus={event=>{event.preventDefault();if(step===null&&!pickerOpen)document.querySelector<HTMLButtonElement>('[aria-label="Quick guide"]')?.focus();}}>
      <div className="learn-topline"><span>DEPTH ATLAS · START HERE</span><button className="learn-text-button" onClick={stop}>Skip tutorial <ArrowRight size={15}/></button></div>
      <div className="learn-sketch"><OceanSketch/></div>
      <Dialog.Title>See it happen. Then try it.</Dialog.Title>
      <Dialog.Description>Find data on the globe, open the ocean at depth, then check a sensor reading. You choose when to move on.</Dialog.Description>
      <fieldset className="learn-mode-options"><legend>Choose your tutorial</legend>
        <label className={mode==='basic'?'selected':''}><input type="radio" name="tutorial-mode" value="basic" checked={mode==='basic'} onChange={()=>setMode('basic')}/><span><strong><Play size={16}/>Basic <small>Default</small></strong><span>What to click and how to read the output.</span></span></label>
        <label className={mode==='deep'?'selected':''}><input type="radio" name="tutorial-mode" value="deep" checked={mode==='deep'} onChange={()=>setMode('deep')}/><span><strong><GraduationCap size={18}/>In-depth</strong><span>The same actions, plus the concepts, methods and limits behind each feature.</span></span></label>
      </fieldset>
      <p className="learn-welcome-note">Starts with a prepared historical case and changes the visible settings. Saved investigations stay available.</p>
      <div className="learn-welcome-footer"><button className="learn-feature-teaser" onClick={showFeatures}><Compass size={21}/><span><strong>Explore extra feature tutorials</strong><small>Virtual particles, El Niño / La Niña and more</small></span><ArrowRight size={16}/></button><button id="start-learning" className="primary-button" onClick={start}>Start {mode==='basic'?'Basic':'In-depth'} tutorial <ArrowRight size={17}/></button></div>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
    {pickerOpen&&<FeatureTourPicker mode={mode} onMode={setMode} onBack={closeFeatures} onSelect={id=>{const tour=featureTours.find(item=>item.id===id)!;startAt(tourSteps(tour)[0],id);}} onAll={()=>startAt(coreCount)}/>}
    {running&&paused&&!overlayOpen&&<div className="learn-resume" role="region" aria-label="Paused tutorial"><span>Your turn. Explore freely.</span><button className="secondary-button" onClick={()=>{setPaused(false);setRun(n=>n+1);}}>Resume tutorial</button><button className="icon-button" aria-label="Exit tutorial" onClick={stop}><X size={16}/></button></div>}
    {running&&!paused&&!overlayOpen&&<div className="tour-scroll-space" aria-hidden="true"/>}
    {running&&!paused&&!overlayOpen&&!modal&&placement.target&&<div className="tour-spotlight" aria-hidden="true" style={placement.target}/>}
    {running&&!paused&&!overlayOpen&&lesson?.action.action==='save'&&saveHost&&createPortal(<div className="learn-save-hint" role="note"><strong>{lesson.id==='offline'?'Save, then choose Offline viewer':'Keep this investigation'}</strong><p>{lesson.id==='offline'?'Save on this browser, then use Offline viewer to download the supported charts and values. This is optional; the tutorial does not save or download for you.':'Saving keeps the applied settings and source evidence on this browser. Saving a supported imported profile also keeps its original file. It is optional for this tutorial.'}</p><button type="button" className="secondary-button" onClick={closeSave}>Close form and continue tutorial <ArrowRight size={15}/></button></div>,saveHost)}
    {(running&&!paused||finished)&&!overlayOpen&&<aside ref={coach} className="learning-coach" data-side={placement.side} data-ready={ready} data-complete={boundary||finished} data-target={lesson?.id} data-anchored={placement.found&&!placement.offscreen} style={{left:placement.left,top:placement.top,visibility:modal?'hidden':undefined}} aria-label={`${mode==='basic'?'Basic':'In-depth'} tutorial`}>
      {placement.found&&!placement.offscreen&&placement.side!=='none'&&<span className="learn-pointer" aria-hidden="true" style={placement.side==='left'||placement.side==='right'?{top:placement.arrow}:{left:placement.arrow}}/>}
      <div className="learn-coach-top"><span><BookOpen size={15}/>{mode==='basic'?'Basic':'In-depth'} tutorial</span><button className="learn-text-button" onClick={stop}>Skip <X size={14}/></button></div>
      {finished?<div className="learn-complete"><Check size={30}/><h2>{feature?`End of the ${feature.title} tour`:'You’re ready to explore.'}</h2><p>{feature?'Try the controls yourself, or choose another feature. Guide keeps these tutorials within reach.':'Each result keeps its source and limits. Revisit any feature whenever you need a hand.'}</p><button className="primary-button" data-feature-picker onClick={showFeatures}>Try another feature <Compass size={16}/></button><button className="secondary-button" onClick={stop}>Explore on my own <ArrowRight size={16}/></button><button className="learn-text-button" onClick={onExplain}>Explain my current result</button></div>:boundary?<div className="learn-complete"><Check size={30}/><h2>The essentials are covered.</h2><p>Where next? Release virtual particles, compare El Niño and La Niña, or plan a virtual expedition.</p><button className="primary-button" data-feature-picker onClick={showFeatures}>Choose an extra feature <Compass size={16}/></button><button className="secondary-button" onClick={()=>startAt(coreCount)}>Show me the extra labs <ArrowRight size={16}/></button><button className="learn-text-button" onClick={stop}>Explore on my own</button></div>:lesson&&<>
        <div className="learn-body" key={`${step}:${run}`}><div className="learn-step-label"><span>{feature?.title??lesson.chapter}</span><span>{progress}</span></div>
        <h2 ref={heading} tabIndex={-1}>{lesson.title}</h2>
        {mode==='deep'&&<nav className="learn-page-tabs" aria-label="Lesson detail"><button aria-pressed={page===0} onClick={()=>setPage(0)}>Watch</button><button aria-pressed={page===1} onClick={()=>setPage(1)}>Understand</button><button aria-pressed={page===2} onClick={()=>setPage(2)}>Method</button>{lesson.check&&<button aria-pressed={page===3} onClick={()=>setPage(3)}>Try a question</button>}</nav>}
        <div className="learn-page" key={`${step}:${run}:${page}`}>
          {placement.offscreen&&<button className="learn-return" onClick={relocate}><Crosshair size={15}/> Bring this view back</button>}
          {!placement.found&&!error&&<p className="learn-status" role="status">Finding this view...</p>}
          {page===0?<><p className="learn-action"><span aria-hidden="true">{ready?<Check size={17}/>:error?<HelpCircle size={17}/>:<LoaderCircle size={17} className="spin"/>}</span>{lesson.doing}</p>
            {error?<div className="learn-error" role="alert">{error}<button className="secondary-button" onClick={()=>setRun(n=>n+1)}>Retry step</button></div>:ready?<><p className="learn-output">{lesson.output}</p><dl className="learn-result" aria-label="Tutorial result">{snapshot!.facts.slice(0,2).map(f=><div key={f.label}><dt>{f.label}</dt><dd>{factText(f)}</dd></div>)}</dl>{snapshot?.parameters.graphics==='basic'&&<p className="learn-status">Basic 2D graphics are active. The source values remain available; no 3D effect is claimed.</p>}</>:<p className="learn-status" role="status">{slow?'Still waiting for the actual result. Retry, skip this step or leave the tutorial.':'Waiting for the app’s result. No made-up values.'}</p>}
          </>:page===1?<><div className="learn-concept-mark"><Layers3 size={30}/><span>What it means</span></div><p>{lesson.concept}</p><button className="learn-text-button" onClick={()=>setPage(2)}>How it works <ArrowRight size={15}/></button></>:page===2?<><p>{lesson.how}</p><div className="learn-limit"><strong>What it cannot tell us</strong><p>{lesson.limit}</p></div></>:lesson.check?<div className="learn-check"><p>{lesson.check.question}</p>{lesson.check.options.map((option,i)=><button className="secondary-button" aria-pressed={answer===i} key={option} onClick={()=>setAnswer(i)}>{option}</button>)}{answer!==null&&<p role="status"><strong>{answer===lesson.check.answer?'That’s right.':'Let’s look at it again.'}</strong> {lesson.check.why}</p>}<small>Optional question. Your answers are not stored.</small></div>:null}
        </div>
        <div className="learn-small-actions"><button className="learn-text-button" onClick={relocate}>Find this view <Crosshair size={14}/></button><button className="learn-text-button" disabled={!ready} onClick={onExplain}>Explain result</button><button className="learn-text-button" aria-label="Replay tutorial step" onClick={()=>setRun(n=>n+1)}><RotateCcw size={14}/>Replay</button></div></div>

        <div className="learn-browse"><details className="learn-contents"><summary>Choose a lesson</summary><div>{sequence.map((i,pos)=><button key={lessons[i].id} aria-current={i===step?'step':undefined} onClick={event=>{event.currentTarget.closest('details')?.removeAttribute('open');setStep(i);setRun(n=>n+1);}}>{pos+1}. {lessons[i].title}</button>)}</div></details><button className="learn-text-button" data-feature-picker onClick={showFeatures}>Extra features <Compass size={14}/></button></div>
        <div className="learn-navigation"><button className="icon-button" aria-label="Previous tutorial step" disabled={step===sequence[0]} onClick={()=>setStep(sequence[Math.max(0,sequence.indexOf(step!)-1)])}><ArrowLeft size={17}/></button><button className="secondary-button" onClick={practice}>Try it myself</button><button className="primary-button tutorial-next-glow" disabled={!ready&&!error&&!slow} onClick={next}>{error||slow&&!ready?'Skip step':'Next'}<ArrowRight size={16}/></button></div>
      </>}
    </aside>}
    {toolsHint&&!overlayOpen&&<ToolsHandoff onOpen={onOpenTools} onDismiss={()=>setToolsHint(false)}/>}
  </>;
}
