import Plot from 'react-plotly.js';
import type { Config } from 'plotly.js';
import type { Params } from '../api/client';
import type { SimulationRun } from '../hooks/useSimulation';
import { Empty } from './EmptyState';

const plotConfig: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
};

function fmt(value: number, digits = 1) {
  return Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: digits })
    : '?';
}

interface SimulationResultsProps {
  data: SimulationRun | null;
  parameters: Params;
}

export function SimulationResults({ data, parameters }: SimulationResultsProps) {
  const final = data ? {
    cod: data.cod_mg_l.slice(-1)[0],
    nh4: data.nh4_mg_l.slice(-1)[0],
    n2o: Math.max(...data.n2o_index),
  } : null;

  return <>
    <section className="results-head"><div><h2>Results</h2><p>{data?'Latest approved simulation outputs':'Run the model to generate results'}</p></div>{data&&<div className="result-meta"><span>● Completed</span><b>{data.time_h.length} displayed points</b></div>}</section>
    <section className="kpis">{([
      ['Final COD',final?.cod,'mg/L',data?`${fmt((1-final!.cod/parameters.influent_cod_mg_l)*100,1)}% removal`:'Awaiting run'],
      ['Final NH₄-N',final?.nh4,'mg/L',data?`${fmt((1-final!.nh4/parameters.influent_nh4_mg_l)*100,1)}% removal`:'Awaiting run'],
      ['Peak N₂O index',final?.n2o,'index',data?'Synthetic demo indicator':'Awaiting run'],
      ['Runtime',data?data.runtimeSeconds:undefined,'s',data?'API round-trip time':'Awaiting run']
    ] as [string, number | undefined, string, string][]).map(([name,val,unit,sub])=><div className="kpi" key={name}><span>{name}</span><div><b>{val===undefined?'—':fmt(val,val<10?3:1)}</b><small>{unit}</small></div><p>{sub}</p></div>)}</section>
    <section className="chart-grid">
     <div className="chart-card wide"><div className="chart-head"><div><h3>Concentration profiles</h3><p>Approved and downsampled model states</p></div><span className="chart-chip">Time series</span></div>{data?<Plot data={[{x:data.time_h,y:data.cod_mg_l,type:'scatter',mode:'lines',name:'COD',line:{width:2.5}},{x:data.time_h,y:data.nh4_mg_l,type:'scatter',mode:'lines',name:'NH₄-N',line:{width:2.5}}]} layout={{autosize:true,height:380,hovermode:'x unified',paper_bgcolor:'transparent',plot_bgcolor:'transparent',legend:{orientation:'h',x:0,y:1.12},xaxis:{title:{text:'Time (h)'},gridcolor:'#edf0f4'},yaxis:{title:{text:'Concentration (mg/L)'},gridcolor:'#edf0f4'},margin:{l:65,r:25,t:55,b:60}}} useResizeHandler style={{width:'100%'}} config={plotConfig}/>:<Empty title="No simulation results" text="Configure parameters above and run the ODE model."/>}</div>
     <div className="chart-card"><div className="chart-head"><div><h3>N₂O indicator</h3><p>Demo output for UI integration testing</p></div></div>{data?<Plot data={[{x:data.time_h,y:data.n2o_index,type:'scatter',mode:'lines',name:'N₂O index',fill:'tozeroy',line:{width:2}}]} layout={{autosize:true,height:310,hovermode:'x',paper_bgcolor:'transparent',plot_bgcolor:'transparent',showlegend:false,xaxis:{title:{text:'Time (h)'},gridcolor:'#edf0f4'},yaxis:{title:{text:'Index'},gridcolor:'#edf0f4'},margin:{l:65,r:25,t:25,b:60}}} useResizeHandler style={{width:'100%'}} config={plotConfig}/>:<Empty title="Awaiting results" text="This panel updates after each model run."/>}</div>
     <div className="chart-card info-card"><div className="chart-head"><div><h3>Run information</h3><p>Execution and data-boundary summary</p></div></div><dl><div><dt>Model</dt><dd>ODE Demo</dd></div><div><dt>Solver</dt><dd>RK4 · server-side</dd></div><div><dt>Raw states</dt><dd>Private</dd></div><div><dt>API output</dt><dd>Allow-listed + downsampled</dd></div><div><dt>Last run</dt><dd>{data?'Completed':'Not run'}</dd></div></dl></div>
    </section>

  </>;
}
