import { localPlotTimestamp } from '../utils/liveSensorDisplay';
import { usePlotSetting } from '../hooks/usePlotSetting';
import { validViewport, stringList } from '../utils/plotSettings';
import { updateViewport, axisViewport, type Viewport } from '../utils/plotViewport';
import { plotLegend } from '../utils/plotLegend';
import { plotInteractionConfig, plotInteractionLayout } from '../plotInteraction';
import { t, useLanguage } from '../i18n';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout } from 'plotly.js';

import { sumoOutputColors, type OutputOption, type ComparisonSeries } from './sumoOutputs';

export function SumoOutputPlot({ result, variables, rightAxis, overlay, options, timestamps, settingsKey }: {
  settingsKey: string;
  result: { simulation_series?: ComparisonSeries; comparison_series?: ComparisonSeries; time_h: number[]; variables: Record<string, (number | null)[]> };
  timestamps?: (string | null)[];
  options: OutputOption[]; variables: string[]; rightAxis: string[]; overlay: boolean; runId: string;
}) {
  const language = useLanguage();
  const frame = useRef<HTMLDivElement>(null);
  const [resetRevision, setResetRevision] = useState(0);
  const viewportScope = timestamps ? 'date' : 'linear';
  const [viewport, setViewport] = usePlotSetting<Viewport>(`${settingsKey}:viewport:${viewportScope}`, {}, validViewport);
  const [hidden, setHidden] = usePlotSetting<string[]>(settingsKey + ':hidden', [], stringList);
  const resetAxes = useCallback(() => {
    setViewport({});
    setResetRevision(value => value + 1);
  }, [setViewport]);
  const [width, setWidth] = useState(0);
  const labels = variables.map(key => `${t(options.find(o => o.key === key)?.label ?? key)} (${options.find(o => o.key === key)?.unit ?? ''})${overlay && rightAxis.includes(key) ? t(' [right]') : ''}`);
  const measureText = useMemo(() => {
    const context = document.createElement('canvas').getContext('2d');
    if (context) context.font = '11px Inter, "Segoe UI", sans-serif';
    return (label: string) => context?.measureText(label).width ?? label.length * 7;
  }, []);
  const legend = plotLegend(labels, width, overlay ? 75 : 25, measureText);
  const plotWidth = overlay ? legend.plotWidth : width;
  const plotHeight = overlay ? 335 : 225;
  const bottom = overlay ? 72 + legend.height : 60;
  const height = 48 + plotHeight + bottom;
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
  const data = useMemo<Data[]>(() => variables.map((key, index) => {
    const right = overlay && rightAxis.includes(key);
    const option = options.find(option => option.key === key);
    const measured = result.comparison_series?.[key];
    const series = measured ?? result.simulation_series?.[key];
    const colorKey = option?.compareTo ?? key;
    return {
      x: series ? series.timestamps.map(value => localPlotTimestamp(Date.parse(value))) : timestamps ?? result.time_h,
      y: series?.values ?? result.variables[key], type: 'scatter', mode: measured ? 'lines+markers' : 'lines',
      connectgaps: false, marker: {size: 5},
      opacity: measured ? 0.45 : 1,
      name: legend.names[index],
      yaxis: right ? 'y2' : 'y',
      visible: hidden.includes(key) ? 'legendonly' : true,
      line: { color: sumoOutputColors[Math.max(0, options.findIndex(o => o.key === colorKey)) % sumoOutputColors.length], width: 2.5, dash: measured ? 'dot' : right ? 'dash' : 'solid' },
      hovertemplate: `${timestamps ? '%{x|%Y-%m-%d %H:%M:%S.%L}' : '%{x:.2f} h'}<br>%{y:.3f} ${options.find(o => o.key === key)?.unit ?? ''}<extra>%{fullData.name}</extra>`,
    };
  }), [result, timestamps, variables, rightAxis, overlay, options, language, width, hidden]);
  const axisTitle = (right: boolean) => {
    const units = [...new Set(options.filter(o => variables.includes(o.key) && (overlay && rightAxis.includes(o.key)) === right).map(o => o.unit))];
    return `${right ? t('Right axis') : t('Value')}${units.length === 1 ? ` (${units[0]})` : t(' (see legend / hover units)')}`;
  };
  const leftTitle = axisTitle(false), rightTitle = axisTitle(true);
  const hasTimestamps = !!timestamps;
  const layout = useMemo<Partial<Layout>>(() => ({
    // Dimensions belong to the container, not the axis viewport. Reset axes
    // changes ranges only; resize the plot only when its container changes.
    ...plotInteractionLayout,
    autosize: false, width: plotWidth, height,
    uirevision: `${viewportScope}:${resetRevision}`,
    paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff',
    font: { family: 'Inter, Segoe UI, sans-serif', size: 11, color: '#64748b' },
    xaxis: { ...axisViewport(viewport, 'xaxis'), type: hasTimestamps ? 'date' : 'linear', hoverformat: hasTimestamps ? '%Y-%m-%d %H:%M:%S.%L' : undefined, title: { text: hasTimestamps ? t('Sensor timestamp (computer local time)') : t('Time (h)'), standoff: 12 }, gridcolor: '#f1f5f9',
      zeroline: false, showline: true, linecolor: '#cbd5e1', ticks: 'outside', tickcolor: '#cbd5e1', automargin: false },
    yaxis: { ...axisViewport(viewport, 'yaxis'), title: { text: leftTitle, standoff: 12 },
      gridcolor: '#e8edf3', zeroline: false, rangemode: 'tozero', tickformat: '~g', automargin: false },
    ...(hasRight ? { yaxis2: { ...axisViewport(viewport, 'yaxis2'), title: { text: rightTitle, standoff: 12 }, overlaying: 'y', side: 'right',
      showgrid: false, zeroline: false, rangemode: 'tozero', tickformat: '~g', automargin: false } } : {}),
    showlegend: overlay, legend: { orientation: 'h', y: -64 / plotHeight, yanchor: 'top', x: 0, xanchor: 'left',
      font: { size: 11 }, maxheight: legend.height },
    margin: { t: 48, b: bottom, l: 75, r: overlay ? 75 : 25, autoexpand: false },
    hovermode: 'x unified', hoverlabel: { bgcolor: '#ffffff', bordercolor: '#e2e8f0', font: { size: 12 } },
    dragmode: 'zoom',
  }), [height, overlay, hasRight, leftTitle, rightTitle, language, hasTimestamps, bottom, plotWidth, legend.height, resetRevision, viewport, viewportScope]);
  const config = useMemo(() => ({
    ...plotInteractionConfig(language), responsive: false,
    modeBarButtons: [['toImage', { name: 'Reset axes', title: t('Reset axes'),
      icon: { width: 24, height: 24, path: 'M4 4v6h6L7.5 7.5A7 7 0 1 1 5 13H3a9 9 0 1 0 3-7L4 4z' },
      click: resetAxes }, 'zoom2d']],
    toImageButtonOptions: { format: 'png' as const, filename: 'sumo-comparison', scale: 2 },
  }), [language, resetAxes]);
  return <div ref={frame} className="sumo-plot-frame" style={{ height: height + (plotWidth > width ? 18 : 0), overflowX: 'auto' }}>
    {width > 0 && <Plot data={data} layout={layout}
      onRelayout={event => setViewport(current => updateViewport(current, event as unknown as Record<string, unknown>))}
      onRestyle={event => {
        const [changes, indices] = event as unknown as [Record<string, unknown>, number[]];
        if (!('visible' in changes)) return;
        setHidden(current => {
          const next = new Set(current);
          indices.forEach((index, position) => {
            const key = variables[index];
            if (!key) return;
            const visible = Array.isArray(changes.visible) ? changes.visible[position % changes.visible.length] : changes.visible;
            if (visible === 'legendonly' || visible === false) next.add(key);
            else if (visible === true) next.delete(key);
          });
          return [...next];
        });
      }}
      config={config}
      style={{ width: plotWidth, height }} />}
  </div>;
}
