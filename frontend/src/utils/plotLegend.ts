/** Fixed-width legend cells make Plotly's wrapping predictable at every card width. */
export function plotLegend(labels: string[], width: number, rightMargin: number) {
  const available = Math.max(80, width - 75 - rightMargin);
  const columns = Math.max(1, Math.floor(available / 260));
  const cellWidth = available / columns;
  // Leave room for the line symbol, padding and generous font-width variation.
  const chars = Math.max(6, Math.floor((cellWidth - 65) / 8));
  const wrapped = labels.map(label => {
    const lines: string[] = [];
    let rest = label;
    while (rest.length > chars) {
      const space = rest.lastIndexOf(' ', chars);
      const end = space > chars / 2 ? space : chars;
      lines.push(rest.slice(0, end));
      rest = rest.slice(end).trimStart();
    }
    lines.push(rest);
    return lines;
  });
  const lineCount = Math.max(1, ...wrapped.map(lines => lines.length));
  const rows = Math.ceil(labels.length / columns);
  return { names: wrapped.map(lines => lines.join('<br>')), cellWidth, fraction: 1 / columns - 0.001,
    height: rows * (lineCount * 16 + 18) + 16 };
}
