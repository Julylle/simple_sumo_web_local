import { plotInteractionConfig, plotInteractionLayout } from '../plotInteraction';
import { t, useLanguage } from '../i18n';
import { useMemo, useState } from "react";
import Plot from "react-plotly.js";
import type { Data } from "plotly.js";
import type { SimulationRun } from "../hooks/useSimulation";
import { Empty } from "./EmptyState";
import type { ReactNode } from "react";
import { variableColor } from "../config/chartColors";
import type { useSimulationMeasurements } from "../hooks/useSimulationMeasurements";

export function SimulationCharts({ data, calibrationPanel, measurements }: {
  data: SimulationRun | null; calibrationPanel: ReactNode;
  measurements: ReturnType<typeof useSimulationMeasurements>;
}) {
  const language = useLanguage();
  const plotConfig = useMemo(() => plotInteractionConfig(language), [language]);
  const [tank, setTank] = useState("all");
  const [component, setComponent] = useState("all");
  const variables = [...new Set([...Object.keys(data?.variables ?? {}), ...Object.keys(measurements.data?.variables ?? {})])];
  const componentOf = (name: string) => name.replace(/^([SX])\d+/, "$1");
  const components = [...new Set(variables.map(name => componentOf(name)))];
  const visibleVariables = variables.filter(name =>
    (tank === "all" || name.match(/^[SX](\d+)/)?.[1] === tank) &&
    (component === "all" || componentOf(name) === component)
  );
  const traces: Data[] = visibleVariables.flatMap(name => {
    const simulated = data?.variables[name];
    const observed = measurements.data?.variables[name];
    const color = variableColor(name);
    const traces: Data[] = [];
    if (simulated && data) traces.push({ x: data.time_h, y: simulated, type: "scatter", mode: "lines",
      name: t(`${name} · Simulated`), legendgroup: name, line: { width: 2, color } });
    if (observed?.some(value => value !== null) && measurements.data) traces.push({
      x: measurements.data.time_h, y: observed, type: "scatter", mode: "markers",
      name: t(`${name} · Measured`), legendgroup: name, marker: { size: 8, color, opacity: 0.45 } });
    return traces;
  });
  return (
    <section className="chart-grid">
      <div className="chart-card wide">
        <div className="chart-head">
          <div>
            <h3>{t("Model variable time series")}</h3>
            <p>{t("Dynamic simulation variables across all five tanks")}</p>
          </div>
          <span className="chart-chip">{t("Time series")}</span>
        </div>
        <div className="measurement-actions">
          <label htmlFor="simulation-measurements">{t("Upload measurements (.xlsx, max 5 MB)")} <input id="simulation-measurements" type="file" accept=".xlsx" disabled={measurements.busy}
              onChange={event => { const file = event.target.files?.[0]; if (file) void measurements.upload(file); event.target.value = ""; }} />
          </label>
          <a href="/api/calibration-measurements/template" download>{t("Download Excel template")}</a>
          {measurements.data && <button className="secondary" disabled={measurements.busy} onClick={measurements.clear}>{t("Remove measurements")}</button>}
        </div>
        <p className="calibration-note">{t("Use the validation sheet: t (min), starting at 0, plus model variable columns such as S5NH or S5NO3 (mg/L). Blank measurements are skipped; dyinput is optional. This upload adds comparison points to the chart.")}</p>
        {measurements.busy && <p role="status">{t("Uploading measurements…")}</p>}
        {measurements.error && <div className="alert" role="alert">{t(measurements.error)}</div>}
        {measurements.data && <p role="status" className="measurement-ready">{t("Loaded:")} {t(measurements.data.filename)} · {t(measurements.data.time_h.length)} {t("timestamps. Lines: simulated; points: measured. Time is aligned by elapsed hours.")}</p>}
        {(data || measurements.data) && (
          <div className="series-filters">
            <label> {t("Tank")} <select value={tank} onChange={(event) => setTank(event.target.value)}>
                <option value="all">{t("All tanks")}</option>
                {[1, 2, 3, 4, 5].map((value) => (
                  <option key={value} value={value}>{t("Tank")} {t(value)}</option>
                ))}
              </select>
            </label>
            <label> {t("Component")} <select value={component} onChange={(event) => setComponent(event.target.value)}>
                <option value="all">{t("All components")}</option>
                {components.map((value) => <option key={value} value={value}>{t(value)}</option>)}
              </select>
            </label>
            <span>{t(visibleVariables.length)} {t("series · Click a legend entry to hide a curve")}</span>
          </div>
        )}
        {data || measurements.data ? (
          <Plot
            data={traces}
            layout={{
              ...plotInteractionLayout,
              autosize: true,
              height: 480,
              hovermode: "closest",
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              legend: { orientation: "v", x: 1.02, y: 1, groupclick: "toggleitem" },
              xaxis: { title: { text: t("Time (h)") }, gridcolor: "#edf0f4" },
              yaxis: {
                title: { text: t("Concentration (mg/L)") },
                gridcolor: "#edf0f4",
              },
              margin: { l: 65, r: 110, t: 48, b: 60 },
            }}
            useResizeHandler
            style={{ width: "100%" }}
            config={plotConfig}
          />
        ) : (
          <Empty
            title={t("No simulation results")}
            text={t("Configure parameters above and run the ODE model.")}
          />
        )}
      </div>
      {t(calibrationPanel)}
    </section>
  );
}
