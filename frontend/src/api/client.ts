export interface Params {
  use_do_setpoint: number;
  flow_m3_d: number;
  influent_cod_mg_l: number;
  influent_nh4_mg_l: number;
  do_mg_l: number;
  srt_d: number;
  duration_h: number;
  tank1_volume_m3: number;
  tank1_do_mg_l: number;
  tank2_volume_m3: number;
  tank2_do_mg_l: number;
  tank3_volume_m3: number;
  tank3_do_mg_l: number;
  tank4_volume_m3: number;
  tank4_do_mg_l: number;
  tank5_volume_m3: number;
  tank5_do_mg_l: number;
  mlr_ratio: number;
  ras_ratio: number;
}

export interface SimulationResult {
  variables: Record<string, number[]>;
  time_h: number[];
  nh4_mg_l: number[];
  cod_mg_l: number[];
  n2o_index: number[];
}

export async function getCalibrationParameters(signal?: AbortSignal): Promise<Record<string, number>> {
  const response = await fetch("/api/calibration-parameters", { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`Could not load calibration parameters (${response.status})`);
  return response.json();
}

export async function simulate(params: Params, calibrationParameters: Record<string, number> = {}, inputSeries: Record<string, string> = {}): Promise<SimulationResult> {
  const response = await fetch("/api/simulation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...params, calibration_parameters: calibrationParameters, input_series: inputSeries }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Simulation failed (${response.status})`);
  }
  return (await response.json()).result;
}

export type InputSeriesKey = "inflow" | "bcod" | "nh4" | "ras" | "was" | "airflow1" | "airflow2" | "airflow3";
export interface InputSeriesInfo {
  id: string | null;
  key: InputSeriesKey;
  filename: string;
  unit: string;
  count: number;
  end_h: number;
  minimum: number;
  maximum: number;
}

export async function uploadInputSeries(key: InputSeriesKey, file: File): Promise<InputSeriesInfo> {
  const response = await fetch(`/api/input-series/${key}?filename=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file,
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail ?? `Import failed (${response.status})`);
  return result;
}
