export type AxisName = 'xaxis' | 'yaxis' | 'yaxis2';
type Bound = number | string;
export type Viewport = Partial<Record<AxisName, [Bound, Bound]>>;
const axes: AxisName[] = ['xaxis', 'yaxis', 'yaxis2'];
const valid = (value: unknown): value is Bound =>
  typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value));

/** Retain explicit user ranges across live samples, resize and trace changes. */
export function updateViewport(current: Viewport, event: Record<string, unknown>): Viewport {
  let next = current;
  for (const axis of axes) {
    if (event[`${axis}.autorange`] === true) {
      if (next[axis]) { next = { ...next }; delete next[axis]; }
      continue;
    }
    const range = event[`${axis}.range`];
    const lower = Array.isArray(range) ? range[0] : event[`${axis}.range[0]`] ?? current[axis]?.[0];
    const upper = Array.isArray(range) ? range[1] : event[`${axis}.range[1]`] ?? current[axis]?.[1];
    if (valid(lower) && valid(upper) && (lower !== current[axis]?.[0] || upper !== current[axis]?.[1])) {
      next = { ...next, [axis]: [lower, upper] };
    }
  }
  return next;
}

export function axisViewport(viewport: Viewport, axis: AxisName) {
  const range = viewport[axis];
  // Plotly may mutate layout objects. Never hand it the state-owned range array.
  return range ? { autorange: false as const, range: [...range] as [Bound, Bound] } : { autorange: true as const };
}
