import { simulationInputSeries } from '../utils/simulationInputSeries';
import { localPlotTimestamp } from '../utils/liveSensorDisplay';
import { useMemo } from 'react';
import { usePlotSetting } from '../hooks/usePlotSetting';
import { validChoices, type PlotChoices } from '../utils/plotSettings';
import { t, useLanguage } from '../i18n';
import { SumoOutputPlot } from './SumoOutputPlot';
import { VariableDropdown } from './SumoOutputDashboard';
import type { OutputOption, SumoResult } from './sumoOutputs';

type Sample = { column: string; value: number; receivedAt: number };

export function LiveSensorPlot({ title, groupTitle, options, history, className = '', source = 'sensor', simulationResult, runId = 'live-sensors' }: {
  title: string; groupTitle: string; options: OutputOption[]; history: Sample[];
  className?: string; source?: 'sensor' | 'simulation'; simulationResult?: SumoResult | null; runId?: string;
}) {
  useLanguage();
  const settingsKey = `live:sensors:${groupTitle}`;
  const [{selection, secondary, right}, setChoices] = usePlotSetting<PlotChoices>(settingsKey + ':choices', {selection: null, secondary: false, right: []}, validChoices);
  const setSelection = (selection: string[]) => setChoices(current => ({...current, selection}));
  const setSecondary = (secondary: boolean) => setChoices(current => ({...current, secondary}));
  const setRight = (right: string[]) => setChoices(current => ({...current, right}));
  const selected = options.filter(o => selection === null || selection.includes(o.key));
  const { result, timestamps } = useMemo(() => {
    if (source === 'simulation') {
      const result = simulationInputSeries(simulationResult, options.map(o => o.key));
      return {result, timestamps: result.sensor_timestamps.map(value =>
        value && Number.isFinite(Date.parse(value)) ? localPlotTimestamp(Date.parse(value)) : null)};
    }
    const keys = new Set(options.map(o => o.key));
    const samples = history.filter(s => keys.has(s.column));
    const times = [...new Set(samples.map(s => s.receivedAt))].sort((a,b) => a-b);
    const byColumn = new Map<string, Map<number, number>>();
    for (const sample of samples) {
      if (!byColumn.has(sample.column)) byColumn.set(sample.column, new Map());
      byColumn.get(sample.column)!.set(sample.receivedAt, sample.value);
    }
    return {
      timestamps: times.map(localPlotTimestamp),
      result: {time_h: times.map(time => (time-times[0])/3600000),
        variables: Object.fromEntries(options.map(o => [o.key, times.map(time => byColumn.get(o.key)?.get(time) ?? null)]))},
    };
  }, [history, options, source, simulationResult]);
  const available = selected.filter(o => result.variables[o.key]?.some(value => value !== null && Number.isFinite(value)));
  return <section className={`sumo-overlay-card ${className}`}>
    <div className="chart-head"><h3>{t(title)}</h3></div>
    <div className="sumo-group-dropdowns">
      <VariableDropdown title={groupTitle} options={options} selected={selected.map(o => o.key)} onChange={setSelection} />
      <label className="sumo-axis-toggle"><input type="checkbox" checked={secondary} onChange={e => setSecondary(e.target.checked)} />{t("Enable secondary Y axis")}</label>
      {secondary && <VariableDropdown title="Right Y axis" options={selected} selected={right} onChange={setRight} />}
    </div>
    {!selected.length ? <div className="empty"><b>{t("Select variables to build this plot")}</b><span>{t("Choose one or more variables from the dropdowns above.")}</span></div>
      : !available.length ? <div className="empty"><b>{source === 'simulation' ? 'No simulated inputs yet' : t("No sensor readings yet")}</b><span>{source === 'simulation' ? 'Database inputs appear as simulation progresses.' : t("Connect KEPServer to display live sensor trends.")}</span></div>
      : <SumoOutputPlot settingsKey={settingsKey} result={result} timestamps={timestamps} variables={available.map(o => o.key)}
          rightAxis={secondary ? right : []} overlay runId={runId} options={options} />}
  </section>;
}
