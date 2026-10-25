/** Pack whole, single-line legend entries by their measured text width. */
export function plotLegend(labels: string[], width: number, rightMargin: number,
  measure: (label: string) => number = label => label.length * 7) {
  // Plotly includes a line symbol and horizontal padding for each entry.
  const entries = labels.map(label => Math.ceil(measure(label)) + 52);
  const available = Math.max(80, width - 75 - rightMargin, ...entries);
  let rows = labels.length ? 1 : 0;
  let used = 0;
  for (const size of entries) {
    if (used > 0 && used + size > available) { rows++; used = 0; }
    used += size;
  }
  return { names: labels, plotWidth: Math.max(width, available + 75 + rightMargin),
    height: rows * 23 + 12 };
}
