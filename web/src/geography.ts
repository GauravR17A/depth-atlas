export function normalizedLongitude(value: number) {
  if (value >= -180 && value < 180) return Object.is(value, -0) ? 0 : value;
  const result = ((value + 180) % 360 + 360) % 360 - 180;
  return Object.is(result, -0) ? 0 : result;
}

export function longitudeLabel(value: number, digits = 2) {
  const longitude = normalizedLongitude(value);
  if (Math.abs(longitude) === 180) return `${Math.abs(longitude).toFixed(digits)}°`;
  return `${Math.abs(longitude).toFixed(digits)}° ${longitude < 0 ? 'W' : 'E'}`;
}

export function latitudeLabel(value: number, digits = 2) {
  return `${Math.abs(value).toFixed(digits)}° ${value < 0 ? 'S' : 'N'}`;
}

export function longitudeOnAxis(value: number, axis: number[]) {
  const center = (axis[0] + axis.at(-1)!) / 2;
  return value + 360 * Math.round((center - value) / 360);
}

// Place the cut in the largest empty longitude arc before averaging positions.
// This preserves nearby instruments on opposite sides of the date line.
export function longitudeContext(values: number[]) {
  if (!values.length) return { center: 0, halfSpan: 0 };
  const sorted = values.map(value => (value % 360 + 360) % 360).sort((a, b) => a - b);
  let gap = -1, start = sorted[0];
  for (let index = 0; index < sorted.length; index++) {
    const next = index === sorted.length - 1 ? sorted[0] + 360 : sorted[index + 1];
    if (next - sorted[index] > gap) { gap = next - sorted[index]; start = sorted[(index + 1) % sorted.length]; }
  }
  const unwrapped = sorted.map(value => value < start ? value + 360 : value);
  const center = unwrapped.reduce((sum, value) => sum + value, 0) / unwrapped.length;
  return { center: normalizedLongitude(center), halfSpan: Math.max(...unwrapped.map(value => Math.abs(value - center))) };
}
