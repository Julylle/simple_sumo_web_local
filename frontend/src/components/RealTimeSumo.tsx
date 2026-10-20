import { useEffect, useRef, useState } from 'react';
import Plot from 'react-plotly.js';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type Option = {name:string;label:string;unit:string};
type Reading = {column:string;node_id:string;value:number;timestamp:string};
type Sample = Reading & { receivedAt: number };
type Run = {id:string;status:'running'|'completed'|'failed';error?:string;progress_pct?:number;phase?:string;result?:{time_h:number[];variables:Record<string,number[]>}};
const defaultNode = 'ns=2;s=GEeth.PLC128.Influent_ammonia_sensor';
const defaultColumn = 'Sumo__Plant__Influent__param__Ammonia_sensor_Horiba';
async function json(url:string,init?:RequestInit) {
  const response=await fetch(url,init);
  const body=await response.json().catch(()=>null);
  if(!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}
export function RealTimeSumo(){
  const [options,setOptions]=useState<Option[]>([]);
  const [mapping,setMapping]=useState<Record<string,string>>({[defaultColumn]:defaultNode});
  const [readings,setReadings]=useState<Reading[]>([]);
  const [history,setHistory]=useState<Sample[]>([]);
  const [secondaryAxis,setSecondaryAxis]=useState(false);
  const [rightAxisVariables,setRightAxisVariables]=useState<string[]>([]);
  const [connected,setConnected]=useState(false);
  const [sensorError,setSensorError]=useState('');
  const pollingRef=useRef(false);
  const mappingRef=useRef(mapping);
  mappingRef.current=mapping;
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [duration,setDuration]=useState('168');
  const [run,setRun]=useState<Run|null>(null);
  const [downloading,setDownloading]=useState(false);
  useEffect(()=>{json('/api/sumo/input-options').then(setOptions).catch(e=>setError(String(e)));},[]);
  useEffect(()=>{
    if(run?.status!=='running')return;
    let active=true;
    const timer=setInterval(()=>{json(`/api/sumo/runs/${run.id}`).then(next=>{if(active)setRun(next);}).catch(e=>{if(active)setError(String(e));});},2000);
    return ()=>{active=false;clearInterval(timer);};
  },[run?.id,run?.status]);
  useEffect(()=>{
    if(!connected)return;
    let cancelled=false;
    const poll=async()=>{
      if(pollingRef.current)return;
      pollingRef.current=true;
      try{
        const selected=Object.fromEntries(Object.entries(mappingRef.current).filter(([,node])=>node.trim()));
        const result=await json('/api/kepserver/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping:selected})});
        if(cancelled)return;
        const receivedAt=Date.now();
        setReadings(result.readings);
        setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-7200));
        setSensorError('');
      }catch(e){if(!cancelled)setSensorError(String(e));}
      finally{pollingRef.current=false;}
    };
    const timer=setInterval(()=>{void poll();},5000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[connected]);
  function changeMapping(column:string,node:string){
    setConnected(false);setHistory([]);setSensorError('');
    setMapping(old=>({...old,[column]:node}));setReadings([]);setRun(null);
  }
  async function refresh(){
    setConnected(false);setBusy(true);setError('');setSensorError('');setReadings([]);setHistory([]);setRun(null);
    try {
      const selected=Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()));
      const result=await json('/api/kepserver/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping:selected})});
      setReadings(result.readings);
      setHistory((result.readings as Reading[]).map(r=>({...r,receivedAt:Date.now()})));
      setConnected(true);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function start(){
    setBusy(true);setError('');
    try{
      const prepared=await json('/api/kepserver/prepare-input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({readings})});
      const result=await json('/api/sumo/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({duration_h:Number(duration),input_id:prepared.id,input_columns:prepared.columns})});
      setRun(result);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function download(){
    if(!run?.id)return;
    setDownloading(true);
    try{
      const response=await fetch(`/api/sumo/runs/${run.id}/download`);
      if(!response.ok)throw new Error('Result download failed');
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');link.href=url;link.download=`sumo_results_${run.id}.csv`;link.click();
      URL.revokeObjectURL(url);
    }catch(e){setError(String(e));}finally{setDownloading(false);}
  }
  const running=busy||run?.status==='running';
  return <>
    <section className="page-head"><div><h1>SUMO Real-time Simulation</h1><p>Cixi Eastern WWTP · KEPServer OPC UA · Manual simulation</p></div></section>
    <section className="config-card">
      <div className="section-title"><div><h2>Simulation settings</h2></div></div>
      <h3>Step1: Connect sensors through KEPServer</h3>
      <p className="calibration-note">Enter OPC UA Node IDs for the desired SUMO influent parameters. The backend connection URL is configured using KEPSERVER_OPC_URL.</p>
      <div className="fields">
        {options.map(option=><label className="field" key={option.name}>
          <span className="field-label">{option.label} ({option.unit})</span>
          <div className="input-wrap"><input type="text" value={mapping[option.name]||''} disabled={running} placeholder="ns=2;s=..." onChange={e=>changeMapping(option.name,e.target.value)}/></div>
        </label>)}
      </div>
      <p><button className="secondary" disabled={running||!Object.values(mapping).some(Boolean)} onClick={refresh}>{busy?'Reading sensors...':'Connect / Refresh sensor data'}</button> <button className="secondary" disabled={!connected} onClick={()=>setConnected(false)}>Disconnect</button> <span role="status">{connected?'Connected · sampling every 5 s':'Disconnected'}</span></p>
      {sensorError&&<div className="alert" role="alert">Sensor update failed: {sensorError}</div>}
      <h3 className="sumo-step-title">Step2: Review sensor snapshot and model inputs</h3>
      {readings.length>0?<table><thead><tr><th>SUMO parameter</th><th>Sensor value</th><th>UTC timestamp</th></tr></thead><tbody>
        {readings.map(r=><tr key={r.column}><td>{r.column.split('__').pop()}</td><td>{r.value} {options.find(o=>o.name===r.column)?.unit}</td><td>{r.timestamp}</td></tr>)}
      </tbody></table>:<p className="calibration-note">No sensor snapshot loaded. Read sensors before starting a simulation.</p>}
      <p className="calibration-note">Sensor chart updates every 5 seconds while connected. Run SUMO still uses the latest snapshot as constant model input; live Scheduler integration is separate.</p>
      <h3 className="sumo-step-title">Step3: Set up simulation duration</h3>
      <label className="field"><span className="field-label">Duration (hours)</span><div className="input-wrap"><input type="number" min="1" max="168" step="any" value={duration} disabled={running} onChange={e=>setDuration(e.target.value)}/></div></label>
      <p><button className="primary" disabled={running||!readings.length||!(Number(duration)>=1&&Number(duration)<=168)} onClick={start}>{running?'Running / preparing...':'Run SUMO'}</button></p>
      {run&&<div className="sumo-progress"><p role="status">{run.phase||run.status} · {Math.floor(run.progress_pct||0)}%</p><progress max="100" value={run.progress_pct||0}/></div>}
      {(error||run?.error)&&<div className="alert" role="alert">{error||run?.error}</div>}
    </section>
    <section className="config-card"><div className="section-title"><div><h2>Output variables visualisation</h2></div><button className="secondary" disabled={run?.status!=='completed'||downloading} onClick={download}>Download results CSV</button></div>
      <section className="sumo-overlay-card">
        <div className="chart-head"><h3>Influent variables · live sensor trends</h3></div>
        <div className="sumo-group-dropdowns">
          <label className="sumo-axis-toggle">
            <input type="checkbox" checked={secondaryAxis} onChange={e=>setSecondaryAxis(e.target.checked)}/>
            Enable secondary Y axis
          </label>
          {secondaryAxis && <details className="sumo-variable-dropdown">
            <summary>Right Y axis <span>{rightAxisVariables.filter(key=>history.some(s=>s.column===key)).length} selected</span></summary>
            <div className="sumo-variable-options">
              {Object.keys(mapping).filter(key=>history.some(s=>s.column===key)).map(key=><label key={key}>
                <input type="checkbox" checked={rightAxisVariables.includes(key)}
                  onChange={e=>setRightAxisVariables(old=>e.target.checked?[...old,key]:old.filter(item=>item!==key))}/>
                {key.split('__').pop()} <small>{options.find(o=>o.name===key)?.unit||''}</small>
              </label>)}
            </div>
          </details>}
        </div>
        {history.length?<Plot style={{width:'100%',height:380}} useResizeHandler
          data={Object.keys(mapping).filter(key=>history.some(s=>s.column===key)).map(key=>({
            x:history.filter(s=>s.column===key).map(s=>new Date(s.receivedAt)),
            y:history.filter(s=>s.column===key).map(s=>s.value),
            type:'scatter' as const,mode:'lines+markers' as const,
            name:key.split('__').pop()||key,
            yaxis:secondaryAxis&&rightAxisVariables.includes(key)?'y2' as const:'y' as const
          }))}
          layout={{autosize:true,height:380,
            margin:{t:20,b:65,l:75,r:secondaryAxis?75:20},
            xaxis:{title:{text:'Sensor timestamp'}},
            yaxis:{title:{text:'Sensor reading (left axis)'}},
            ...(secondaryAxis?{yaxis2:{title:{text:'Sensor reading (right axis)'},overlaying:'y' as const,side:'right' as const,showgrid:false}}:{}),
            showlegend:true}}
          config={{responsive:true,displaylogo:false}}/>
          :<p className="calibration-note">Connect KEPServer to display live influent sensor trends.</p>}
      </section>
      <SumoOutputDashboard influent={readings.map(r=>({key:r.column,label:`Influent ${r.column.split('__').pop()}`,unit:options.find(o=>o.name===r.column)?.unit||''}))} result={run?.result} runId={run?.id||''}/>
    </section>
  </>;
}
