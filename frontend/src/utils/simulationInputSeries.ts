import type { SumoResult } from '../components/sumoOutputs';

/** Use the completed model samples, already in model units, without rescaling.
 * The same timestamps drive the output charts. Never append the unprocessed
 * database backlog or the independent current OPC preview to this series.
 */
export function simulationInputSeries(result: SumoResult | null | undefined, keys: string[]) {
  const times = result?.time_h ?? [];
  return {
    time_h: times,
    sensor_timestamps: times.map((_, i) => result?.sensor_timestamps?.[i] ?? null),
    variables: Object.fromEntries(keys.map(key => [key, times.map((_, i) => {
      const value = result?.variables[key]?.[i];
      return typeof value === 'number' && Number.isFinite(value) ? value : null;
    })])),
  };
}
