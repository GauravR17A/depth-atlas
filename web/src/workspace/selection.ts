/** Source sample IDs, not list offsets or approximate model depths. */
export type SharedSample = { profileId: string; sampleIndex: number; variable: string; origin: 'profile' | 'comparison' | 'support' };

export function selectedOffset(selection: SharedSample | undefined, profileId: string | undefined, indices: number[], fallback: number) {
  const index = selection && selection.profileId === profileId ? indices.indexOf(selection.sampleIndex) : -1;
  return index >= 0 ? index : Math.max(0, Math.min(fallback, indices.length - 1));
}
