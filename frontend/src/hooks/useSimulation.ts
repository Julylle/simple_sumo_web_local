import { useState } from 'react';
import { simulate } from '../api/client';
import type { Params, SimulationResult } from '../api/client';
import { defaultParameters } from '../config/simulation';

export interface SimulationRun extends SimulationResult {
  runtimeSeconds: number;
}

export function useSimulation() {
  const [parameters, setParameters] = useState<Params>(defaultParameters);
  const [lastParameters, setLastParameters] = useState<Params | null>(null);
  const [data, setData] = useState<SimulationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dirty = !lastParameters || (Object.keys(parameters) as (keyof Params)[])
    .some(key => parameters[key] !== lastParameters[key]);

  function updateParameter(key: keyof Params, value: number) {
    setParameters(current => ({ ...current, [key]: value }));
  }

  async function run() {
    setBusy(true);
    setError('');
    const submittedParameters = { ...parameters };
    const started = performance.now();
    try {
      const result = await simulate(submittedParameters);
      setData({ ...result, runtimeSeconds: (performance.now() - started) / 1000 });
      setLastParameters(submittedParameters);
      return true;
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : 'Simulation failed');
      return false;
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setParameters(defaultParameters);
    setError('');
  }

  return { parameters, data, busy, error, dirty, updateParameter, run, reset };
}
