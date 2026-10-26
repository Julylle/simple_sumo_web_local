import { localPlotTimestamp } from '../utils/liveSensorDisplay';
import { t, useLanguage } from '../i18n';
import { usePlotSetting } from '../hooks/usePlotSetting';
import { validChoices, validCards, type PlotChoices, type PlotCards } from '../utils/plotSettings';
import { SumoOutputPlot } from './SumoOutputPlot';
import { doOptions, pollutantOptions, type OutputOption, type SumoResult } from './sumoOutputs';

export function VariableDropdown({ title, options, selected, onChange }: {
  title: string; options: OutputOption[]; selected: string[]; onChange: (keys: string[]) => void;
}) {
  useLanguage();
  return <details className="sumo-variable-dropdown" onMouseLeave={event => { event.currentTarget.open = false; }}><summary>{t(title)} <span>{selected.filter(k => options.some(o => o.key === k)).length} {t("selected")}</span></summary>
    <div className="sumo-variable-options"><div className="measurement-actions">
      <button className="secondary" onClick={() => onChange(options.map(o => o.key))}>{t("Select all")}</button>
      <button className="secondary" onClick={() => onChange([])}>{t("Clear")}</button></div>
      {options.map(option => <label key={option.key}><input type="checkbox" checked={selected.includes(option.key)}
        onChange={e => onChange(e.target.checked ? [...selected, option.key] : selected.filter(k => k !== option.key))} />{t(option.label)} <small>{t(option.unit)}</small></label>)}
      {!options.length && <p>{t("Select influent parameters in Step1.")}</p>}
    </div></details>;
}
function OutputCard({title, groups, result, runId, remove, localTime = false, settingsKey}: {
  settingsKey: string; title: string; groups: {title: string; options: OutputOption[]}[]; result?: SumoResult; runId: string; remove?: () => void; localTime?: boolean;
}) {
  useLanguage();
  const options = groups.flatMap(g => g.options);
  const [{selection, secondary, right}, setChoices] = usePlotSetting<PlotChoices>(settingsKey + ':choices', {selection: remove ? [] : null, secondary: false, right: []}, validChoices);
  const setSelection = (selection: string[]) => setChoices(current => ({...current, selection}));
  const setSecondary = (secondary: boolean) => setChoices(current => ({...current, secondary}));
  const setRight = (right: string[]) => setChoices(current => ({...current, right}));
  const selected = selection === null ? options.map(o => o.key) : selection.filter(k => options.some(o => o.key === k));
  const timestamps = localTime && result ? result.time_h.map((_, i) => {
    const value = result.sensor_timestamps?.[i];
    return value && Number.isFinite(Date.parse(value)) ? localPlotTimestamp(Date.parse(value)) : null;
  }) : undefined;
  const available = selected.filter(k => result?.variables[k] || result?.comparison_series?.[k]);
  return <article className="sumo-overlay-card">
    <div className="chart-head"><h3>{t(title)}</h3>{remove && <button className="secondary" onClick={remove}>{t("Remove plot")}</button>}</div>
    <div className="sumo-group-dropdowns">{groups.map(group => <VariableDropdown key={group.title} {...group}
      selected={selected.filter(k => group.options.some(o => o.key === k))} onChange={keys => setSelection([...selected.filter(k => !group.options.some(o => o.key === k)), ...keys])} />)}
      <label className="sumo-axis-toggle"><input type="checkbox" checked={secondary} onChange={e => setSecondary(e.target.checked)} />{t("Enable secondary Y axis")}</label>
      {secondary && <VariableDropdown title={t("Right Y axis")} options={options.filter(o => selected.includes(o.key))} selected={right} onChange={setRight} />}
    </div>
    {!selected.length ? <div className="empty"><b>{t("Select variables to build this plot")}</b><span>{t("Choose one or more variables from the dropdowns above.")}</span></div> : !result ?
      <div className="empty"><b>{t("No simulation results yet")}</b><span>{t("Run SUMO to populate this plot.")}</span></div> : <>
        {selected.some(k => !options.find(o => o.key === k)?.compareTo && !result.variables[k]) && <p role="status">{t("Some selected variables are not in this result. Run SUMO again with the current Step1 parameters.")}</p>}
        {localTime && timestamps?.some(value => value === null) && <p role="status">{t("Older samples have no recorded sensor timestamp and cannot be placed on the local-time axis. They remain available in the CSV.")}</p>}
        {!!available.length && <SumoOutputPlot settingsKey={settingsKey} timestamps={timestamps} result={result} variables={available} rightAxis={secondary ? right : []} overlay runId={runId} options={options} />}
      </>}
  </article>;
}
export function SumoOutputDashboard({influent, result, runId, showInfluent = true, showDo = true, localTime = false, pollutants = pollutantOptions}: {influent: OutputOption[]; result?: SumoResult; runId: string; showInfluent?: boolean; showDo?: boolean; localTime?: boolean; pollutants?: OutputOption[]}) {
  useLanguage();
  const scope = localTime ? 'live:outputs' : 'offline:outputs';
  const [cards, setCards] = usePlotSetting<PlotCards>(scope + ':cards', {ids: [], nextId: 1}, validCards);
  const groups = [{title: 'Influent variables', options: influent}, {title: 'Effluent pollutants', options: pollutants}, {title: 'DO concentrations', options: doOptions}];
  return <div className="sumo-output-dashboard">
    {groups.filter(group => (showInfluent || group.title !== 'Influent variables') && (showDo || group.title !== 'DO concentrations')).map(group => <OutputCard key={group.title} settingsKey={`${scope}:${group.title}`} title={t(group.title)} groups={[group]} result={result} localTime={localTime} runId={runId} />)}
    <div className="section-title"><div><h3>{t("Custom comparison plots")}</h3><p>{t("Add a blank plot and compare variables across all three groups.")}</p></div>
      <button className="secondary" onClick={() => {setCards(current => ({ids: [...current.ids, current.nextId], nextId: current.nextId + 1}));}}>{t("Add comparison plot")}</button></div>
    {cards.ids.map(id => <OutputCard key={id} settingsKey={`${scope}:comparison:${id}`} title={t(`Comparison ${id}`)} groups={groups} result={result} localTime={localTime} runId={runId} remove={() => setCards(current => ({...current, ids: current.ids.filter(k => k !== id)}))} />)}
  </div>;
}
