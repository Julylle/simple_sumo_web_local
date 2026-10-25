import { useState } from 'react';
import Plot from 'react-plotly.js';
import { VariableDropdown } from './SumoOutputDashboard';
import type { OutputOption } from './sumoOutputs';

type Sample = { column: string; value: number; receivedAt: number };

export function LiveSensorPlot({ title, groupTitle, options, history, axisTitle, className = '' }: {
  title: string; groupTitle: string; options: OutputOption[]; history: Sample[];
  axisTitle: string; className?: string;
}) {
  const [selection, setSelection] = useState<string[] | null>(null);
  const [secondary, setSecondary] = useState(false);
  const [right, setRight] = useState<string[]>([]);
  const selected = options.filter(o => selection === null || selection.includes(o.key));
  const available = selected.filter(o => history.some(s => s.column === o.key));
  return <section className={`sumo-overlay-card ${className}`}>
    <div className="chart-head"><h3>{title}</h3></div>
    <div className="sumo-group-dropdowns">
      <VariableDropdown title={groupTitle} options={options} selected={selected.map(o => o.key)} onChange={setSelection} />
      <label className="sumo-axis-toggle"><input type="checkbox" checked={secondary} onChange={e => setSecondary(e.target.checked)} />Enable secondary Y axis</label>
      {secondary && <VariableDropdown title="Right Y axis" options={selected} selected={right} onChange={setRight} />}
    </div>
    {!selected.length ? <div className="empty"><b>Select variables to build this plot</b><span>Choose one or more variables from the dropdown above.</span></div>
      : !available.length ? <p className="calibration-note">Connect KEPServer to display live sensor trends.</p>
      : <Plot style={{width:'100%',height:380}} useResizeHandler
        data={available.map(o => ({
          x: history.filter(s => s.column === o.key).map(s => new Date(s.receivedAt)),
          y: history.filter(s => s.column === o.key).map(s => s.value),
          type: 'scatter' as const, mode: 'lines+markers' as const, name: o.label,
          yaxis: secondary && right.includes(o.key) ? 'y2' as const : 'y' as const,
        }))}
        layout={{autosize:true,height:380,margin:{t:20,b:65,l:75,r:secondary?75:20},
          xaxis:{title:{text:'Sensor timestamp'}},
          yaxis:{title:{text:axisTitle + (secondary?' · left axis':'')}},
          ...(secondary ? {yaxis2:{title:{text:axisTitle+' · right axis'},overlaying:'y' as const,side:'right' as const,showgrid:false}} : {}),
          showlegend:true}}
        config={{responsive:true,displaylogo:false}} />}
  </section>;
}
