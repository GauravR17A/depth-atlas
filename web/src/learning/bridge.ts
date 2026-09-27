import { useEffect, useRef, useState } from 'react';
import { create } from 'zustand';
import type { ActivityId } from '../workspace/ToolMenu';

export type Fact = { label: string; value: string | number | null; unit?: string };
export type EvidenceLink = { label: string; href: string };
export type LearningSnapshot = {
  tool: ActivityId; caseId: string; status: 'ready' | 'loading' | 'empty' | 'error';
  title: string; kind: 'model' | 'observation' | 'comparison' | 'derived' | 'simulation' | 'source';
  facts: Fact[]; parameters: Record<string, string | number | boolean | null>;
  sources: EvidenceLink[]; limits: string[]; message?: string; commandId?: number;
};
export type LearningAction = { tool: ActivityId; action: string; value?: string | number; caseId?: string };
export type LearningCommand = LearningAction & { id: number };
type State = {
  activeTool: ActivityId; command: LearningCommand | null; snapshot: LearningSnapshot | null; commandError: string;
  activate: (tool: ActivityId) => void; issue: (action: LearningAction) => number; cancel: () => void;
  report: (snapshot: LearningSnapshot) => void;
};
let sequence = 0;
export const useLearning = create<State>((set, get) => ({
  activeTool: 'ocean', command: null, snapshot: null, commandError: '',
  activate: tool => { if (get().activeTool !== tool) set({ activeTool: tool, snapshot: null, command: null, commandError: '' }); },
  issue: action => { const id = ++sequence; set({ activeTool: action.tool, snapshot: null, command: { ...action, id }, commandError: '' }); return id; },
  cancel: () => set({ command: null, commandError: '' }),
  report: snapshot => { if (snapshot.tool === get().activeTool) set({ snapshot }); },
}));

// Tutorials call the same component handlers as the visible controls. They never
// synthesize a result or advance by scraping numbers from rendered text.
export function useLearningTool(
  tool: ActivityId, active: boolean, snapshot: LearningSnapshot,
  run: (command: LearningCommand, signal: AbortSignal) => boolean | Promise<boolean>,
) {
  const command = useLearning(s => s.command);
  const handler = useRef(run); handler.current = run;
  const [applied, setApplied] = useState(0);
  const handled = useRef(0), inFlight = useRef<AbortController | null>(null);
  const serialized = JSON.stringify(snapshot);
  useEffect(() => {
    if (!active) return;
    useLearning.getState().report({ ...JSON.parse(serialized) as LearningSnapshot, commandId: applied });
  }, [active, serialized, applied]);
  useEffect(() => {
    if (!active || !command || command.tool !== tool || handled.current === command.id) return;
    if (command.caseId && command.caseId !== snapshot.caseId) return;
    handled.current = command.id;
    const controller = new AbortController(); inFlight.current?.abort(); inFlight.current = controller;
    Promise.resolve().then(() => controller.signal.aborted ? false : handler.current(command, controller.signal)).then(accepted => {
      if (controller.signal.aborted || useLearning.getState().command?.id !== command.id) return;
      if (accepted) setApplied(command.id); else handled.current = 0;
    }).catch(error => {
      if (!controller.signal.aborted && useLearning.getState().command?.id === command.id)
        useLearning.setState({ commandError: error instanceof Error ? error.message : 'The action could not finish. Try again.' });
    });
  }); // Source readiness can change before a publishable result exists.
  useEffect(() => {
    if (!active || !command || command.tool !== tool) inFlight.current?.abort();
    return () => { inFlight.current?.abort(); };
  }, [active, command?.id, tool]);
}

export const modelSource = (id: string): EvidenceLink => ({ label: 'Case metadata and original sources', href: `/api/cases/${encodeURIComponent(id)}` });
export const factText = (fact: Fact) => `${fact.value === null ? 'Unavailable' : typeof fact.value === 'number' ? fact.value.toLocaleString('en-US', { maximumFractionDigits: 6 }) : fact.value}${fact.value !== null && fact.unit ? ` ${fact.unit}` : ''}`;
