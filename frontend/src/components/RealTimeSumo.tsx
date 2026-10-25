import { defaultDoMapping, doSensorOptions } from '../config/doSensors';
import { useEffect, useMemo, useRef, useState } from 'react';
import { LiveSensorPlot } from './LiveSensorPlot';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type Option = {name:string;label:string;unit:string};
type Reading = {column:string;node_id:string;value:number;timestamp:string};
type Sample = Reading & { receivedAt: number };
type UploadedModel = {id:string;name:string;state_name:string};
type LiveRun = {id?:string;model_id?:string;model_name?:string;status:string;phase?:string;error?:string;simulated_h?:number;samples?:number;result?:{time_h:number[];variables:Record<string,number[]>}};
type Run = {id:string;status:'running'|'completed'|'failed';error?:string;progress_pct?:number;phase?:string;result?:{time_h:number[];variables:Record<string,number[]>}};
// Default influent mappings from Julylle/Sumo_web/demo_MLE/cx_opcua1124.csv.
const defaultMapping: Record<string,string> = {
  "Sumo__Plant__Influent__param__Q": "ns=2;s=SiemensEth.PLC204.F_Q0",
  "Sumo__Plant__Influent__param__pH": "ns=2;s=GEeth.PLC128.pH",
  "Sumo__Plant__Influent__param__T": "ns=2;s=GEeth.PLC128.Temperature",
  "Sumo__Plant__Influent__param__Ammonia_sensor_Horiba": "ns=2;s=GEeth.PLC132.Influent_ammonia_sensor(Horiba)",
  "Sumo__Plant__Influent__param__COD_lab": "ns=2;s=MySQL.Dev1.inlet_cod.inlet_cod__1_",
  "Sumo__Plant__Influent__param__TKN_lab": "ns=2;s=MySQL.Dev1.inlet_tn.inlet_tn__1_",
  "Sumo__Plant__Influent__param__Ammonia_lab": "ns=2;s=MySQL.Dev1.inlet_nh3n.inlet_nh3n__1_",
  "Sumo__Plant__Influent__param__TSS_sensor": "ns=2;s=GEeth.PLC128.Influent_TSS_sensor(HACH)",
  "Sumo__Plant__Influent__param__Ammonia_analyzer": "ns=2;s=GEeth.PLC128.JS_NH3N",
  "Sumo__Plant__Influent__param__TCOD": "ns=2;s=MySQL.Dev4.COD_nh3_sen_ratio",
  "Sumo__Plant__Influent__param__TKN": "ns=2;s=MySQL.Dev4.TN_nh3_sen_ratio",
  "Sumo__Plant__Influent__param__TP": "ns=2;s=MySQL.Dev1.inlet_tp.inlet_tp__1_"
};
// These 12 configured inputs must remain selectable even if the SUMO API is offline.
const influentUnits: Record<string,string> = {
  Q: 'm3/d', pH: 'pH', T: 'deg C', Ammonia_sensor_Horiba: 'mg/L',
  COD_lab: 'mg/L', TKN_lab: 'mg/L', Ammonia_lab: 'mg/L', TSS_sensor: 'mg/L',
  Ammonia_analyzer: 'mg/L', TCOD: 'mg COD/L', TKN: 'mg N/L', TP: 'mg P/L',
};
const options: Option[] = Object.keys(defaultMapping).map(name => {
  const label = name.split('__').pop()!;
  return {name, label, unit: influentUnits[label]};
});
const defaultColumn = 'Sumo__Plant__Influent__param__Ammonia_sensor_Horiba';
const defaultNode = defaultMapping[defaultColumn];
async function json(url:string,init?:RequestInit) {
  const response=await fetch(url,init);
  const body=await response.json().catch(()=>null);
  if(!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}
export function RealTimeSumo(){
  const [mapping,setMapping]=useState<Record<string,string>>(()=>({...defaultMapping,...defaultDoMapping}));
  const [selectedColumn,setSelectedColumn]=useState(defaultColumn);
  const [nodeDraft,setNodeDraft]=useState(defaultNode);
  const [selectedDo,setSelectedDo]=useState(doSensorOptions[0].name);
  const [doDraft,setDoDraft]=useState(defaultDoMapping[doSensorOptions[0].name]);
  const [readings,setReadings]=useState<Reading[]>([]);
  const [history,setHistory]=useState<Sample[]>([]);
  // Display the same converted flow used by SUMO without changing raw readings.
  const influentPlotHistory=useMemo(()=>history.map(sample=>
    sample.column==='Sumo__Plant__Influent__param__Q'
      ? {...sample,value:sample.value/0.0417}
      : sample
  ),[history]);
  const [connected,setConnected]=useState(false);
  const [sensorError,setSensorError]=useState('');
  const pollingRef=useRef(false);
  const mappingRef=useRef(mapping);
  mappingRef.current=mapping;
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [limitMinutes,setLimitMinutes]=useState('5');
  const [modelSource,setModelSource]=useState('builtin');
  const [modelFile,setModelFile]=useState<File|null>(null);
  const [stateFile,setStateFile]=useState<File|null>(null);
  const [uploadedModel,setUploadedModel]=useState<UploadedModel|null>(null);
  const [modelUploading,setModelUploading]=useState(false);
  const [modelError,setModelError]=useState('');
  const modelReady=modelSource==='builtin'||!!uploadedModel;

  const [run,setRun]=useState<Run|null>(null);
  const [liveRun,setLiveRun]=useState<LiveRun|null>(null);
  const [downloading,setDownloading]=useState(false);
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
        setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-25920));
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
      const receivedAt=Date.now();
      setHistory((result.readings as Reading[]).map(r=>({...r,receivedAt})));
      setConnected(true);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function uploadModel(){
    if(!modelFile||!stateFile)return;
    setModelUploading(true);setModelError('');setUploadedModel(null);
    try{
      if(!modelFile.name.toLowerCase().endsWith('.sumo')||modelFile.size>50*1024*1024)
        throw new Error('Choose a .sumo project no larger than 50 MB.');
      if(!stateFile.name.toLowerCase().endsWith('.xml')||stateFile.size>20*1024*1024)
        throw new Error('Choose an initial-state XML no larger than 20 MB.');
      const form=new FormData();form.append('project',modelFile);form.append('initial_state',stateFile);
      setUploadedModel(await json('/api/sumo/live/models',{method:'POST',body:form}));
    }catch(e){setModelError(String(e));}finally{setModelUploading(false);}
  }
  async function start(){
    if(!modelReady)return;
    setBusy(true);setError('');
    try{
      const selected=Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()));
      const result:LiveRun=await json('/api/sumo/live/start',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mapping:selected,interval_minutes:Number(limitMinutes),model_id:modelSource==='builtin'?'builtin':uploadedModel!.id})});
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
  const running=busy||liveActive||modelUploading;
  const influentPlotOptions=Object.keys(mapping).filter(key=>!defaultDoMapping[key]).map(key=>({
    key,label:options.find(o=>o.name===key)?.label||key.split('__').pop()||key,
    unit:options.find(o=>o.name===key)?.unit||''
  }));
  const doPlotOptions=doSensorOptions.filter(o=>mapping[o.name]).map(o=>({key:o.name,label:o.label,unit:o.unit}));
  return <>
    <section className="page-head"><div><h1>SUMO Real-time Simulation</h1><p>Cixi Eastern WWTP · KEPServer OPC UA · Manual simulation</p></div></section>
    <section className="config-card">
      <div className="section-title"><div><h2>Simulation settings</h2></div></div>
      <section className="sensor-setup" aria-labelledby="sensor-step-title">
        <div className="sensor-heading"><div><h3 id="sensor-step-title">Step1: Connect sensors through KEPServer</h3><p>Review the prefilled tags, then connect to see live influent and dissolved oxygen readings.</p></div><span className={'sensor-status '+(connected?'is-connected':'')} role="status">{connected?'Connected · every 5 s':'Disconnected'}</span></div>
        <div className="sensor-editor-grid">
          {[{title:'Influent variable',items:options,selected:selectedColumn,draft:nodeDraft,setSelected:setSelectedColumn,setDraft:setNodeDraft,isDo:false},
            {title:'DO sensors',items:doSensorOptions,selected:selectedDo,draft:doDraft,setSelected:setSelectedDo,setDraft:setDoDraft,isDo:true}].map(group=><article className="sensor-editor" key={group.title}>
            <div className="sensor-editor-title"><h4>{group.title}</h4><span>{Object.keys(mapping).filter(key=>Boolean(defaultDoMapping[key])===group.isDo).length} mapped</span></div>
            <label className="sensor-field"><span>{group.title}</span><select value={group.selected} onChange={e=>{group.setSelected(e.target.value);group.setDraft(mapping[e.target.value]||'');}}>
              {group.items.map(option=><option key={option.name} value={option.name}>{option.label} ({option.unit})</option>)}
            </select></label>
            <label className="sensor-field"><span>KEPServer OPC UA Node ID</span><input type="text" value={group.draft} disabled={running} placeholder="ns=2;s=..." onChange={e=>group.setDraft(e.target.value)}/></label>
            <button className="secondary" disabled={running||!group.selected||!group.draft.trim()} onClick={()=>changeMapping(group.selected,group.draft.trim())}>Add / Update mapping</button>
            <details className="sensor-mapping-list" onMouseLeave={event => { event.currentTarget.open = false; }}><summary>Review mappings</summary>
              {Object.entries(mapping).filter(([key])=>Boolean(defaultDoMapping[key])===group.isDo).map(([column,node])=><div className="sensor-mapping-row" key={column}>
                <div><strong>{[...options,...doSensorOptions].find(o=>o.name===column)?.label||column.split('__').pop()}</strong><code>{node}</code></div>
                <button className="secondary" aria-label={'Remove '+column} disabled={running} onClick={()=>{
                  setConnected(false);setHistory([]);setReadings([]);setSensorError('');
                  setMapping(old=>{const next={...old};delete next[column];return next;});
                  if(group.selected===column)group.setDraft('');
                }}>Remove</button>
              </div>)}
            </details>
          </article>)}
        </div>
        <div className="sensor-actions"><button className="primary" disabled={running||!Object.values(mapping).some(Boolean)} onClick={refresh}>{busy?'Reading sensors...':connected?'Refresh sensor data':'Connect sensor data'}</button><button className="secondary" disabled={!connected||busy} onClick={()=>setConnected(false)}>Disconnect</button><span>Live charts update automatically after connecting.</span></div>
        {sensorError&&<div className="alert" role="alert">Sensor update failed: {sensorError}</div>}
      </section>
      <h3 className="sumo-step-title">Step2: Set up real time simulation</h3>
      <section className="sensor-setup" aria-label="SUMO model selection">
        <label className="sensor-field"><span>SUMO model</span>
          <select value={modelSource} disabled={running} onChange={e=>{setModelSource(e.target.value);setModelError('');}}>
            <option value="builtin">Built-in · Cixi Eastern WWTP_20260920</option>
            <option value="upload">Upload a SUMO model</option>
          </select>
        </label>
        {modelSource==='builtin'?<p className="calibration-note">Uses the built-in model and sumo_steady_state.xml initial state.</p>:<>
          <p className="calibration-note">Choose a compiled SUMO project and its matching initial state. The model must support your selected sensor variables. Uploads are available until the backend restarts.</p>
          <div className="sensor-editor-grid">
            <label className="sensor-field"><span>SUMO project (.sumo, max 50 MB)</span><input type="file" accept=".sumo" disabled={running} onChange={e=>{setModelFile(e.target.files?.[0]||null);setUploadedModel(null);setModelError('');}}/></label>
            <label className="sensor-field"><span>Initial state (.xml, max 20 MB)</span><input type="file" accept=".xml" disabled={running} onChange={e=>{setStateFile(e.target.files?.[0]||null);setUploadedModel(null);setModelError('');}}/></label>
          </div>
          <div className="sensor-actions"><button className="secondary" disabled={running||!modelFile||!stateFile} onClick={()=>void uploadModel()}>{modelUploading?'Uploading model...':'Upload model and initial state'}</button></div>
          {uploadedModel&&<p role="status" className="measurement-ready">Ready: {uploadedModel.name} · {uploadedModel.state_name}</p>}
        </>}
        {modelError&&<div className="alert" role="alert">{modelError}</div>}
        {liveActive&&liveRun?.model_name&&<p role="status">Running model: {liveRun.model_name}</p>}
      </section>
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
      <p><button className="primary" disabled={running||!modelReady||!connected||!(Number(limitMinutes)>=1&&Number(limitMinutes)<=60)} onClick={()=>void start()}>Run SUMO</button> <button className="secondary" disabled={busy||!['starting','running'].includes(liveRun?.status||'')} onClick={()=>void stop()}>Stop SUMO</button></p>
      {liveRun&&<div className="sumo-progress"><p role="status">{liveRun.status} · {liveRun.phase||''} · {(liveRun.simulated_h||0).toFixed(2)} simulated hours · {liveRun.samples||0} output samples</p>{liveRun.error&&<div className="alert">{liveRun.error}</div>}</div>}
      {run&&<div className="sumo-progress"><p role="status">{run.phase||run.status} · {Math.floor(run.progress_pct||0)}%</p><progress max="100" value={run.progress_pct||0}/></div>}
      {(error||run?.error)&&<div className="alert" role="alert">{error||run?.error}</div>}
    </section>
    <section className="config-card"><div className="section-title"><div><h2>Output variables visualisation</h2></div><button className="secondary" disabled={!liveRun?.result?.time_h?.length||downloading} onClick={async()=>{setDownloading(true);try{const response=await fetch('/api/sumo/live/download');if(!response.ok)throw Error('Download failed');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='sumo_live_results.csv';link.click();URL.revokeObjectURL(url);}catch(e){setError(String(e));}finally{setDownloading(false);}}}>Download results CSV</button></div>
      <LiveSensorPlot title="Influent variables · live sensor trends" groupTitle="Influent variables"
        options={influentPlotOptions} history={influentPlotHistory} />
      <LiveSensorPlot title="DO concentrations · live sensor trends" groupTitle="DO concentrations"
        options={doPlotOptions} history={history} className="live-do-card" />
      <SumoOutputDashboard showInfluent={false} showDo={false} influent={influentPlotOptions} result={liveRun?.result} runId={liveRun?.id||''}/>
    </section>
  </>;
}
