import { t, useLanguage } from '../i18n';
import { useState } from 'react';
import { SumoOutputPlot } from './SumoOutputPlot';
import { doOptions, pollutantOptions, type OutputOption, type SumoResult } from './sumoOutputs';

function VariableDropdown({ title, options, selected, onChange }: {
  title: string; options: OutputOption[]; selected: string[]; onChange: (keys: string[]) => void;
}) {
  useLanguage();
  return <details className="sumo-variable-dropdown"><summary>{t(title)} <span>{selected.filter(k => options.some(o => o.key === k)).length} {t("selected")}</span></summary>
    <div className="sumo-variable-options"><div className="measurement-actions">
      <button className="secondary" onClick={() => onChange(options.map(o => o.key))}>{t("Select all")}</button>
      <button className="secondary" onClick={() => onChange([])}>{t("Clear")}</button></div>
      {options.map(option => <label key={option.key}><input type="checkbox" checked={selected.includes(option.key)}
        onChange={e => onChange(e.target.checked ? [...selected, option.key] : selected.filter(k => k !== option.key))} />{t(option.label)} <small>{option.unit}</small></label>)}
      {!options.length && <p>{t("Select influent parameters in Step1.")}</p>}
    </div></details>;
}
function OutputCard({title, groups, result, runId, remove}: {
  title: string; groups: {title: string; options: OutputOption[]}[]; result?: SumoResult; runId: string; remove?: () => void;
}) {
  useLanguage();
  const options = groups.flatMap(g => g.options);
  const [selection, setSelection] = useState<string[] | null>(remove ? [] : null);
  const selected = selection === null ? options.map(o => o.key) : selection.filter(k => options.some(o => o.key === k));
  const [secondary, setSecondary] = useState(false);
  const [right, setRight] = useState<string[]>([]);
  const available = selected.filter(k => result?.variables[k]);
  return <article className="sumo-overlay-card">
    <div className="chart-head"><h3>{t(title)}</h3>{remove && <button className="secondary" onClick={remove}>{t("Remove plot")}</button>}</div>
    <div className="sumo-group-dropdowns">{groups.map(group => <VariableDropdown key={group.title} {...group}
      selected={selected.filter(k => group.options.some(o => o.key === k))} onChange={keys => setSelection([...selected.filter(k => !group.options.some(o => o.key === k)), ...keys])} />)}
      <label className="sumo-axis-toggle"><input type="checkbox" checked={secondary} onChange={e => setSecondary(e.target.checked)} />{t("Enable secondary Y axis")}</label>
      {secondary && <VariableDropdown title={t("Right Y axis")} options={options.filter(o => selected.includes(o.key))} selected={right} onChange={setRight} />}
    </div>
    {!selected.length ? <div className="empty"><b>{t("Select variables to build this plot")}</b><span>{t("Choose one or more variables from the dropdowns above.")}</span></div> : !result ?
      <div className="empty"><b>{t("No simulation results yet")}</b><span>{t("Run SUMO to populate this plot.")}</span></div> : <>
        {available.length < selected.length && <p role="status">{t("Some selected variables are not in this result. Run SUMO again with the current Step1 parameters.")}</p>}
        {!!available.length && <SumoOutputPlot result={result} variables={available} rightAxis={secondary ? right : []} overlay runId={runId} options={options} />}
      </>}
  </article>;
}
export function SumoOutputDashboard({influent, result, runId}: {influent: OutputOption[]; result?: SumoResult; runId: string}) {
  useLanguage();
  const [custom, setCustom] = useState<number[]>([]);
  const [nextId, setNextId] = useState(1);
  const groups = [{title: 'Influent variables', options: influent}, {title: 'Effluent pollutants', options: pollutantOptions}, {title: 'DO concentrations', options: doOptions}];
  return <div className="sumo-output-dashboard">
    {groups.map(group => <OutputCard key={group.title} title={group.title} groups={[group]} result={result} runId={runId} />)}
    <div className="section-title"><div><h3>{t("Custom comparison plots")}</h3><p>{t("Add a blank plot and compare variables across all three groups.")}</p></div>
      <button className="secondary" onClick={() => {setCustom(current => [...current, nextId]); setNextId(nextId + 1);}}>{t("Add comparison plot")}</button></div>
    {custom.map(id => <OutputCard key={id} title={t(`Comparison ${id}`)} groups={groups} result={result} runId={runId} remove={() => setCustom(current => current.filter(k => k !== id))} />)}
  </div>;
}
