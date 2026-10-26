import { t, useLanguage } from '../i18n';
import { mergeStoredSimulation } from '../utils/mergeStoredSimulation';
import { useSensorComparisons } from '../hooks/useSensorComparisons';
import { realtimePollutantOptions } from './sumoOutputs';
import { LiveProgressDiagnostics, type LiveDiagnostics } from './LiveProgressDiagnostics';
import { useLiveSetting } from '../hooks/useLiveSetting';
import { defaultControlMapping, controlSensorOptions } from '../config/additionalControls';
import { defaultDoMapping, doSensorOptions } from '../config/doSensors';
import { useEffect, useRef, useState } from 'react';
import { LiveSensorPlot } from './LiveSensorPlot';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type Option = {name:string;label:string;unit:string};
type Reading = {column:string;node_id:string;value:number;timestamp:string};
type Sample = Reading & { receivedAt: number };
type UploadedModel = {id:string;name:string;state_name:string};
type Checkpoint = {sensor_boundary_at?:string;boundary_source?:string;error?:string;model_name?:string;saved_at?:string;simulated_h?:number;interval_minutes?:number;mapping?:Record<string,string>};
type HistoryProgress = {start:string;end:string|null;completed:number;total:number;database:string;follow?:boolean;caught_up?:boolean};
type LiveRun = {diagnostics?:LiveDiagnostics;sumo_commands?:string[];last_sumo_message?:string;mode?:'history'|'live';history?:HistoryProgress|null;mapping?:Record<string,string>;interval_minutes?:number;checkpoint?:Checkpoint|null;id?:string;model_id?:string;model_name?:string;status:string;phase?:string;error?:string;simulated_h?:number;samples?:number;result?:{sensor_timestamps?:(string|null)[];time_h:number[];variables:Record<string,number[]>}};
type Run = {id:string;status:'running'|'completed'|'failed';error?:string;progress_pct?:number;phase?:string;result?:{sensor_timestamps?:(string|null)[];time_h:number[];variables:Record<string,number[]>}};
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
function localDateInput(value:string) {
  const date=new Date(value);
  return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
}
async function json(url:string,init?:RequestInit) {
  const response=await fetch(url,init);
  const body=await response.json().catch(()=>null);
  if(!response.ok) throw new Error(body?.detail || `Request failed (${response.status})`);
  return body;
}
export function RealTimeSumo(){
  useLanguage();
  const [mapping,setMapping]=useLiveSetting<Record<string,string>>('mapping',{...defaultMapping,...defaultDoMapping,...defaultControlMapping});
  const [selectedColumn,setSelectedColumn]=useLiveSetting('selectedColumn',defaultColumn);
  const [nodeDraft,setNodeDraft]=useLiveSetting('nodeDraft',defaultNode);
  const [selectedDo,setSelectedDo]=useLiveSetting('selectedDo',doSensorOptions[0].name);
  const [doDraft,setDoDraft]=useLiveSetting('doDraft',defaultDoMapping[doSensorOptions[0].name]);
  const [selectedControl,setSelectedControl]=useLiveSetting('selectedControl',controlSensorOptions[0].name);
  const [controlDraft,setControlDraft]=useLiveSetting('controlDraft',defaultControlMapping[controlSensorOptions[0].name]);
  const [readings,setReadings]=useState<Reading[]>([]);
  const [history,setHistory]=useLiveSetting<Sample[]>('sensorHistory',[]);
  const [connected,setConnected]=useLiveSetting('connected',false);
  const [sensorError,setSensorError]=useState('');
  const pollingRef=useRef(false);
  const mappingRef=useRef(mapping);
  mappingRef.current=mapping;
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [limitMinutes,setLimitMinutes]=useLiveSetting('limitMinutes','1');
  const limitInterval=limitMinutes.trim()===''?1:Number(limitMinutes);
  const [savedSimulationMode,setSimulationMode]=useLiveSetting('simulationMode','resume');
  const simulationMode=savedSimulationMode==='history_then_live'?'history_then_live':'resume';
  const [historyStart,setHistoryStart]=useLiveSetting('historyStart','');
  const historyValid=!!historyStart&&Number.isFinite(Date.parse(historyStart))&&Date.parse(historyStart)<=Date.now();
  const [modelSource,setModelSource]=useLiveSetting('modelSource','builtin');
  const [stateMode,setStateMode]=useLiveSetting('stateMode','upload');
  const [stateFilename,setStateFilename]=useLiveSetting('stateFilename','');
  const [stateFile,setStateFile]=useState<File|null>(null);
  const [steadyTolerance,setSteadyTolerance]=useLiveSetting('steadyTolerance','0.000001');
  const [modelFile,setModelFile]=useState<File|null>(null);
  const [preparingModel,setPreparingModel]=useLiveSetting<UploadedModel|null>('preparingModel',null);
  const [uploadedModel,setUploadedModel]=useLiveSetting<UploadedModel|null>('uploadedModel',null);
  const [modelUploading,setModelUploading]=useState(false);
  const [modelError,setModelError]=useState('');
  const [modelVerified,setModelVerified]=useState(false);
  const modelReady=(!!uploadedModel&&modelVerified)||(modelSource==='builtin'&&stateMode==='upload'&&!stateFile&&!stateFilename);

  const [run,setRun]=useState<Run|null>(null);
  const [liveRun,setLiveRun]=useState<LiveRun|null>(null);
  const [checkpoint,setCheckpoint]=useState<Checkpoint|null>(null);
  const [downloading,setDownloading]=useState(false);
  const [statusReady,setStatusReady]=useState(false);
  const restoredRun=useRef('');
  // Uploaded model IDs survive a page reload, but the backend registry may restart.
  useEffect(()=>{
    setModelVerified(false);
    if(!uploadedModel)return;
    let active=true;
    json('/api/sumo/live/models/'+uploadedModel.id).then(model=>{
      if(active&&model.status==='ready')setModelVerified(true);
      if(active&&model.status!=='ready'){setUploadedModel(null);setModelError('Prepare the model again before starting a new run.');}
    }).catch(()=>{if(active)setModelError('Could not verify the prepared model. Reconnect or prepare it again.');});
    return()=>{active=false;};
  },[uploadedModel?.id]);
  useEffect(()=>{
    if(run?.status!=='running')return;
    let active=true;
    const timer=setInterval(()=>{json(`/api/sumo/runs/${run.id}`).then(next=>{if(active)setRun(next);}).catch(e=>{if(active)setError(String(e));});},2000);
    return ()=>{active=false;clearInterval(timer);};
  },[run?.id,run?.status]);
  useEffect(()=>{
    let active=true;
    let polling=false;
    const poll=async()=>{
      if(polling)return;
      polling=true;
      try{
        const next:LiveRun=await json('/api/sumo/live/status');
        if(active){
          setLiveRun(next.status==='idle'?null:next);setCheckpoint(next.checkpoint||null);
          setStatusReady(true);
          if(next.id && restoredRun.current!==next.id){
            restoredRun.current=next.id;
            if(next.mapping){
              setMapping(next.mapping);
              setNodeDraft(next.mapping[selectedColumn]||'');
              setDoDraft(next.mapping[selectedDo]||'');
              setControlDraft(next.mapping[selectedControl]||'');
            }
            if(next.interval_minutes)setLimitMinutes(String(next.interval_minutes));
            setSimulationMode(next.status==='interrupted'||next.model_id==='checkpoint'?'resume':next.history?'history_then_live':'resume');
            if(next.history)setHistoryStart(localDateInput(next.history.start));
          }
        }
      }catch(e){if(active)setError(String(e));}
      finally{polling=false;}
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
        setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt:Number.isFinite(Date.parse(r.timestamp))?Date.parse(r.timestamp):receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-28800));
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
    setConnected(false);setBusy(true);setError('');setSensorError('');setRun(null);
    try {
      const selected=Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()));
      const result=await json('/api/kepserver/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping:selected})});
      setReadings(result.readings);
      const receivedAt=Date.now();
      setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt:Number.isFinite(Date.parse(r.timestamp))?Date.parse(r.timestamp):receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-28800));
      setConnected(true);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function uploadModel(){
    if(modelSource==='upload'&&!modelFile)return;
    setModelUploading(true);setModelError('');setUploadedModel(null);
    try{
      if(modelFile&&(!modelFile.name.toLowerCase().endsWith('.sumo')||modelFile.size>50*1024*1024))
        throw new Error('Choose a .sumo project no larger than 50 MB.');
      const form=new FormData();
      if(modelSource==='upload'&&modelFile)form.append('project',modelFile);
      form.append('state_mode',stateMode);
      if(stateMode==='upload'){
        if(!stateFile||!stateFile.name.toLowerCase().endsWith('.xml')||stateFile.size>20*1024*1024)
          throw new Error('Choose a steady-state XML no larger than 20 MB.');
        form.append('initial_state',stateFile);
      }else{
        if(!connected)throw new Error('Connect sensor data first.');
        if(!Number.isFinite(Number(steadyTolerance))||Number(steadyTolerance)<=0)
          throw new Error('Convergence tolerance must be positive.');
        form.append('tolerance',steadyTolerance);
        form.append('mapping',JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()))));
      }
      const model=await json('/api/sumo/live/models',{method:'POST',body:form});
      if(model.status==='ready')setUploadedModel(model);
      else setPreparingModel(model);
    }catch(e){setModelError(String(e));}finally{setModelUploading(false);}
  }
  useEffect(()=>{
    if(!preparingModel)return;
    let cancelled=false;
    let timer:ReturnType<typeof setTimeout>;
    async function pollModel(){
      try{
        const model=await json('/api/sumo/live/models/'+preparingModel!.id);
        if(cancelled)return;
        setModelError('');
        if(model.status==='ready'){setUploadedModel(model);setPreparingModel(null);return;}
        if(model.status==='failed'){setModelError(model.error||'Initial-state generation failed.');setPreparingModel(null);return;}
      }catch(e){
        if(cancelled)return;
        setModelError(String(e));
      }
      timer=setTimeout(()=>void pollModel(),3000);
    }
    void pollModel();
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[preparingModel]);

  async function start(){
    if(!statusReady||!modelReady)return;
    if(simulationMode==='history_then_live'&&!historyValid){setError('Select a historical start time in the past.');return;}
    if((liveRun?.samples||0)>0 && !window.confirm(t('Start a new simulation? This replaces the displayed run and, after its first interval, the latest checkpoint. Download the current results first if you need to keep them.')))return;
    setBusy(true);setError('');
    try{
      const selected=Object.fromEntries(Object.entries(mapping).filter(([,node])=>node.trim()));
      const result:LiveRun=await json('/api/sumo/live/start',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mapping:selected,interval_minutes:limitInterval,model_id:uploadedModel?.id||'builtin',mode:simulationMode,
          ...(simulationMode==='history_then_live'?{history_start:new Date(historyStart).toISOString()}: {})})});
      setLiveRun(result);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function resume(){
    if(!statusReady||!checkpoint||checkpoint.error)return;
    setBusy(true);setError('');
    try{
      const result:LiveRun=await json('/api/sumo/live/resume',{method:'POST'});
      setLiveRun(result);
      if(result.checkpoint?.mapping)setMapping(result.checkpoint.mapping);
      if(result.checkpoint?.interval_minutes)setLimitMinutes(String(result.checkpoint.interval_minutes));
      setConnected(true);
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  async function stop(){
    if(!window.confirm(t('Stop the shared live simulation for all viewers?')))return;
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
  const resumeMode=simulationMode==='resume';
  const checkpointReady=!!checkpoint&&!checkpoint.error;
  const running=!statusReady||busy||liveActive||modelUploading||!!preparingModel;
  const sensorGroup=(key:string)=>defaultDoMapping[key]?'do':defaultControlMapping[key]?'control':'influent';
  const comparisons = useSensorComparisons(liveRun?.id, !!liveRun?.result?.time_h.length, liveRun?.interval_minutes);
  const visualisationResult = liveRun?.result ? {...liveRun.result, comparison_series: comparisons?.series, simulation_series: mergeStoredSimulation(comparisons?.stored_series, liveRun.result)} : undefined;
  const chartMapping=liveRun?.mapping??mapping;
  const influentPlotOptions=Object.keys(chartMapping).filter(key=>Boolean(defaultMapping[key]||defaultControlMapping[key])).map(key=>({
    key,label:[...options,...controlSensorOptions].find(o=>o.name===key)?.label||key.split('__').pop()||key,
    unit:[...options,...controlSensorOptions].find(o=>o.name===key)?.unit||''
  }));
  const doChartMapping=liveRun?.mapping??mapping;
  const doPlotOptions=doSensorOptions.filter(o=>/^Sumo__Plant__CSTR[34]_/.test(o.name)&&doChartMapping[o.name]).map(o=>({key:o.name,label:o.label,unit:o.unit}));
  return <>
    <section className="page-head"><div><h1>{t("SUMO Real-time Simulation")}</h1><p>{t("Cixi Eastern WWTP · KEPServer OPC UA · Manual simulation")}</p></div></section>
    <section className="config-card">
      <div className="section-title"><div><h2>{t("Simulation settings")}</h2></div></div>
      <section className="sensor-setup" aria-labelledby="sensor-step-title">
        <div className="sensor-heading"><div><h3 id="sensor-step-title">{t("Step1: Connect sensors through KEPServer")}</h3><p>{t("Review the prefilled influent, DO and additional control tags, then connect to read sensor data.")}</p></div><span className={'sensor-status '+(connected?'is-connected':'')} role="status">{t(connected?'Connected · every 5 s':'Disconnected')}</span></div>
        <div className="sensor-editor-grid sensor-input-grid">
          {[{title:'Influent variable',items:options,selected:selectedColumn,draft:nodeDraft,setSelected:setSelectedColumn,setDraft:setNodeDraft,kind:'influent'},
            {title:'DO sensors',items:doSensorOptions,selected:selectedDo,draft:doDraft,setSelected:setSelectedDo,setDraft:setDoDraft,kind:'do'},
            {title:'Additional control',items:controlSensorOptions,selected:selectedControl,draft:controlDraft,setSelected:setSelectedControl,setDraft:setControlDraft,kind:'control'}].map(group=><article className="sensor-editor" key={group.title}>
            <div className="sensor-editor-title"><h4>{t(group.title)}</h4><span>{Object.keys(mapping).filter(key=>sensorGroup(key)===group.kind).length}{t(" mapped")}</span></div>
            <label className="sensor-field"><span>{t(group.title)}</span><select value={group.selected} onChange={e=>{group.setSelected(e.target.value);group.setDraft(mapping[e.target.value]||'');}}>
              {group.items.map(option=><option key={option.name} value={option.name}>{t(option.label)} ({t(option.unit)})</option>)}
            </select></label>
            <label className="sensor-field"><span>{t("KEPServer OPC UA Node ID")}</span><input type="text" value={group.draft} disabled={running} placeholder={t("ns=2;s=...")} onChange={e=>group.setDraft(e.target.value)}/></label>
            <button className="secondary" disabled={running||!group.selected||!group.draft.trim()} onClick={()=>changeMapping(group.selected,group.draft.trim())}>{t("Add / Update mapping")}</button>
            <details className="sensor-mapping-list" onMouseLeave={event => { event.currentTarget.open = false; }}><summary>{t("Review mappings")}</summary>
              {Object.entries(mapping).filter(([key])=>sensorGroup(key)===group.kind).map(([column,node])=><div className="sensor-mapping-row" key={column}>
                <div><strong>{t([...options,...doSensorOptions,...controlSensorOptions].find(o=>o.name===column)?.label||column.split('__').pop())}</strong><code>{node}</code></div>
                <button className="secondary" aria-label={t('Remove '+column)} disabled={running} onClick={()=>{
                  setConnected(false);setHistory([]);setReadings([]);setSensorError('');
                  setMapping(old=>{const next={...old};delete next[column];return next;});
                  if(group.selected===column)group.setDraft('');
                }}>{t("Remove")}</button>
              </div>)}
            </details>
          </article>)}
        </div>
        <div className="sensor-actions"><button className="primary" disabled={running||!Object.values(mapping).some(Boolean)} onClick={refresh}>{t(busy?'Connecting...':'Connect')}</button><button className="secondary" disabled={!connected||busy} onClick={()=>setConnected(false)}>{t("Disconnect")}</button><span>{t("Check sensor connectivity and current readings. Plots update with simulation results.")}</span></div>
        {sensorError&&<div className="alert" role="alert">{t("Sensor update failed: ")}{t(sensorError)}</div>}
      </section>
      <section className="sensor-setup simulation-setup" aria-labelledby="simulation-step-title">
        <div className="sensor-heading"><div><h3 id="simulation-step-title">{t("Step2: Set up real time simulation")}</h3><p>{t("Choose a simulation mode, then configure a new run or resume the latest saved simulation.")}</p></div><span className={'sensor-status '+((resumeMode?checkpointReady:modelReady)?'is-connected':'')} role="status">{t(liveActive?'Simulation active':preparingModel?'Preparing state':resumeMode?(checkpointReady?'Checkpoint ready':'No usable checkpoint'):modelReady?'Model ready':'Setup required')}</span></div>
          <label className="sensor-field"><span>{t("Simulation mode")}</span><select value={simulationMode} disabled={running} onChange={e=>setSimulationMode(e.target.value)}>
            <option value="resume">{t("Resume a saved simulation")}</option>
            <option value="history_then_live">{t("Historical data → Live")}</option>
          </select></label>
        <div className="sensor-editor-grid sensor-input-grid" style={resumeMode?{gridTemplateColumns:'1fr'}:undefined}>
        {!resumeMode&&<>
        <article className="sensor-editor" aria-label={t("SUMO model selection")}>
          <div className="sensor-editor-title"><h4>{t("SUMO model")}</h4><span>{t("01 · Model")}</span></div>
        <label className="sensor-field"><span>{t("SUMO model")}</span>
          <select value={modelSource} disabled={running} onChange={e=>{setModelSource(e.target.value);setUploadedModel(null);setModelError('');}}>
            <option value="builtin">{t("Built-in · Cixi Eastern WWTP_20260920")}</option>
            <option value="upload">{t("Upload a SUMO model")}</option>
          </select>
        </label>
        {modelSource==='upload'&&<label className="sensor-field"><span>{t("SUMO project (.sumo, max 50 MB)")}</span><input type="file" accept=".sumo" disabled={running} onChange={e=>{setModelFile(e.target.files?.[0]||null);setUploadedModel(null);setModelError('');}}/></label>}
          <p className="calibration-note">{t("Use the built-in plant model or upload a compiled SUMO project that supports your sensor variables.")}</p>
          <p className="calibration-note simulation-card-footnote">{t("Prepared models are available until the backend restarts.")}</p>
        </article>
        <article className="sensor-editor">
          <div className="sensor-editor-title"><h4>{t("Initial state")}</h4><span>{t("02 · Preparation")}</span></div>
        <label className="sensor-field"><span>{t("Steady state")}</span>
          <select value={stateMode} disabled={running} onChange={e=>{setStateMode(e.target.value);setUploadedModel(null);setModelError('');}}>
            <option value="upload">{t("Upload steady-state file")}</option>
            <option value="calculate">{t("Calculate from latest sensor data")}</option>
          </select>
        </label>
        {stateMode==='upload'?<>
          <label className="sensor-field"><span>{t("Steady-state file (.xml, max 20 MB)")}</span><input type="file" accept=".xml" disabled={running} onChange={e=>{setStateFile(e.target.files?.[0]||null);setStateFilename(e.target.files?.[0]?.name||'');setUploadedModel(null);setModelError('');}}/></label>
          {stateFilename&&!stateFile&&!uploadedModel&&<p role="status">{t("Reselect ")}{t(stateFilename)}{t(" to prepare this state, or clear the selection to use the built-in state. ")}<button className="secondary" disabled={running} onClick={()=>setStateFilename('')}>{t("Clear file selection")}</button></p>}
          <p className="calibration-note">{t(modelSource==='builtin'&&!stateFile&&!stateFilename?'Using the built-in sumo_steady_state.xml. Select a file to replace it.':'Choose a steady-state XML matching the selected model.')}</p>
        </>:<>
          <p className="calibration-note">{t("Reads a fresh sensor snapshot when calculation starts, applies scaling, and holds those inputs constant until convergence. Connect sensor data first.")}</p>
          <label className="sensor-field"><span>{t("Convergence tolerance (MaxAbsDer)")}</span><input type="number" min="0" step="any" value={steadyTolerance} disabled={running} onChange={e=>{setSteadyTolerance(e.target.value);setUploadedModel(null);}}/></label>
          <p className="calibration-note">{t("Requires MaxAbsDer at or below the tolerance for three consecutive samples, or at the solver's natural finish. A 3.5-hour timeout reports failure without accepting an unconverged state.")}</p>
        </>}
        <div className="sensor-actions simulation-prepare-action"><button className="secondary"
          disabled={running||(modelSource==='upload'&&!modelFile)||(stateMode==='upload'?!stateFile:(!connected||!Number.isFinite(Number(steadyTolerance))||Number(steadyTolerance)<=0))}
          onClick={()=>void uploadModel()}>{t(modelUploading?'Preparing model...':stateMode==='upload'?'Use uploaded steady state':'Calculate steady state')}</button></div>
        {preparingModel&&<p role="status">{t("Calculating steady state for ")}{t(preparingModel.name)}{t(". Run SUMO will be available after convergence and saving.")}</p>}
        {uploadedModel&&<p role="status" className="measurement-ready">{t("Ready: ")}{t(uploadedModel.name)} · {t(uploadedModel.state_name)}</p>}

        {modelError&&<div className="alert" role="alert">{t(modelError)}</div>}
        </article>
        </>}
        <article className="sensor-editor">
          <div className="sensor-editor-title"><h4>{t(resumeMode?'Saved simulation':'Simulation timing')}</h4><span>{t(resumeMode?'Latest checkpoint':'03 · Timing')}</span></div>
          {resumeMode?<>
            {!checkpoint?<p role="status">{t("No saved simulation is available yet. Run a simulation to create a checkpoint.")}</p>
              :checkpoint.error?<p className="alert" role="alert">{t(checkpoint.error)}</p>:<>
                <div className="resume-layout">
                  <div className="resume-summary">
                    <span className="resume-eyebrow">{t("Saved model")}</span>
                    <h4 className="resume-model-name">{t(checkpoint.model_name)}</h4>
                    <dl className="resume-metadata">
                      <div><dt>{t("Simulation time")}</dt><dd>{t(checkpoint.simulated_h?.toFixed(3)??'—')} <small>{t("h")}</small></dd></div>
                      <div><dt>{t("LimitTime")}</dt><dd>{t(checkpoint.interval_minutes??'—')} <small>{t("min")}</small></dd></div>
                      <div><dt>{t("Last saved · local time")}</dt><dd>{t(checkpoint.saved_at?new Date(checkpoint.saved_at).toLocaleString():'—')}</dd></div>
                      <div><dt>{t("Resume database from · local time")}</dt><dd>{t(checkpoint.sensor_boundary_at?new Date(checkpoint.sensor_boundary_at).toLocaleString():'—')}</dd></div>
                    </dl>
                  </div>
                  <aside className="resume-details" aria-label={t("Resume behavior")}>
                    <h4>{t("Continue from your checkpoint")}</h4>
                    <p>{t("Restores the saved model, state, sensor mappings and interval. No model upload or initial-state preparation is needed.")}</p>
                    <ul><li><strong>{t("Database:")}</strong>{t(" Replays collected sensor data from the saved boundary using the saved mappings and LimitTime.")}</li><li><strong>{t("Mode:")}</strong>{t(" Preserves saved results, catches up, then follows new collection automatically. Missing inputs keep their previous values.")}</li></ul>
                  </aside>
                </div>
                {checkpoint.boundary_source==='legacy_save_time_estimate'&&<p className="calibration-note resume-notice">{t("This older checkpoint has no sensor timestamp; its save time is used as the approximate database start.")}</p>}
              </>}
          </>:<>
          {simulationMode==='history_then_live'&&<>
            <label className="sensor-field"><span>{t("History start (local time)")}</span><input type="datetime-local" value={historyStart} disabled={running} onChange={e=>setHistoryStart(e.target.value)}/></label>
            <ul className="calibration-note">
              <li><strong>{t("Database:")}</strong>{t(" sumo_web_database for historical inputs and simulation results.")}</li>
              <li><strong>{t("Mode:")}</strong>{t(" Runs history in LimitTime intervals as fast as possible, then checks for new data at the same interval (default: 1 minute). Missing inputs keep their previous values.")}</li>
            </ul>
            {!historyValid&&<p role="status">{t("Select a historical start time in the past.")}</p>}
          </>}
          <label className="sensor-field"><span>{t("Input update interval / Limit time (minutes, default 1)")}</span><input type="number" min="1" max="60" step="1" placeholder={t("1")} value={limitMinutes} disabled={running} onChange={e=>setLimitMinutes(e.target.value)}/></label>
          <label className="sensor-field"><span>{t("Operation")}</span><input value={t("Continuous · until Stop SUMO")} readOnly aria-label={t("Simulation operation")}/></label>
          <p className="calibration-note">{t("Sensor inputs refresh at each interval. The model continues from the previous interval's state until you stop it.")}</p>
          </>}
        </article>
        </div>
        {liveActive&&liveRun?.model_name&&<p className="simulation-model-status" role="status">{t("Running model: ")}{t(liveRun.model_name)}</p>}
      <p className="calibration-note">{t("Refreshing or closing this page does not stop the server simulation. Saved output history is restored after a backend restart; choose Resume a saved simulation to continue. Sensor preview history and draft settings are retained in this browser. File selections must be reselected if not yet uploaded.")}</p>
      {!statusReady&&<p role="status">{t("Reconnecting to the live simulation…")}</p>}
      <div className="sensor-actions simulation-run-actions"><button className="primary" disabled={running||(resumeMode?!checkpointReady:(!modelReady||!historyValid||!(Number.isInteger(limitInterval)&&limitInterval>=1&&limitInterval<=60)))} onClick={()=>void (resumeMode?resume():start())}>{t(resumeMode?'Resume SUMO':'Run SUMO')}</button> <button className="secondary" disabled={busy||!['starting','running'].includes(liveRun?.status||'')} onClick={()=>void stop()}>{t("Stop SUMO")}</button><span>{t("Each completed interval saves the latest checkpoint. Stop finishes and saves the current interval.")}</span></div>
      {liveRun&&<div className="sumo-progress"><p role="status">{t(liveRun.status)} · {t(liveRun.mode==='history'?'Historical replay':liveRun.mode==='live'?'Live operation':'')} · {t(liveRun.phase||'')} · {t((liveRun.simulated_h||0).toFixed(2))}{t(" simulated hours · ")}{t(liveRun.samples||0)}{t(" output samples")}</p>{liveRun.history&&(liveRun.history.follow?<p role="status">{t(liveRun.history.caught_up?'Caught up · following sensor collection':'Catching up with collected data')} · {t(liveRun.history.completed)}{t(" completed intervals")}{t(liveRun.history.total>liveRun.history.completed?` · ${liveRun.history.total-liveRun.history.completed} loaded intervals remaining`:'')}</p>:<><progress aria-label={t("History replay progress")} max={liveRun.history.total} value={liveRun.history.completed}/><p>{t("Historical intervals: ")}{t(liveRun.history.completed)} / {t(liveRun.history.total)}</p></>)}<LiveProgressDiagnostics value={liveRun.diagnostics}/>{liveRun.last_sumo_message&&<p>{t("SUMO: ")}{t(liveRun.last_sumo_message)}</p>}{liveRun.error&&<div className="alert">{t(liveRun.error)}</div>}{liveRun.error&&!!liveRun.sumo_commands?.length&&<details><summary>{t("SUMO command diagnostics")}</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{liveRun.sumo_commands.join("\n")}</pre></details>}</div>}
      {run&&<div className="sumo-progress"><p role="status">{t(run.phase||run.status)} · {t(Math.floor(run.progress_pct||0))}%</p><progress max="100" value={run.progress_pct||0}/></div>}
      {(error||run?.error)&&<div className="alert" role="alert">{t(error||run?.error)}</div>}
      </section>
    </section>
    <section className="config-card"><div className="section-title"><div><h2>{t("Output variables visualisation")}</h2></div><button className="secondary" disabled={!liveRun?.result?.time_h?.length||downloading} onClick={async()=>{setDownloading(true);try{const response=await fetch('/api/sumo/live/download');if(!response.ok)throw Error('Download failed');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='sumo_live_results.csv';link.click();URL.revokeObjectURL(url);}catch(e){setError(String(e));}finally{setDownloading(false);}}}>{t("Download results CSV")}</button></div>
      <LiveSensorPlot title={t("Influent variables · simulation inputs")} groupTitle="Influent variables"
        options={influentPlotOptions} history={history} source="simulation"
        simulationResult={liveRun?.result} runId={liveRun?.id||'simulation-inputs'} />
      <LiveSensorPlot title={t("DO concentrations · simulation inputs")} groupTitle="DO concentrations"
        options={doPlotOptions} history={history} className="live-do-card" source="simulation"
        simulationResult={liveRun?.result} runId={liveRun?.id||'simulation-inputs'} />
      {comparisons?.error&&<p role="status">{t(comparisons.error)}</p>}
      {comparisons?.aggregation_seconds&&<p className="calibration-note">{t("Dotted sensor curves from ")}{t(comparisons.database || 'sumo_web_database')}{t(": recorded nitrate means over ")}{t(comparisons.aggregation_seconds)}{t(" seconds, compared with simulated SNOx. Missing measurements remain gaps.")}</p>}
      <SumoOutputDashboard localTime pollutants={realtimePollutantOptions} showInfluent={false} showDo={false} influent={influentPlotOptions} result={visualisationResult} runId={liveRun?.id||''}/>
    </section>
  </>;
}
