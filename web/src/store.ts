import { create } from 'zustand';

export const variables = {
  temperature: { label: 'Temperature', short: 'Heat through the water column' },
  salinity: { label: 'Salinity', short: 'Salt through the water column' },
  horizontal_kinetic_energy: { label: 'Kinetic energy', short: 'Horizontal flow only, derived from currents' },
  currents: { label: 'Currents', short: 'Direction and speed of ocean flow' },
} as const;

export type Variable = keyof typeof variables;
export type MapView = 'globe' | 'map';
type WorkspaceState = {
  regionId: string;
  variable: Variable;
  mapView: MapView;
  zoom: number;
  evidenceOpen: boolean;
  setRegion: (id: string) => void;
  setVariable: (variable: Variable) => void;
  setMapView: (view: MapView) => void;
  setZoom: (change: number) => void;
  toggleEvidence: () => void;
  resetView: () => void;
};

export const useWorkspace = create<WorkspaceState>((set) => ({
  regionId: 'bay-of-bengal', variable: 'temperature', mapView: 'globe', zoom: 1, evidenceOpen: false,
  setRegion: (regionId) => set({ regionId, zoom: 1 }),
  setVariable: (variable) => set({ variable }),
  setMapView: (mapView) => set({ mapView, zoom: 1 }),
  setZoom: (change) => set((state) => ({ zoom: Math.max(0.8, Math.min(1.8, Math.round((state.zoom + change) * 10) / 10)) })),
  toggleEvidence: () => set((state) => ({ evidenceOpen: !state.evidenceOpen })),
  resetView: () => set({ zoom: 1, mapView: 'globe' }),
}));
