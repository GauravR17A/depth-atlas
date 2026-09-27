import { lessons } from './lessons';

// Each entry starts with an action that prepares its own real source result.
// In particular, particle playback is always preceded by the calculation.
export const featureTours = [
  { id: 'chlorophyll', title: 'Find chlorophyll', question: 'Where was it measured, and at what depth?', description: 'Locate a real BGC float, read its profile and open the save form.', kind: 'Observation', lessonIds: ['chlorophyll-location','chlorophyll-profile','save-profile'] },
  { id: 'imports', title: 'Import and review', question: 'Can I bring my own observations?', description: 'Preview a source file, then review a small batch.', kind: 'Data workflow', lessonIds: ['import-preview','import-batch'] },
  { id: 'builder', title: 'Build an investigation', question: 'How do these tools fit together?', description: 'Follow the data-to-comparison workflow.', kind: 'Guided workflow', lessonIds: ['builder-start','builder-compare'] },
  { id: 'support', title: 'Support and sensitivity', question: 'Which readings support this shape?', description: 'Inspect coverage gaps and a stricter matching rule.', kind: 'Derived evidence', lessonIds: ['support','support-sensitivity'] },
  { id: 'offline', title: 'Save for offline use', question: 'Can I keep this finding without internet?', description: 'Open the save form and find the offline download.', kind: 'Saved evidence', lessonIds: ['offline'] },
  { id: 'publication', title: 'Dataset updates', question: 'How old is this data release?', description: 'Check source dates and the publication status.', kind: 'Source provenance', lessonIds: ['publication'] },
  { id: 'drift', title: 'Drift', question: 'Where would a virtual particle go?', description: 'Release particles, then play their calculated paths.', kind: 'Simulation', lessonIds: ['drift', 'drift-play'] },
  { id: 'climate', title: 'El Niño & La Niña', question: 'What changes in the Pacific?', description: 'Compare the supported warm and cool historical seasons.', kind: 'Historical comparison', lessonIds: ['climate', 'la-nina'] },
  { id: 'heat', title: 'Heat & Depth', question: 'What does a warm surface hide?', description: 'Read a surface heat event and its available depth evidence.', kind: 'Derived analysis', lessonIds: ['heat'] },
  { id: 'structures', title: 'Ocean structures', question: 'Where does warm water connect?', description: 'Find connected regions with a stated temperature rule.', kind: 'Derived analysis', lessonIds: ['structures'] },
  { id: 'expedition', title: 'Virtual expedition', question: 'Where would you measure next?', description: 'Build a station plan with a limited sampling budget.', kind: 'Simulation', lessonIds: ['expedition'] },
  { id: 'evolution', title: 'Feature evolution', question: 'How do ocean shapes change?', description: 'Follow overlaps, splits and merges between model frames.', kind: 'Derived analysis', lessonIds: ['evolution'] },
  { id: 'blackout', title: 'Sensor blackout', question: 'What if one sensor were missing?', description: 'Remove a profile from the comparison and inspect the loss.', kind: 'Evidence rehearsal', lessonIds: ['blackout'] },
  { id: 'wider', title: 'Explore other regions', question: 'What can we see elsewhere?', description: 'Open a bounded source region and check its coverage.', kind: 'Source exploration', lessonIds: ['wider'] },
] as const;
export type FeatureTour = typeof featureTours[number];
export type FeatureTourId = FeatureTour['id'];
export const tourSteps = (tour: FeatureTour) => tour.lessonIds.map(id => lessons.findIndex(lesson => lesson.id === id));
