import { useState } from "react";
import Plot from "react-plotly.js";
import type { Config, Data } from "plotly.js";
import type { SimulationRun } from "../hooks/useSimulation";
import { Empty } from "./EmptyState";
import type { ReactNode } from "react";
import { variableColor } from "../config/chartColors";
import type { useSimulationMeasurements } from "../hooks/useSimulationMeasurements";

const plotConfig: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

export function SimulationCharts({ data, calibrationPanel, measurements }: {
  data: SimulationRun | null; calibrationPanel: ReactNode;
  measurements: ReturnType<typeof useSimulationMeasurements>;
}) {
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
      name: `${name} · Simulated`, legendgroup: name, line: { width: 2, color } });
    if (observed?.some(value => value !== null) && measurements.data) traces.push({
      x: measurements.data.time_h, y: observed, type: "scatter", mode: "markers",
      name: `${name} · Measured`, legendgroup: name, marker: { size: 8, color } });
    return traces;
  });
  return (
    <section className="chart-grid">
      <div className="chart-card wide">
        <div className="chart-head">
          <div>
            <h3>Model variable time series</h3>
            <p>Dynamic simulation variables across all five tanks</p>
          </div>
          <span className="chart-chip">Time series</span>
        </div>
        <div className="measurement-actions">
          <label htmlFor="simulation-measurements">Upload measurements (.xlsx, max 5 MB)
            <input id="simulation-measurements" type="file" accept=".xlsx" disabled={measurements.busy}
              onChange={event => { const file = event.target.files?.[0]; if (file) void measurements.upload(file); event.target.value = ""; }} />
          </label>
          <a href="/api/calibration-measurements/template" download>Download Excel template</a>
          {measurements.data && <button className="secondary" disabled={measurements.busy} onClick={measurements.clear}>Remove measurements</button>}
        </div>
        <p className="calibration-note">Use the validation sheet: t (min), starting at 0, plus model variable columns such as S5NH or S5NO3 (mg/L). Blank measurements are skipped; dyinput is optional. This upload adds comparison points to the chart.</p>
        {measurements.busy && <p role="status">Uploading measurements…</p>}
        {measurements.error && <div className="alert" role="alert">{measurements.error}</div>}
        {measurements.data && <p role="status" className="measurement-ready">Loaded: {measurements.data.filename} · {measurements.data.time_h.length} timestamps. Lines: simulated; points: measured. Time is aligned by elapsed hours.</p>}
        {(data || measurements.data) && (
          <div className="series-filters">
            <label>
              Tank
              <select value={tank} onChange={(event) => setTank(event.target.value)}>
                <option value="all">All tanks</option>
                {[1, 2, 3, 4, 5].map((value) => (
                  <option key={value} value={value}>Tank {value}</option>
                ))}
              </select>
            </label>
            <label>
              Component
              <select value={component} onChange={(event) => setComponent(event.target.value)}>
                <option value="all">All components</option>
                {components.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
            <span>{visibleVariables.length} series · Click a legend entry to hide a curve</span>
          </div>
        )}
        {data || measurements.data ? (
          <Plot
            data={traces}
            layout={{
              autosize: true,
              height: 480,
              hovermode: "closest",
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              legend: { orientation: "v", x: 1.02, y: 1, groupclick: "toggleitem" },
              xaxis: { title: { text: "Time (h)" }, gridcolor: "#edf0f4" },
              yaxis: {
                title: { text: "Concentration (mg/L)" },
                gridcolor: "#edf0f4",
              },
              margin: { l: 65, r: 110, t: 20, b: 60 },
            }}
            useResizeHandler
            style={{ width: "100%" }}
            config={plotConfig}
          />
        ) : (
          <Empty
            title="No simulation results"
            text="Configure parameters above and run the ODE model."
          />
        )}
      </div>
      {calibrationPanel}
    </section>
  );
}
