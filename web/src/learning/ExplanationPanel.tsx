import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowRight, BookOpen, ExternalLink, HelpCircle, X } from 'lucide-react';
import type { CaseManifest } from '../contracts';
import { safeSource } from '../instruments/contracts';
import { factText, useLearning, type LearningAction } from './bridge';
import { explainSnapshot, glossary, interpretRequest, type RequestPlan } from './explain';

export function ExplanationPanel({open,onClose,manifest,onAction}:{open:boolean;onClose:()=>void;manifest?:CaseManifest;onAction:(action:LearningAction)=>void}){
  const snapshot=useLearning(s=>s.snapshot),explanation=explainSnapshot(snapshot);
  const [input,setInput]=useState(''),[answer,setAnswer]=useState<RequestPlan|null>(null),[term,setTerm]=useState('model');
  useEffect(()=>{setAnswer(null);},[snapshot?.caseId]);
  function ask(value=input){setInput(value);setAnswer(interpretRequest(value,manifest));}
  return <Dialog.Root open={open} onOpenChange={value=>{if(!value)onClose();}}><Dialog.Portal><Dialog.Overlay className="dialog-overlay"/><Dialog.Content className="explanation-panel">
    <div className="explain-heading"><div><span className="eyebrow">READ THE EVIDENCE</span><Dialog.Title><BookOpen size={22}/>Explain this result</Dialog.Title></div><Dialog.Close asChild><button className="icon-button" aria-label="Close explanation"><X size={19}/></button></Dialog.Close></div>
    <Dialog.Description>Short explanations from the app’s current results and reviewed definitions. No external language model is connected.</Dialog.Description>
    <section className="explain-current"><span className="learn-kind">{snapshot?.kind??'No result'}{snapshot?.caseId?` · ${snapshot.caseId}`:''}</span><h3>{explanation.title}</h3><p>{explanation.body}</p>
      {explanation.available&&snapshot&&<><dl className="explain-facts">{snapshot.facts.map(f=><div key={f.label}><dt>{f.label}</dt><dd>{factText(f)}</dd></div>)}</dl><div className="explain-limits"><strong>Keep in mind</strong>{snapshot.limits.map(line=><p key={line}>{line}</p>)}</div><div className="explain-sources">{snapshot.sources.filter(s=>s.href.startsWith('/api/')||s.href.startsWith('/data-access')||safeSource(s.href)).map(s=><a key={s.href} href={s.href} target="_blank" rel="noreferrer">{s.label}<ExternalLink size={13}/></a>)}</div><details><summary>Applied parameters</summary><dl className="explain-facts">{Object.entries(snapshot.parameters).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{String(value??'Unavailable')}</dd></div>)}</dl></details></>}
    </section>
    <form className="explain-question" onSubmit={e=>{e.preventDefault();ask();}}><label htmlFor="explain-request">Ask a supported question or prepare a view</label><div><input id="explain-request" maxLength={300} value={input} onChange={e=>{setInput(e.target.value);setAnswer(null);}} placeholder="Show temperature at 100 m"/><button className="primary-button" disabled={!input.trim()}>Check request <ArrowRight size={16}/></button></div><small>Bounded requests, not an open-ended chatbot. Requests stay in this tab.</small></form>
    <div className="explain-suggestions">{['Explain this result','What is a residual?','Show temperature at 100 m','Open cutaway'].map(q=><button className="secondary-button" key={q} onClick={()=>ask(q)}>{q}</button>)}</div>
    {answer&&<section className="explain-answer" aria-label="Request answer" aria-live="polite">{answer.kind==='plan'?<><h3>Ready to apply: {answer.label}</h3><p>Review the query. Nothing has changed yet.</p><dl className="explain-facts">{Object.entries(answer.parameters).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{v}</dd></div>)}</dl><button className="primary-button" onClick={()=>{const checked=interpretRequest(input,manifest);if(checked.kind!=='plan'){setAnswer(checked);return;}onAction(checked.action);onClose();}}>Apply this query <ArrowRight size={15}/></button></>:answer.kind==='unsupported'?<><h3>Not supported</h3><p>{answer.message}</p></>:answer.kind==='definition'?<><h3>{answer.term}</h3><p>{answer.text}</p></>:<><h3>{explanation.title}</h3><p>{explanation.body}</p><p>The current values, sources and limits are shown above.</p></>}</section>}
    <details className="explain-glossary"><summary><HelpCircle size={16}/>Understand a concept</summary><label>Concept<select aria-label="Explanation concept" value={term} onChange={e=>setTerm(e.target.value)}>{Object.keys(glossary).map(key=><option key={key} value={key}>{key}</option>)}</select></label><p>{glossary[term]}</p><p className="muted">Definitions explain terminology. They do not supply additional measurements or establish a forecast.</p></details>
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
