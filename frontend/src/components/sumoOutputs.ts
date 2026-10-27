export type OutputOption = { key: string; label: string; unit: string; compareTo?: string };
export type ComparisonSeries = Record<string, {timestamps: string[]; values: (number | null)[]}>;
export type SumoResult = {simulation_series?: ComparisonSeries; comparison_series?: ComparisonSeries; sensor_timestamps?: (string | null)[]; time_h: number[]; variables: Record<string, (number | null)[]>; input_columns?: string[] };
export const sumoOutputColors = ['#2563eb', '#8b5cf6', '#d97706', '#059669', '#e11d48', '#0891b2', '#c026d3', '#65a30d', '#ea580c', '#475569', '#4f46e5', '#0d9488'];
export const pollutantOptions: OutputOption[] = ['Effluent1', 'CSTR3_10', 'CSTR4_10'].flatMap(tank =>
  ['SNHx', 'SNOx', 'TCOD', 'TP'].map(p => ({key: `Sumo__Plant__${tank}__${p}`, label: `${tank} ${p}`, unit: 'mg/L'})));
export const doOptions: OutputOption[] = [3, 4].flatMap(line => Array.from({length: 6}, (_, i) => ({
  key: `Sumo__Plant__CSTR${line}_${i + 5}__SO2`, label: `CSTR${line}_${i + 5} SO2`, unit: 'mg/L',
})));

// Realtime-only choices: keep Offline SUMO's existing output options unchanged.
export const realtimePollutantOptions: OutputOption[] = [
  ...pollutantOptions.filter(option => !/CSTR.*__(TCOD|TP)$/.test(option.key)),
  ...[3,4].flatMap(lane => ['SNOx','SNHx'].map(name => ({
    key: `Sumo__Plant__CSTR${lane}_4__${name}`, label: `CSTR${lane}_4 ${name}`, unit: 'mg/L',
  }))),
  ...['CSTR3_4','CSTR3_10'].map(tank => ({
    key: `sensor:Sumo__Plant__${tank}__SNOx`, label: `${tank} nitrate · sensor`, unit: 'mg/L',
    compareTo: `Sumo__Plant__${tank}__SNOx`,
  })),
];

// Lab observations remain separate from model outputs and model inputs.
export const realtimeSolidsOptions: OutputOption[] = [3,4].flatMap(lane =>
  ([['MLSS','XTSS','mg TSS/L'],['MLVSS','XVSS','mg VSS/L']] as const).flatMap(([label,variable,unit]) => {
    const key=`Sumo__Plant__CSTR${lane}_10__${variable}`;
    return [
      {key,label:`CSTR${lane}_10 ${label} · simulation`,unit},
      {key:`lab:${key}`,label:`CSTR${lane}_10 ${label} · lab`,unit,compareTo:key},
    ];
  }));
