export interface Params {
  flow_m3_d: number;
  influent_cod_mg_l: number;
  influent_nh4_mg_l: number;
  do_mg_l: number;
  srt_d: number;
  duration_h: number;
}

export interface SimulationResult {
  time_h: number[];
  nh4_mg_l: number[];
  cod_mg_l: number[];
  n2o_index: number[];
}

export async function simulate(params: Params): Promise<SimulationResult> {
  const response = await fetch('/api/simulation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`Simulation failed (${response.status})`);
  return (await response.json()).result;
}
