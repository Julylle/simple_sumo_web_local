import { t, useLanguage } from '../i18n';
import { ProcessFlowDiagram } from "./ProcessFlowDiagram";
import { InputSeriesUpload } from "./InputSeriesUpload";
import type { InputSeriesControls } from "../hooks/useInputSeries";
import { useState } from "react";
import type { Params } from "../api/client";

type ProcessField = { key: keyof Params; label: string; unit: string; min: number; max?: number; step: number };
const nodes = [
  { id: "inlet", label: "Raw influent", x: 15, width: 110 },
  { id: "1", label: "Anoxic 1", x: 170, width: 125 },
  { id: "2", label: "Anoxic 2", x: 335, width: 125 },
  { id: "3", label: "Aerobic 1", x: 500, width: 125 },
  { id: "4", label: "Aerobic 2", x: 665, width: 125 },
  { id: "5", label: "Aerobic 3", x: 830, width: 125 },
  { id: "sst", label: "SST", x: 1010, width: 100 },
];

export function ProcessConfiguration({ parameters, onChange, inputSeries, busy }: {
  inputSeries: InputSeriesControls;
  busy: boolean;
  parameters: Params;
  onChange: (key: keyof Params, value: number) => void;
}) {
  useLanguage();
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState("1");
  const tank = Number(selected);
  const title = nodes.find((node) => node.id === selected)?.label ?? t("Internal recycle (MLR)");
  const fields: ProcessField[] = selected === "inlet" || selected === "sst" ? [] : selected === "mlr" ? [
    { key: "mlr_ratio", label: t("MLR / influent flow"), unit: "ratio", min: 0, step: 0.1 },
  ] : [
    { key: `tank${tank}_volume_m3` as keyof Params, label: t("Volume per lane"), unit: "m3", min: 0.001, step: 0.1 },
  ];


  return (
    <section className="process-config" aria-labelledby="process-title">
      <div className="process-heading">
        <div><h2 id="process-title">{t("MLE configuration")}</h2><p>{t("11 parallel lanes · One representative treatment line")}</p></div>
        <button type="button" className="secondary" aria-expanded={expanded} aria-controls="process-diagram" onClick={() => setExpanded(!expanded)}>
          {t(expanded ? t("Hide flow diagram") : t("Simplify configuration"))}
        </button>
      </div>
      {expanded && <div id="process-diagram">
        <p className="process-help">{t("Select a reactor or flow to edit its parameters. Import each input from Excel: first sheet, time_h and value columns, starting at 0 h. All flows are per lane. Each value is held until the next time point, and the last value is held after the series ends. Imports persist after refresh; Reset keeps imported files.")}</p>
        <div className="process-scroll">
          <ProcessFlowDiagram parameters={parameters} selected={selected} onSelect={setSelected} />
        </div>
        <div className="process-editor">
          <div><h3>{t(title)}</h3><p>{t(selected === "sst" ? t("RAS and WAS use single-lane Excel flow series in m3/d.") : selected === "inlet" ? t("Import single-lane inflow in m3/d, bCOD and NH4-N in mg/L. Uploaded values are used directly, without COD scaling or division by 11.") : selected === "mlr" ? t("Mixed liquor returns from Aerobic 3 to Anoxic 1.") : t("Volume applies to each lane. Airflow in m3/h drives oxygen transfer and the calculated DO."))}</p></div>
          <div className="process-fields">{fields.map((field) => <label key={field.key}>{t(field.label)}<div><input type="number" value={parameters[field.key]} min={field.min} max={field.max} step={field.step} onChange={(event) => onChange(field.key, Number(event.target.value))} /><span>{field.unit}</span></div></label>)}</div>
          <div className="process-series">
            {inputSeries.loadError && <p role="alert">{t(inputSeries.loadError)} <button onClick={inputSeries.retry}>{t("Retry")}</button></p>}
            {selected === "inlet" && <>
              <InputSeriesUpload seriesKey="inflow" label={t("Single lane inflow rate")} controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="bcod" label={t("Influent biodegradable COD (bCOD)")} controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="nh4" label={t("Influent NH4-N")} controls={inputSeries} busy={busy} />
            </>}
            {selected === "sst" && <>
              <InputSeriesUpload seriesKey="ras" label={t("Return activated sludge (RAS)")} controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="was" label={t("Waste activated sludge (WAS)")} controls={inputSeries} busy={busy} />
            </>}
            {tank >= 3 && tank <= 5 && <>
              <InputSeriesUpload seriesKey={`airflow${tank - 2}` as "airflow1" | "airflow2" | "airflow3"} label={t(`Aerobic ${tank - 2} airflow rate`)} controls={inputSeries} busy={busy} />
              <div className="input-series-card">
                <h4>{t("Aerobic")} {t(tank - 2)} {t("DO setpoint")}</h4>
                <label className="field">
                  <span className="field-label">{t("DO setpoint (mg/L)")}</span>
                  <div className="input-wrap"><input type="number" min={0} max={8} step={0.1} disabled={busy}
                    value={parameters[`tank${tank}_do_mg_l` as keyof Params]}
                    onChange={(event) => onChange(`tank${tank}_do_mg_l` as keyof Params, Number(event.target.value))} /><span>mg/L</span></div>
                </label>
                <p>{t(parameters.use_do_setpoint ? t("Active: DO is held at this value.") : t("Enable Use DO setpoints in Simulation settings to apply this value."))}</p>
              </div>
            </>}
          </div>
        </div>
      </div>}
    </section>
  );
}
