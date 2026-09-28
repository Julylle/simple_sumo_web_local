import { useInputSeries } from "./useInputSeries";
import { useEffect, useState } from "react";
import { getCalibrationParameters, simulate } from "../api/client";
import type { Params, SimulationResult } from "../api/client";
import { defaultParameters } from "../config/simulation";

export interface SimulationRun extends SimulationResult {
  runtimeSeconds: number;
}

export function useSimulation() {
  const inputSeries = useInputSeries();
  const [lastSeries, setLastSeries] = useState("");
  const [parameters, setParameters] = useState<Params>(defaultParameters);
  const [lastParameters, setLastParameters] = useState<Params | null>(null);
  const [data, setData] = useState<SimulationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [calibrationDefaults, setCalibrationDefaults] = useState<Record<string, number> | null>(null);
  const [calibration, setCalibration] = useState<Record<string, string>>({});
  const [calibrationError, setCalibrationError] = useState("");
  const [calibrationAttempt, setCalibrationAttempt] = useState(0);
  const [lastCalibration, setLastCalibration] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setCalibrationError("");
    getCalibrationParameters(controller.signal).then(values => {
      if (controller.signal.aborted) return;
      setCalibrationDefaults(values);
      setCalibration(Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)])));
      if (values.qmlr_ratio !== undefined) setParameters(current => ({ ...current, mlr_ratio: values.qmlr_ratio }));
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setCalibrationError(error instanceof Error ? error.message : "Could not load parameters");
    });
    return () => controller.abort();
  }, [calibrationAttempt]);

  function updateCalibration(name: string, value: string) {
    setCalibration(current => ({ ...current, [name]: value }));
    if (name === "qmlr_ratio" && value.trim() && Number.isFinite(Number(value))) {
      setParameters(current => ({ ...current, mlr_ratio: Number(value) }));
    }
  }

  const dirty = JSON.stringify(inputSeries.ids) !== lastSeries || JSON.stringify(calibration) !== lastCalibration ||
    !lastParameters ||
    (Object.keys(parameters) as (keyof Params)[]).some(
      (key) => parameters[key] !== lastParameters[key],
    );

  function updateParameter(key: keyof Params, value: number) {
    if (key === "mlr_ratio" && calibrationDefaults?.qmlr_ratio !== undefined) setCalibration(current => ({ ...current, qmlr_ratio: String(value) }));
    setParameters((current) => ({
      ...current,
      [key]: value,
      ...(key === "do_mg_l" ? { tank3_do_mg_l: value, tank4_do_mg_l: value, tank5_do_mg_l: value } : {}),
    }));
  }

  async function run() {
    if (inputSeries.pending) { setError("Wait for Excel imports to finish."); return false; }
    const seriesSnapshot = JSON.stringify(inputSeries.ids);
    if (!calibrationDefaults) { setError("Load calibration parameters before running."); return false; }
    const invalid = Object.entries(calibration).find(([name, value]) =>
      !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || (name.startsWith("K") && Number(value) === 0));
    if (invalid) { setError(`Invalid calibration value: ${invalid[0]}`); return false; }
    const submittedCalibration = Object.fromEntries(Object.entries(calibration).map(([name, value]) => [name, Number(value)]));
    const calibrationSnapshot = JSON.stringify(calibration);
    setBusy(true);
    setError("");
    const submittedParameters = { ...parameters };
    const started = performance.now();
    try {
      const result = await simulate(submittedParameters, submittedCalibration, inputSeries.ids);
      setData({
        ...result,
        runtimeSeconds: (performance.now() - started) / 1000,
      });
      setLastParameters(submittedParameters);
      setLastCalibration(calibrationSnapshot);
      setLastSeries(seriesSnapshot);
      return true;
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Simulation failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setParameters({ ...defaultParameters, mlr_ratio: calibrationDefaults?.qmlr_ratio ?? defaultParameters.mlr_ratio });
    if (calibrationDefaults) setCalibration(Object.fromEntries(Object.entries(calibrationDefaults).map(([name, value]) => [name, String(value)])));
    setError("");
  }

  return { inputSeries, parameters, data, busy, error, dirty, updateParameter, run, reset,
    calibration, calibrationError, calibrationLoaded: calibrationDefaults !== null,
    updateCalibration, retryCalibration: () => setCalibrationAttempt(current => current + 1) };
}
