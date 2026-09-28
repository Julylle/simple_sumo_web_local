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
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState("1");
  const tank = Number(selected);
  const title = nodes.find((node) => node.id === selected)?.label ?? "Internal recycle (MLR)";
  const fields: ProcessField[] = selected === "inlet" || selected === "sst" ? [] : selected === "mlr" ? [
    { key: "mlr_ratio", label: "MLR / influent flow", unit: "ratio", min: 0, step: 0.1 },
  ] : [
    { key: `tank${tank}_volume_m3` as keyof Params, label: "Volume per lane", unit: "m3", min: 0.001, step: 0.1 },
  ];


  return (
    <section className="process-config" aria-labelledby="process-title">
      <div className="process-heading">
        <div><h2 id="process-title">MLE configuration</h2><p>11 parallel lanes · One representative treatment line</p></div>
        <button type="button" className="secondary" aria-expanded={expanded} aria-controls="process-diagram" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Hide flow diagram" : "Simplify configuration"}
        </button>
      </div>
      {expanded && <div id="process-diagram">
        <p className="process-help">Select a reactor or flow to edit its parameters. Import each input from Excel: first sheet, time_h and value columns, starting at 0 h. All flows are per lane. Each value is held until the next time point, and the last value is held after the series ends. Imports persist after refresh; Reset keeps imported files.</p>
        <div className="process-scroll">
          <svg className="process-svg" viewBox="0 0 1230 320" aria-label="MLE process: influent, two anoxic tanks, three aerobic tanks, secondary settling tank and effluent, with internal and sludge recycles">
            <defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
            <g className="process-pipes" fill="none" strokeWidth="2" markerEnd="url(#flow-arrow)">
              {nodes.map((node, index) => <path key={node.id} d={`M ${node.x + node.width} 105 H ${nodes[index + 1]?.x ?? 1210}`} />)}
              <path className="recycle-pipe" d="M 980 105 V 205 H 150 V 105 H 170" />
              <path className="ras-pipe" d="M 1060 145 V 275 H 140 V 105 H 170" />
              <path className="ras-pipe" d="M 1060 275 V 312" />
            </g>
            <text x="1165" y="80" textAnchor="middle" className="flow-label">Final effluent</text>
            <text x="1075" y="305" className="flow-label">WAS</text>
            {nodes.map((node) => {
              const volume = parameters[`tank${node.id}_volume_m3` as keyof Params];
              return <g key={node.id} role="button" tabIndex={0} aria-label={`Edit ${node.label} parameters`} aria-pressed={selected === node.id}
                className={`process-node ${selected === node.id ? "selected" : ""}`}
                onClick={() => setSelected(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected(node.id); } }}>
                <rect x={node.x} y="65" width={node.width} height="80" rx={node.id === "sst" ? 30 : 7} />
                <text x={node.x + node.width / 2} y="92" textAnchor="middle">{node.label}</text>
                <text className="node-detail" x={node.x + node.width / 2} y="113" textAnchor="middle">{node.id === "inlet" ? "Excel time series" : node.id === "sst" ? "RAS / WAS: Excel" : `${volume.toFixed(1)} m3`}</text>
                {Number(node.id) > 0 && <text className="node-detail" x={node.x + node.width / 2} y="132" textAnchor="middle">{Number(node.id) >= 3 ? "Airflow: Excel" : "Anoxic reactor"}</text>}
              </g>;
            })}
            <g role="button" tabIndex={0} className={`process-node recycle-node ${selected === "mlr" ? "selected" : ""}`} aria-label="Edit internal recycle ratio" aria-pressed={selected === "mlr"} onClick={() => setSelected("mlr")}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelected("mlr"); } }}>
              <rect x="490" y="185" width="240" height="40" rx="6" /><text x="610" y="210" textAnchor="middle">← MLR · {parameters.mlr_ratio} × Q</text>
            </g>
            <text x="610" y="263" textAnchor="middle" className="flow-label">← Return activated sludge (RAS)</text>
          </svg>
        </div>
        <div className="process-editor">
          <div><h3>{title}</h3><p>{selected === "sst" ? "RAS and WAS use single-lane Excel flow series in m3/d." : selected === "inlet" ? "Import single-lane inflow in m3/d, bCOD and NH4-N in mg/L. Uploaded values are used directly, without COD scaling or division by 11." : selected === "mlr" ? "Mixed liquor returns from Aerobic 3 to Anoxic 1." : "Volume applies to each lane. Airflow in m3/h drives oxygen transfer and the calculated DO."}</p></div>
          <div className="process-fields">{fields.map((field) => <label key={field.key}>{field.label}<div><input type="number" value={parameters[field.key]} min={field.min} max={field.max} step={field.step} onChange={(event) => onChange(field.key, Number(event.target.value))} /><span>{field.unit}</span></div></label>)}</div>
          <div className="process-series">
            {inputSeries.loadError && <p role="alert">{inputSeries.loadError} <button onClick={inputSeries.retry}>Retry</button></p>}
            {selected === "inlet" && <>
              <InputSeriesUpload seriesKey="inflow" label="Single lane inflow rate" controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="bcod" label="Influent biodegradable COD (bCOD)" controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="nh4" label="Influent NH4-N" controls={inputSeries} busy={busy} />
            </>}
            {selected === "sst" && <>
              <InputSeriesUpload seriesKey="ras" label="Return activated sludge (RAS)" controls={inputSeries} busy={busy} />
              <InputSeriesUpload seriesKey="was" label="Waste activated sludge (WAS)" controls={inputSeries} busy={busy} />
            </>}
            {tank >= 3 && tank <= 5 && <InputSeriesUpload seriesKey={`airflow${tank - 2}` as "airflow1" | "airflow2" | "airflow3"} label={`Aerobic ${tank - 2} airflow rate`} controls={inputSeries} busy={busy} />}
          </div>
        </div>
      </div>}
    </section>
  );
}
