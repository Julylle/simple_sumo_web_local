import type { Params } from "../api/client";

export const defaultParameters: Params = {
  flow_m3_d: 5098,
  influent_cod_mg_l: 412.8,
  influent_nh4_mg_l: 63.6,
  do_mg_l: 2,
  srt_d: 14,
  duration_h: 960,
  tank1_volume_m3: 233.72729,
  tank1_do_mg_l: 0,
  tank2_volume_m3: 233.72729,
  tank2_do_mg_l: 0,
  tank3_volume_m3: 467.45451,
  tank3_do_mg_l: 2,
  tank4_volume_m3: 467.45451,
  tank4_do_mg_l: 2,
  tank5_volume_m3: 467.45451,
  tank5_do_mg_l: 2,
  mlr_ratio: 2.5,
  ras_ratio: 1,
};
type Field = {
  key: keyof Params;
  label: string;
  unit: string;
  min: number;
  max?: number;
  step: number;
  hint: string;
};
export const parameterGroups: {
  title: string;
  subtitle: string;
  fields: Field[];
}[] = [
  {
    title: "Influent",
    subtitle: "Boundary conditions entering the model",
    fields: [
      {
        key: "flow_m3_d",
        label: "Flow",
        unit: "m³/d",
        min: 100,
        max: 1000000,
        step: 100,
        hint: "Influent flow rate",
      },
      {
        key: "influent_cod_mg_l",
        label: "Influent COD",
        unit: "mg/L",
        min: 10,
        max: 1000,
        step: 1,
        hint: "Initial biodegradable COD",
      },
      {
        key: "influent_nh4_mg_l",
        label: "Influent NH₄-N",
        unit: "mg/L",
        min: 1,
        max: 300,
        step: 0.1,
        hint: "Initial ammonium nitrogen",
      },
    ],
  },
  {
    title: "Operating conditions",
    subtitle: "Parameters controlling process kinetics",
    fields: [
      {
        key: "do_mg_l",
        label: "DO setpoint",
        unit: "mg/L",
        min: 0.2,
        max: 4,
        step: 0.1,
        hint: "Dissolved oxygen concentration",
      },
      {
        key: "srt_d",
        label: "SRT",
        unit: "d",
        min: 1,
        max: 30,
        step: 1,
        hint: "Solids retention time",
      },
    ],
  },
  {
    title: "Simulation settings",
    subtitle: "Numerical run configuration",
    fields: [
      {
        key: "duration_h",
        label: "Simulation duration",
        unit: "h",
        min: 1,
        step: 1,
        hint: "ODE integration horizon",
      },
    ],
  },
];
