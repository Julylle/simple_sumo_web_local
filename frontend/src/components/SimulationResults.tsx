import type { ReactNode } from "react";
import type { Params } from "../api/client";
import type { SimulationRun } from "../hooks/useSimulation";
import { SimulationCharts } from "./SimulationCharts";

function formatNumber(value: number, digits = 1) {
  return Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: digits })
    : "—";
}

interface SimulationResultsProps {
  data: SimulationRun | null;
  parameters: Params;
  calibrationPanel: ReactNode;
}

export function SimulationResults({
  data,
  parameters,
  calibrationPanel,
}: SimulationResultsProps) {
  const final = data
    ? {
        cod: data.cod_mg_l.slice(-1)[0],
        nh4: data.nh4_mg_l.slice(-1)[0],
        n2o: Math.max(...data.n2o_index),
      }
    : null;

  return (
    <>
      <section className="results-head">
        <div>
          <h2>Results</h2>
          <p>
            {data
              ? "Latest approved simulation outputs"
              : "Run the model to generate results"}
          </p>
        </div>
        {data && (
          <div className="result-meta">
            <span>● Completed</span>
            <b>{data.time_h.length} displayed points</b>
          </div>
        )}
      </section>
      <section className="kpis">
        {(
          [
            [
              "Final COD",
              final?.cod,
              "mg/L",
              data ? "Measured dynamic influent" : "Awaiting run",
            ],
            [
              "Final NH₄-N",
              final?.nh4,
              "mg/L",
              data ? "Measured dynamic influent" : "Awaiting run",
            ],
            [
              "Peak N₂O index",
              final?.n2o,
              "index",
              data ? "Synthetic demo indicator" : "Awaiting run",
            ],
            [
              "Runtime",
              data ? data.runtimeSeconds : undefined,
              "s",
              data ? "API round-trip time" : "Awaiting run",
            ],
          ] as [string, number | undefined, string, string][]
        ).map(([name, val, unit, sub]) => (
          <div className="kpi" key={name}>
            <span>{name}</span>
            <div>
              <b>
                {val === undefined ? "—" : formatNumber(val, val < 10 ? 3 : 1)}
              </b>
              <small>{unit}</small>
            </div>
            <p>{sub}</p>
          </div>
        ))}
      </section>
      <SimulationCharts data={data} calibrationPanel={calibrationPanel} />
    </>
  );
}
