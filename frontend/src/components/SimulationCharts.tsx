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
  return (
    <section className="chart-grid">
      <div className="chart-card wide">
        <div className="chart-head">
          <div>
            <h3>Concentration profiles</h3>
            <p>Approved and downsampled model states</p>
          </div>
          <span className="chart-chip">Time series</span>
        </div>
        {data ? (
          <Plot
            data={[
              {
                x: data.time_h,
                y: data.cod_mg_l,
                type: "scatter",
                mode: "lines",
                name: "COD",
                line: { width: 2.5 },
              },
              {
                x: data.time_h,
                y: data.nh4_mg_l,
                type: "scatter",
                mode: "lines",
                name: "NH₄-N",
                line: { width: 2.5 },
              },
            ]}
            layout={{
              autosize: true,
              height: 380,
              hovermode: "x unified",
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              legend: { orientation: "h", x: 0, y: 1.12 },
              xaxis: { title: { text: "Time (h)" }, gridcolor: "#edf0f4" },
              yaxis: {
                title: { text: "Concentration (mg/L)" },
                gridcolor: "#edf0f4",
              },
              margin: { l: 65, r: 25, t: 55, b: 60 },
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
      <div className="chart-card">
        <div className="chart-head">
          <div>
            <h3>N₂O indicator</h3>
            <p>Demo output for UI integration testing</p>
          </div>
        </div>
        {data ? (
          <Plot
            data={[
              {
                x: data.time_h,
                y: data.n2o_index,
                type: "scatter",
                mode: "lines",
                name: "N₂O index",
                fill: "tozeroy",
                line: { width: 2 },
              },
            ]}
            layout={{
              autosize: true,
              height: 310,
              hovermode: "x",
              paper_bgcolor: "transparent",
              plot_bgcolor: "transparent",
              showlegend: false,
              xaxis: { title: { text: "Time (h)" }, gridcolor: "#edf0f4" },
              yaxis: { title: { text: "Index" }, gridcolor: "#edf0f4" },
              margin: { l: 65, r: 25, t: 25, b: 60 },
            }}
            useResizeHandler
            style={{ width: "100%" }}
            config={plotConfig}
          />
        ) : (
          <Empty
            title="Awaiting results"
            text="This panel updates after each model run."
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
