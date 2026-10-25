import { plotLocale } from '../plotLocale';
import { t, useLanguage } from '../i18n';
import { useEffect, useMemo, useRef, useState } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout } from 'plotly.js';

import { sumoOutputColors, type OutputOption } from './sumoOutputs';

export function SumoOutputPlot({ result, variables, rightAxis, overlay, runId, options, timestamps }: {
  result: { time_h: number[]; variables: Record<string, (number | null)[]> };
  timestamps?: string[];
  options: OutputOption[]; variables: string[]; rightAxis: string[]; overlay: boolean; runId: string;
}) {
  const language = useLanguage();
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const height = overlay ? 480 : 320;
  useEffect(() => {
    if (!frame.current) return;
    const observer = new ResizeObserver(entries => {
      const nextWidth = Math.floor(entries[0].contentRect.width);
      // Hidden tabs report zero; retain the last usable dimensions.
      if (nextWidth > 0) setWidth(current => current === nextWidth ? current : nextWidth);
    });
    observer.observe(frame.current);
    return () => observer.disconnect();
  }, []);
  const axisKey = overlay ? rightAxis.filter(key => variables.includes(key)).join(',') : '';
  const hasRight = !!axisKey;
  const data = useMemo<Data[]>(() => variables.map(key => {
    const right = overlay && rightAxis.includes(key);
    return {
      x: timestamps ?? result.time_h, y: result.variables[key], type: 'scatter', mode: 'lines',
      name: `${t(options.find(o => o.key === key)?.label ?? key)} (${options.find(o => o.key === key)?.unit ?? ''})${right ? t(' [right]') : ''}`,
      yaxis: right ? 'y2' : 'y',
      line: { color: sumoOutputColors[Math.max(0, options.findIndex(o => o.key === key)) % sumoOutputColors.length], width: 2.5, dash: right ? 'dash' : 'solid' },
      hovertemplate: `${timestamps ? '%{x|%Y-%m-%d %H:%M:%S}' : '%{x:.2f} h'}<br>%{y:.3f} ${options.find(o => o.key === key)?.unit ?? ''}<extra>%{fullData.name}</extra>`,
    };
  }), [result, timestamps, variables, rightAxis, overlay, options, language]);
  const axisTitle = (right: boolean) => {
    const units = [...new Set(options.filter(o => variables.includes(o.key) && (overlay && rightAxis.includes(o.key)) === right).map(o => o.unit))];
    return `${right ? t('Right axis') : t('Value')}${units.length === 1 ? ` (${units[0]})` : t(' (see legend / hover units)')}`;
  };
  const leftTitle = axisTitle(false), rightTitle = axisTitle(true);
  const layout = useMemo<Partial<Layout>>(() => ({
    // Dimensions belong to the container, not the axis viewport. Reset axes
    // changes ranges only; resize the plot only when its container changes.
    autosize: false, width, height,
    uirevision: `${runId}:${overlay}:${variables.join(',')}:${axisKey}`,
    paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
    font: { family: 'Inter, Segoe UI, sans-serif', size: 11, color: '#64748b' },
    xaxis: { title: { text: timestamps ? t('Sensor timestamp (computer local time)') : t('Time (h)'), standoff: 12 }, gridcolor: '#f1f5f9',
      zeroline: false, showline: true, linecolor: '#cbd5e1', ticks: 'outside', tickcolor: '#cbd5e1', automargin: false },
    yaxis: { title: { text: leftTitle, standoff: 12 },
      gridcolor: '#e8edf3', zeroline: false, rangemode: 'tozero', tickformat: '~g', automargin: false },
    ...(hasRight ? { yaxis2: { title: { text: rightTitle, standoff: 12 }, overlaying: 'y', side: 'right',
      showgrid: false, zeroline: false, rangemode: 'tozero', tickformat: '~g', automargin: false } } : {}),
    showlegend: overlay, legend: { orientation: 'h', y: -0.22, x: 0, font: { size: 11 }, maxheight: 95 },
    margin: { t: 35, b: overlay ? 110 : 60, l: 75, r: overlay ? 75 : 25, autoexpand: false },
    hovermode: 'x unified', hoverlabel: { bgcolor: '#ffffff', bordercolor: '#e2e8f0', font: { size: 12 } },
    dragmode: 'zoom',
  }), [width, height, runId, overlay, variables, axisKey, hasRight, leftTitle, rightTitle, language, timestamps]);
  return <div ref={frame} className="sumo-plot-frame" style={{ height }}>
    {width > 0 && <Plot data={data} layout={layout}
      config={{ ...plotLocale(language), responsive: false, displaylogo: false, displayModeBar: true, doubleClick: 'reset',
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        toImageButtonOptions: { format: 'png', filename: 'sumo-comparison', scale: 2 } }}
      style={{ width: '100%', height: '100%' }} />}
  </div>;
}
