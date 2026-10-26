import { useEffect, useState } from 'react';
import type { ComparisonSeries } from '../components/sumoOutputs';

type Comparisons = {stored_series?: ComparisonSeries; database?: string; run_id: string; series: ComparisonSeries; aggregation_seconds: number | null; error?: string};
export function useSensorComparisons(runId: string | undefined, hasSamples: boolean, intervalMinutes = 1) {
  const [value, setValue] = useState<Comparisons>();
  useEffect(() => {
    if (!runId || !hasSamples) return;
    let active = true, pending = false;
    const controller = new AbortController();
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await fetch(`/api/sumo/live/comparisons?run_id=${encodeURIComponent(runId)}`, {signal: controller.signal});
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw Error(typeof body?.detail === 'string' ? body.detail : 'Sensor comparisons unavailable. Check collector/database access.');
        }
        const next: Comparisons = await response.json();
        if (active && next.run_id === runId) setValue(next);
      } catch (error) {
        if (active) setValue({run_id: runId, series: {}, aggregation_seconds: null, error: String(error)});
      } finally { pending = false; }
    };
    void poll();
    // Comparison queries are independent of the two-second model-result poll.
    const timer = setInterval(() => void poll(), Math.max(60, intervalMinutes * 60) * 1000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [runId, hasSamples, intervalMinutes]);
  return value?.run_id === runId ? value : undefined;
}
