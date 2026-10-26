import type { ComparisonSeries, SumoResult } from '../components/sumoOutputs';

export function mergeStoredSimulation(stored: ComparisonSeries | undefined, live: SumoResult): ComparisonSeries {
  const merged: ComparisonSeries = {};
  for (const [key, series] of Object.entries(stored ?? {})) {
    const points = new Map<number, number | null>();
    series.timestamps.forEach((stamp, i) => {
      const time = Date.parse(stamp);
      if (Number.isFinite(time)) points.set(time, series.values[i] ?? null);
    });
    live.sensor_timestamps?.forEach((stamp, i) => {
      const time = stamp ? Date.parse(stamp) : NaN;
      const value = live.variables[key]?.[i];
      if (Number.isFinite(time) && typeof value === 'number' && Number.isFinite(value)) points.set(time, value);
    });
    const entries = [...points].sort(([a], [b]) => a - b);
    merged[key] = {timestamps: entries.map(([time]) => new Date(time).toISOString()), values: entries.map(([, value]) => value)};
  }
  return merged;
}
