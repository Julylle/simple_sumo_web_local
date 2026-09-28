import type { Params } from "../api/client";
import { parameterGroups } from "../config/simulation";

interface SimulationConfigurationProps {
  parameters: Params;
  onChange: (key: keyof Params, value: number) => void;
}

export function SimulationConfiguration({
  parameters,
  onChange,
}: SimulationConfigurationProps) {
  return (
    <section className="config-card">
      <div className="section-title">
        <div>
          <h2>Simulation configuration</h2>
          <p>Validated ranges are enforced again by the backend API.</p>
        </div>
        <span className="model-badge">ODE · 2 states</span>
      </div>
      <div className="param-groups">
        {parameterGroups.map((g) => (
          <div className="param-group" key={g.title}>
            <div className="group-head">
              <h3>{g.title}</h3>
              <p>{g.subtitle}</p>
            </div>
            <div className="fields">
              {g.fields.map((f) => (
                <label className="field" key={f.key}>
                  <span className="field-label">
                    {f.label}
                    <small>{f.unit}</small>
                  </span>
                  <div className="input-wrap">
                    <input
                      type="number"
                      value={parameters[f.key]}
                      min={f.min}
                      max={f.max}
                      step={f.step}
                      onChange={(e) => onChange(f.key, Number(e.target.value))}
                    />
                    <span>{f.unit}</span>
                  </div>
                  <small className="hint">
                    {f.hint} · {f.max === undefined ? `Minimum ${f.min} ${f.unit}; no upper limit` : `${f.min}–${f.max}`}
                  </small>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
