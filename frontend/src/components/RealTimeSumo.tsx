import { useEffect, useRef, useState } from 'react';
import Plot from 'react-plotly.js';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type Option = {name:string;label:string;unit:string};
type Reading = {column:string;node_id:string;value:number;timestamp:string};
type Sample = Reading & { receivedAt: number };
type LiveRun = {id?:string;status:string;phase?:string;error?:string;simulated_h?:number;samples?:number;result?:{time_h:number[];variables:Record<string,number[]>}};
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
  const [selectedColumn,setSelectedColumn]=useState(defaultColumn);
  const [nodeDraft,setNodeDraft]=useState(defaultNode);
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
  const [limitMinutes,setLimitMinutes]=useState('5');
  const [run,setRun]=useState<Run|null>(null);
  const [liveRun,setLiveRun]=useState<LiveRun|null>(null);
  const [downloading,setDownloading]=useState(false);
  useEffect(()=>{json('/api/sumo/input-options').then(setOptions).catch(e=>setError(String(e)));},[]);
  useEffect(()=>{
    if(run?.status!=='running')return;
    let active=true;
    const timer=setInterval(()=>{json(`/api/sumo/runs/${run.id}`).then(next=>{if(active)setRun(next);}).catch(e=>{if(active)setError(String(e));});},2000);
    return ()=>{active=false;clearInterval(timer);};
  },[run?.id,run?.status]);
  useEffect(()=>{
    let active=true;
    const poll=async()=>{
      try{
        const next:LiveRun=await json('/api/sumo/live/status');
        if(active)setLiveRun(next.status==='idle'?null:next);
      }catch(e){if(active)setError(String(e));}
    };
    void poll();
    const timer=setInterval(()=>{void poll();},2000);
    return()=>{active=false;clearInterval(timer);};
  },[]);
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
      const selected=Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()));
      const result:LiveRun=await json('/api/sumo/live/start',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mapping:selected,interval_minutes:Number(limitMinutes)})});
      setLiveRun(result);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function stop(){
    setBusy(true);setError('');
    try{setLiveRun(await json('/api/sumo/live/stop',{method:'POST'}));}
    catch(e){setError(String(e));}finally{setBusy(false);}
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
  const liveActive=['starting','running','stopping'].includes(liveRun?.status||'');
  const running=busy||liveActive;
  return <>
    <section className="page-head"><div><h1>SUMO Real-time Simulation</h1><p>Cixi Eastern WWTP · KEPServer OPC UA · Manual simulation</p></div></section>
    <section className="config-card">
      <div className="section-title"><div><h2>Simulation settings</h2></div></div>
      <h3>Step1: Connect sensors through KEPServer</h3>
      <p className="calibration-note">Select a SUMO influent variable from the dropdown, enter its KEPServer OPC UA Node ID, then add the mapping. Existing mappings can be changed or removed below.</p>
      <div className="fields">
        <label className="field"><span className="field-label">Influent variable</span>
          <select value={selectedColumn} disabled={running} onChange={e=>{const key=e.target.value;setSelectedColumn(key);setNodeDraft(mapping[key]||'');}}>
            {options.map(option=><option key={option.name} value={option.name}>{option.label} ({option.unit})</option>)}
          </select>
        </label>
        <label className="field"><span className="field-label">KEPServer OPC UA Node ID</span>
          <div className="input-wrap"><input type="text" value={nodeDraft} disabled={running} placeholder="ns=2;s=..." onChange={e=>setNodeDraft(e.target.value)}/></div>
        </label>
      </div>
      <p><button className="secondary" disabled={running||!selectedColumn||!nodeDraft.trim()} onClick={()=>changeMapping(selectedColumn,nodeDraft.trim())}>Add / Update sensor mapping</button></p>
      <div className="sumo-group-dropdowns">
        <details className="sumo-variable-dropdown"><summary>Connected sensor mappings <span>{Object.keys(mapping).length} selected</span></summary>
          <div className="sumo-variable-options">
            {Object.entries(mapping).map(([column,node])=><div key={column} style={{padding:'8px 0'}}>
              <strong>{options.find(o=>o.name===column)?.label||column.split('__').pop()}</strong>
              <div style={{overflowWrap:'anywhere',fontSize:12}}>{node}</div>
              <button className="secondary" disabled={running} onClick={()=>{
                setConnected(false);setHistory([]);setReadings([]);setSensorError('');
                setMapping(old=>{const next={...old};delete next[column];return next;});
                if(selectedColumn===column)setNodeDraft('');
              }}>Remove</button>
            </div>)}
          </div>
        </details>
      </div>
      <p><button className="secondary" disabled={running||!Object.values(mapping).some(Boolean)} onClick={refresh}>{busy?'Reading sensors...':'Connect / Refresh sensor data'}</button> <button className="secondary" disabled={!connected} onClick={()=>setConnected(false)}>Disconnect</button> <span role="status">{connected?'Connected · sampling every 5 s':'Disconnected'}</span></p>
      {sensorError&&<div className="alert" role="alert">Sensor update failed: {sensorError}</div>}
      <h3 className="sumo-step-title">Step2: Set up real time simulation</h3>
      <div className="fields">
        <label className="field"><span className="field-label">Simulation mode</span>
          <div className="input-wrap"><input value="Live · continuous (1×)" readOnly aria-label="Simulation mode"/></div>
        </label>
        <label className="field"><span className="field-label">Input update interval / Limit time (minutes)</span>
          <div className="input-wrap"><input type="number" min="1" max="60" step="1" value={limitMinutes} disabled={running} onChange={e=>setLimitMinutes(e.target.value)}/></div>
        </label>
        <label className="field"><span className="field-label">Operation</span>
          <div className="input-wrap"><input value="Continuous · until Stop SUMO" readOnly aria-label="Simulation operation"/></div>
        </label>
      </div>
      <p className="calibration-note">Live-only mode: SUMO will run continuously until manually stopped, using the selected input update interval. The model runs in one persistent Scheduler session until Stop SUMO is clicked.</p>
      <p><button className="primary" disabled={running||!connected||!(Number(limitMinutes)>=1&&Number(limitMinutes)<=60)} onClick={()=>void start()}>Run SUMO</button> <button className="secondary" disabled={busy||!['starting','running'].includes(liveRun?.status||'')} onClick={()=>void stop()}>Stop SUMO</button></p>
      {liveRun&&<div className="sumo-progress"><p role="status">{liveRun.status} · {liveRun.phase||''} · {(liveRun.simulated_h||0).toFixed(2)} simulated hours · {liveRun.samples||0} output samples</p>{liveRun.error&&<div className="alert">{liveRun.error}</div>}</div>}
      {run&&<div className="sumo-progress"><p role="status">{run.phase||run.status} · {Math.floor(run.progress_pct||0)}%</p><progress max="100" value={run.progress_pct||0}/></div>}
      {(error||run?.error)&&<div className="alert" role="alert">{error||run?.error}</div>}
    </section>
    <section className="config-card"><div className="section-title"><div><h2>Output variables visualisation</h2></div><button className="secondary" disabled={!liveRun?.result?.time_h?.length||downloading} onClick={async()=>{setDownloading(true);try{const response=await fetch('/api/sumo/live/download');if(!response.ok)throw Error('Download failed');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='sumo_live_results.csv';link.click();URL.revokeObjectURL(url);}catch(e){setError(String(e));}finally{setDownloading(false);}}}>Download results CSV</button></div>
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
      <SumoOutputDashboard showInfluent={false} influent={readings.map(r=>({key:r.column,label:`Influent ${r.column.split('__').pop()}`,unit:options.find(o=>o.name===r.column)?.unit||''}))} result={liveRun?.result} runId={liveRun?.id||''}/>
    </section>
  </>;
}
