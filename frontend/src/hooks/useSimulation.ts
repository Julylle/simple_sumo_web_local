import { useInputSeries } from "./useInputSeries";
import { useEffect, useState } from "react";
import { autoCalibrate, getCalibrationParameters, simulate, uploadCalibrationMeasurements } from "../api/client";
import type { Params, SimulationResult, MeasurementUpload, CalibrationComparison, OxygenMode } from "../api/client";
import { defaultParameters } from "../config/simulation";
import { useSimulationMeasurements } from "./useSimulationMeasurements";

export interface SimulationRun extends SimulationResult {
  runtimeSeconds: number;
}

export function useSimulation() {
  const inputSeries = useInputSeries();
  const simulationMeasurements = useSimulationMeasurements();
  const [lastSeries, setLastSeries] = useState("");
  const [parameters, setParameters] = useState<Params>(defaultParameters);
  const [lastParameters, setLastParameters] = useState<Params | null>(null);
  const [data, setData] = useState<SimulationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [autoCalibrationBusy, setAutoCalibrationBusy] = useState(false);
  const [autoCalibrationError, setAutoCalibrationError] = useState("");
  const [autoCalibrationComplete, setAutoCalibrationComplete] = useState(false);
  const [oxygenMode, setOxygenMode] = useState<OxygenMode>("calculated_kla");
  const [doSetpoints, setDoSetpoints] = useState(["0", "0", "1.6", "2.0", "2.2"]);
  const [measurements, setMeasurements] = useState<MeasurementUpload | null>(null);
  const [measurementBusy, setMeasurementBusy] = useState(false);
  const [measurementError, setMeasurementError] = useState("");
  const [comparison, setComparison] = useState<CalibrationComparison | null>(null);
  const [calibrationDefaults, setCalibrationDefaults] = useState<Record<string, number> | null>(null);
  const [calibration, setCalibration] = useState<Record<string, string>>({});
  const [autoParameters, setAutoParameters] = useState<Record<string, string>>({});
  const [parameterActionStatus, setParameterActionStatus] = useState("");
  const [simulationParameterStatus, setSimulationParameterStatus] = useState("");
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
      setAutoParameters(Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)])));
      if (values.qmlr_ratio !== undefined) setParameters(current => ({ ...current, mlr_ratio: values.qmlr_ratio }));
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setCalibrationError(error instanceof Error ? error.message : "Could not load parameters");
    });
    return () => controller.abort();
  }, [calibrationAttempt]);

  function updateCalibration(name: string, value: string) {
    setSimulationParameterStatus("");
    setCalibration(current => ({ ...current, [name]: value }));
    if (name === "qmlr_ratio" && value.trim() && Number.isFinite(Number(value))) {
      setParameters(current => ({ ...current, mlr_ratio: Number(value) }));
    }
  }

  function updateAutoParameter(name: string, value: string) {
    setAutoParameters(current => ({ ...current, [name]: value }));
    setAutoCalibrationComplete(false);
    setParameterActionStatus("");
  }

  function updateOxygenMode(value: OxygenMode) {
    if (value === oxygenMode) return;
    setOxygenMode(value);
    setAutoCalibrationComplete(false);
    setParameterActionStatus("");
  }

  function updateDoSetpoint(tank: number, value: string) {
    setDoSetpoints(current => current.map((entry, index) => index === tank ? value : entry));
    setAutoCalibrationComplete(false);
    setParameterActionStatus("");
  }

  function saveCalibratedParameters() {
    if (!autoCalibrationComplete || busy || autoCalibrationBusy) return;
    const values = Object.fromEntries(Object.entries(autoParameters).map(([name, value]) => [name, Number(value)]));
    const url = URL.createObjectURL(new Blob([JSON.stringify({ calibration_parameters: values,
      oxygen_mode: oxygenMode, ...(oxygenMode === "do_setpoint" ? { do_setpoints: doSetpoints.map(Number) } : {}) }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "calibrated_parameters.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setParameterActionStatus("Parameter file downloaded: calibrated_parameters.json.");
  }

  function applyCalibratedParameters() {
    if (!autoCalibrationComplete || busy || autoCalibrationBusy) return false;
    setCalibration({ ...autoParameters });
    if (autoParameters.qmlr_ratio !== undefined) setParameters(current => ({ ...current, mlr_ratio: Number(autoParameters.qmlr_ratio) }));
    setSimulationParameterStatus("Calibrated parameters applied. Run simulation to update the curves.");
    setParameterActionStatus("Parameters updated in Simulation.");
    return true;
  }

  async function uploadMeasurements(file: File) {
    if (busy || autoCalibrationBusy || measurementBusy) return;
    setMeasurementError("");
    setAutoCalibrationError("");
    setMeasurements(null);
    setComparison(null);
    setAutoCalibrationComplete(false);
    setParameterActionStatus("");
    if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 5 * 1024 * 1024) {
      setMeasurementError("Choose an .xlsx workbook under 5 MB.");
      return;
    }
    setMeasurementBusy(true);
    try { setMeasurements(await uploadCalibrationMeasurements(file)); }
    catch (error: unknown) { setMeasurementError(error instanceof Error ? error.message : "Upload failed"); }
    finally { setMeasurementBusy(false); }
  }

  async function runAutoCalibration() {
    if (busy || autoCalibrationBusy || measurementBusy || !calibrationDefaults) return;
    if (!measurements) { setAutoCalibrationError("Upload measured data before running auto-calibration."); return; }
    setParameterActionStatus("");
    setAutoCalibrationComplete(false);
    setAutoCalibrationError("");
    setComparison(null);
    const invalid = Object.entries(autoParameters).find(([name, value]) =>
      !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || (name.startsWith("K") && Number(value) === 0));
    if (invalid) { setAutoCalibrationError(`Invalid calibration value: ${invalid[0]}`); return; }
    if (oxygenMode === "do_setpoint" && doSetpoints.some(value => !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 8)) {
      setAutoCalibrationError("DO setpoints must be between 0 and 8 mg/L for all five tanks."); return;
    }
    setAutoCalibrationBusy(true);
    try {
      const result = await autoCalibrate(Object.fromEntries(Object.entries(autoParameters).map(([name, value]) => [name, Number(value)])), measurements.id,
        oxygenMode, oxygenMode === "do_setpoint" ? doSetpoints.map(Number) : [0, 0, 1.6, 2.0, 2.2]);
      const values = result.calibration_parameters;
      setComparison(result.comparison);
      setAutoParameters(Object.fromEntries(Object.entries(values).map(([name, value]) => [name, String(value)])));
      setParameterActionStatus("");
      setAutoCalibrationComplete(true);
    } catch (error: unknown) {
      setAutoCalibrationError(error instanceof Error ? error.message : "Auto-calibration failed");
    } finally {
      setAutoCalibrationBusy(false);
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
    if (busy || autoCalibrationBusy) return false;
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
      setSimulationParameterStatus("");
      return true;
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Simulation failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setSimulationParameterStatus("");
    setParameters({ ...defaultParameters, mlr_ratio: calibrationDefaults?.qmlr_ratio ?? defaultParameters.mlr_ratio });
    if (calibrationDefaults) setCalibration(Object.fromEntries(Object.entries(calibrationDefaults).map(([name, value]) => [name, String(value)])));
    setError("");
  }

  return { inputSeries, parameters, data, busy: busy || autoCalibrationBusy, error, dirty, updateParameter, run, reset,
    runAutoCalibration, autoCalibrationBusy, autoCalibrationError, autoCalibrationComplete,
    measurements, measurementBusy, measurementError, uploadMeasurements, comparison,
    autoParameters, updateAutoParameter, saveCalibratedParameters, applyCalibratedParameters,
    oxygenMode, doSetpoints, updateOxygenMode, updateDoSetpoint,
    parameterActionStatus, simulationParameterStatus, simulationMeasurements,
    calibration, calibrationError, calibrationLoaded: calibrationDefaults !== null,
    updateCalibration, retryCalibration: () => setCalibrationAttempt(current => current + 1) };
}
