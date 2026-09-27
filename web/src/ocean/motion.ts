/** Display-only easing. Scientific coordinates and values never pass through it. */
export function transitionValue(from: number, to: number, elapsed: number, duration: number) {
  const t = duration <= 0 ? 1 : Math.max(0, Math.min(1, elapsed / duration));
  return from + (to - from) * (t * t * (3 - 2 * t));
}
