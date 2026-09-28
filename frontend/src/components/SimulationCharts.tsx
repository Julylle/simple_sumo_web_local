import { useState } from "react";
import Plot from "react-plotly.js";
import type { Config } from "plotly.js";
import type { SimulationRun } from "../hooks/useSimulation";
import { Empty } from "./EmptyState";

const plotConfig: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

export function SimulationCharts({ data }: { data: SimulationRun | null }) {
  const [tank, setTank] = useState("all");
  const [component, setComponent] = useState("all");
  const variables = Object.entries(data?.variables ?? {});
  const componentOf = (name: string) => name.replace(/^([SX])\d+/, "$1");
  const components = [...new Set(variables.map(([name]) => componentOf(name)))];
  const visibleVariables = variables.filter(([name]) =>
    (tank === "all" || name.match(/^[SX](\d+)/)?.[1] === tank) &&
    (component === "all" || componentOf(name) === component)
  );
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
        {data && (
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
        {data ? (
          <Plot
            data={visibleVariables.map(([name, values]) => ({
              x: data.time_h,
              y: values,
              type: "scatter",
              mode: "lines",
              name,
              line: { width: 2 },
            }))}
            layout={{
              autosize: true,
              height: 480,
              hovermode: "closest",
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              legend: { orientation: "v", x: 1.02, y: 1 },
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
      <div className="chart-card info-card">
        <div className="chart-head">
          <div>
            <h3>Run information</h3>
            <p>Execution and data-boundary summary</p>
          </div>
        </div>
        <dl>
          <div>
            <dt>Model</dt>
            <dd>ODE Demo</dd>
          </div>
          <div>
            <dt>Solver</dt>
            <dd>RK4 · server-side</dd>
          </div>
          <div>
            <dt>Raw states</dt>
            <dd>Private</dd>
          </div>
          <div>
            <dt>API output</dt>
            <dd>Allow-listed + downsampled</dd>
          </div>
          <div>
            <dt>Last run</dt>
            <dd>{data ? "Completed" : "Not run"}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
