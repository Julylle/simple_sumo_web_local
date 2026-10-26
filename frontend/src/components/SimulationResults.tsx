import { t, useLanguage } from '../i18n';
import type { ReactNode } from "react";
import type { Params } from "../api/client";
import type { SimulationRun } from "../hooks/useSimulation";
import { SimulationCharts } from "./SimulationCharts";
import type { useSimulationMeasurements } from "../hooks/useSimulationMeasurements";

function formatNumber(value: number, digits = 1) {
  return Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: digits })
    : "—";
}

interface SimulationResultsProps {
  data: SimulationRun | null;
  parameters: Params;
  calibrationPanel: ReactNode;
  measurements: ReturnType<typeof useSimulationMeasurements>;
}

export function SimulationResults({
  data,
  parameters,
  calibrationPanel,
  measurements,
}: SimulationResultsProps) {
  useLanguage();
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
          <h2>{t("Results")}</h2>
          <p>
            {t(data
              ? t("Latest approved simulation outputs")
              : t("Run the model to generate results"))}
          </p>
        </div>
        {data && (
          <div className="result-meta">
            <span>{t("● Completed")}</span>
            <b>{t(data.time_h.length)} {t("displayed points")}</b>
          </div>
        )}
      </section>
      <section className="kpis">
        {(
          [
            [
              t("Final COD"),
              final?.cod,
              "mg/L",
              data ? t("Measured dynamic influent") : t("Awaiting run"),
            ],
            [
              t("Final NH₄-N"),
              final?.nh4,
              "mg/L",
              data ? t("Measured dynamic influent") : t("Awaiting run"),
            ],
            [
              t("Peak N₂O index"),
              final?.n2o,
              "index",
              data ? t("Synthetic demo indicator") : t("Awaiting run"),
            ],
            [
              t("Runtime"),
              data ? data.runtimeSeconds : undefined,
              "s",
              data ? t("API round-trip time") : t("Awaiting run"),
            ],
          ] as [string, number | undefined, string, string][]
        ).map(([name, val, unit, sub]) => (
          <div className="kpi" key={name}>
            <span>{t(name)}</span>
            <div>
              <b>
                {t(val === undefined ? "—" : formatNumber(val, val < 10 ? 3 : 1))}
              </b>
              <small>{t(unit)}</small>
            </div>
            <p>{t(sub)}</p>
          </div>
        ))}
      </section>
      <SimulationCharts data={data} calibrationPanel={calibrationPanel} measurements={measurements} />
    </>
  );
}
