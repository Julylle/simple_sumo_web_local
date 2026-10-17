export type OutputOption = { key: string; label: string; unit: string };
export type SumoResult = { time_h: number[]; variables: Record<string, number[]>; input_columns?: string[] };
export const sumoOutputColors = ['#2563eb', '#8b5cf6', '#d97706', '#059669', '#e11d48', '#0891b2', '#c026d3', '#65a30d', '#ea580c', '#475569', '#4f46e5', '#0d9488'];
export const pollutantOptions: OutputOption[] = ['Effluent1', 'CSTR3_10', 'CSTR4_10'].flatMap(tank =>
  ['SNHx', 'SNOx', 'TCOD'].map(p => ({key: `Sumo__Plant__${tank}__${p}`, label: `${tank} ${p}`, unit: 'mg/L'})));
export const doOptions: OutputOption[] = [3, 4].flatMap(line => Array.from({length: 6}, (_, i) => ({
  key: `Sumo__Plant__CSTR${line}_${i + 5}__SO2`, label: `CSTR${line}_${i + 5} SO2`, unit: 'mg/L',
})));
