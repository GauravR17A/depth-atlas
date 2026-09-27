/** Project a horizontal velocity onto a lon/lat plot before normalizing its glyph.
 * Longitude degrees shrink physically with cos(latitude); the plot axes may have
 * different pixel scales. This changes direction on screen, never source speed.
 */
export function mapVector(
  east: number, north: number, latitude: number,
  longitudeSpan: number, latitudeSpan: number,
  plotWidth: number, plotHeight: number, length = 14,
): [number, number] | null {
  if (![east, north, latitude, longitudeSpan, latitudeSpan, plotWidth, plotHeight, length].every(Number.isFinite)) return null;
  if (longitudeSpan <= 0 || latitudeSpan <= 0 || plotWidth <= 0 || plotHeight <= 0 || length <= 0 || Math.abs(latitude) >= 90) return null;
  if (Math.hypot(east, north) < 1e-8) return null;
  const cosine = Math.cos(latitude * Math.PI / 180);
  const dx = east * plotWidth / (longitudeSpan * cosine);
  const dy = -north * plotHeight / latitudeSpan;
  const magnitude = Math.hypot(dx, dy);
  if (!Number.isFinite(magnitude) || magnitude === 0) return null;
  return [length * dx / magnitude, length * dy / magnitude];
}
