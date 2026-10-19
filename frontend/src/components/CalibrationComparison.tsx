import { plotLocale } from '../plotLocale';
import { t, useLanguage } from '../i18n';
import { useState } from "react";
import Plot from "react-plotly.js";
import type { CalibrationComparison as Comparison, MeasurementUpload } from "../api/client";
import { variableColor } from "../config/chartColors";

export function CalibrationComparison({ measurements, result, current }: {
  measurements: MeasurementUpload | null; result: Comparison | null; current: boolean;
}) {
  const language = useLanguage();
  const [tank, setTank] = useState("5");
  const [component, setComponent] = useState("NH");
  const selectedTanks = tank === "all" ? [1, 2, 3, 4, 5] : [Number(tank)];
  const series = selectedTanks.map(value => {
    const variable = `S${value}${component}`;
    return { variable, observed: measurements?.variables[variable], color: variableColor(variable), metrics: result?.metrics[variable] };
  }).filter(series => series.observed?.some(value => value !== null));
  const selectionLabel = tank === "all" ? `S1–S5 ${component}` : `S${tank}${component}`;
  const format = (value: number | null | undefined) => value == null ? "—" : value.toPrecision(4);
  return (
    <div className="chart-card wide">
      <div className="chart-head">
        <div><h3>{t("Simulated vs measured")}</h3><p>{t("Measured points and model curves at matching timestamps · mg/L")}</p></div>
      </div>
      <div className="series-filters">
        <label>{t("Tank")} <select value={tank} onChange={event => setTank(event.target.value)}>
          <option value="all">{t("All tanks")}</option>
          {[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{t("Tank")} {t(value)}</option>)}
        </select></label>
        <label>{t("Component")} <select value={component} onChange={event => setComponent(event.target.value)}>
          <option value="NH">NH4-N</option><option value="NO3">NO3-N</option>
          <option value="NO2">NO2-N</option><option value="O">{t("Dissolved oxygen")}</option><option value="N2O">N2O-N</option>
        </select></label>
      </div>
      {measurements ? <>
        {result && !current && <p className="calibration-note" role="status">{t("Calibration settings have changed. Curves show the last completed calibration; run again to update.")}</p>}
        {series.length > 0 ? <>
          <Plot data={series.flatMap(({ variable, observed, color }) => [
            { x: measurements.time_h, y: observed, type: "scatter" as const, mode: "markers" as const, name: t(`${variable} · Measured`), legendgroup: variable, marker: { color, size: 8 } },
            ...(result ? [
              { x: result.time_h, y: result.before[variable], type: "scatter" as const, mode: "lines" as const, name: t(`${variable} · Before calibration`), legendgroup: variable, line: { color, dash: "dash" as const, width: 2 } },
              { x: result.time_h, y: result.after[variable], type: "scatter" as const, mode: "lines" as const, name: t(`${variable} · After calibration`), legendgroup: variable, line: { color, width: 2.5 } },
            ] : []),
          ])} layout={{ autosize: true, height: tank === "all" ? 580 : 420, hovermode: "closest", margin: { l: 65, r: 20, t: 20, b: tank === "all" ? 180 : 85 },
            legend: { orientation: "h", y: -0.2, groupclick: "toggleitem" }, paper_bgcolor: "transparent", plot_bgcolor: "transparent",
            xaxis: { title: { text: t("Elapsed time (h)") }, gridcolor: "#edf0f4" },
            yaxis: { title: { text: `${selectionLabel} (mg/L)` }, gridcolor: "#edf0f4" },
          }} config={{ ...plotLocale(language), displaylogo: false, responsive: true }} useResizeHandler style={{ width: "100%" }} />
          <p className="calibration-note">{t("Color identifies the model variable and matches Simulation. Points: measured · dashed: before calibration · solid: after calibration.")}</p>
          {series.map(({ variable, observed, color, metrics }) => metrics && <div className="calibration-metrics" key={variable}>
            <span>{t("Variable")} <b style={{ color }}>{t(variable)}</b></span>
            <span>{t("RMSE before")} <b>{t(format(metrics.before))} mg/L</b></span>
            <span>{t("RMSE after")} <b>{t(format(metrics.after))} mg/L</b></span>
            <span>{t("Measured points")} <b>{observed?.filter(value => value !== null).length}</b></span>
          </div>)}
          {!result && <p className="calibration-note">{t("Measured data loaded. Run auto-calibration to add the model curves.")}</p>}
        </> : <div className="empty"><b>{t("No measurements for")} {t(selectionLabel)}</b><span>{t("Select another component or upload a workbook containing these measurements.")}</span></div>}
        <p className="calibration-note">{t("The optimizer fits NH4-N and NO3-N across all five tanks. Other components are shown for comparison. Missing measurements are skipped.")}</p>
      </> : <div className="empty"><b>{t("Upload measured data to begin")}</b><span>{t("Your uploaded measurements and calibration results will appear here.")}</span></div>}
    </div>
  );
}
