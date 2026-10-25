/** Match the conversions applied at the backend SUMO input boundary. */
export function sensorDisplayValue(column: string, raw: number): number {
  if (column === 'Sumo__Plant__Influent__param__Q' ||
      column === 'Sumo__Plant__Sideflowdivider3__param__Qpumped_target') return raw / 0.0417;
  if (['Sumo__Plant__Carbon1__param__Q', 'Sumo__Plant__Carbon2__param__Q',
       'Sumo__Plant__Metal1__param__Q'].includes(column)) return raw / 41.67;
  return raw;
}

/** Plotly date strings are wall-clock values: supply browser-local fields, not UTC ISO. */
export function localPlotTimestamp(time: number): string {
  const date = new Date(time);
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(),3)}`;
}
