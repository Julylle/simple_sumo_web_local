import { t, useLanguage } from '../i18n';
import { mergeStoredSimulation } from '../utils/mergeStoredSimulation';
import { useSensorComparisons } from '../hooks/useSensorComparisons';
import { realtimePollutantOptions } from './sumoOutputs';
import { LiveProgressDiagnostics, type LiveDiagnostics } from './LiveProgressDiagnostics';
import { useLiveSetting } from '../hooks/useLiveSetting';
import { defaultControlMapping, controlSensorOptions } from '../config/additionalControls';
import { defaultDoMapping, doSensorOptions } from '../config/doSensors';
import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { LiveSensorPlot } from './LiveSensorPlot';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type Option = {name:string;label:string;unit:string};
type Reading = {column:string;node_id:string;value:number;timestamp:string;source?:string;age_seconds?:number;opc_error?:string};
type Sample = Reading & { receivedAt: number };
type UploadedModel = {id:string;name:string;state_name:string};
type Checkpoint = {sensor_boundary_at?:string;boundary_source?:string;error?:string;model_name?:string;saved_at?:string;simulated_h?:number;interval_minutes?:number;mapping?:Record<string,string>};
type HistoryProgress = {start:string;end:string|null;completed:number;total:number;database:string;follow?:boolean;caught_up?:boolean};
type InputProvenance = {start_ms:number;end_ms:number;interval_start:string|null;interval_end:string|null;inputs:{column:string;node_id:string;model_value:number;source:string;original_source?:string;collected_from?:string;collected_to?:string;sample_count?:number}[]};
function localCollectionTime(value?:string|null){return value?new Date(value).toLocaleString():t('Unknown');}
function inputSource(source:string){return t(({opcua:'OPC UA real time',database_interval:'Database interval average',held_previous:'Previous available input',database_current:'Database at requested time',database_previous:'Previous available database value'} as Record<string,string>)[source]||'Unknown');}
type LiveRun = {input_provenance?:InputProvenance;diagnostics?:LiveDiagnostics;sumo_commands?:string[];last_sumo_message?:string;mode?:'history'|'live';history?:HistoryProgress|null;mapping?:Record<string,string>;interval_minutes?:number;checkpoint?:Checkpoint|null;id?:string;model_id?:string;model_name?:string;status:string;phase?:string;error?:string;simulated_h?:number;samples?:number;result?:{sensor_timestamps?:(string|null)[];time_h:number[];variables:Record<string,number[]>}};
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
  "Sumo__Plant__Influent__param__TP": "ns=2;s=MySQL.Dev1.inlet_tp.inlet_tp__1_",
  "Sumo__Plant__Influent__param__COD_analyzer": "ns=2;s=GEeth.PLC128.JS_COD",
  "Sumo__Plant__Primary1__param__TSS_sensor": "ns=2;s=GEeth.PLC132.PE_TSS_sensor",
  "Sumo__Plant__Influent__param__frVSS_TSS": "ns=2;s=MySQL.Dev6.Influent_VSS_TSS_Ratio",
  "Sumo__Plant__Primary1__param__TSS_lab": "ns=2;s=MySQL.Dev2.primary_eff_tss.primary_eff_tss__1_",
};
// Dropdown selection only controls the editor, never the subscribed input set.
const allDefaultMapping = {...defaultMapping,...defaultDoMapping,...defaultControlMapping};
function selectedMappings(saved: Record<string,string>): Record<string,string> {
  return Object.fromEntries(Object.entries(saved).filter(([name,node]) =>
    name in allDefaultMapping && typeof node === 'string' && node.trim()
  ).map(([name,node]) => [name,node.trim()]));
}
// These configured inputs must remain selectable even if the SUMO API is offline.
const influentUnits: Record<string,string> = {
  COD_analyzer: 'mg COD/L', TSS_lab: 'mg TSS/L', frVSS_TSS: '-',
  Q: 'm3/d', pH: 'pH', T: 'deg C', Ammonia_sensor_Horiba: 'mg/L',
  COD_lab: 'mg/L', TKN_lab: 'mg/L', Ammonia_lab: 'mg/L', TSS_sensor: 'mg/L',
  Ammonia_analyzer: 'mg/L', TCOD: 'mg COD/L', TKN: 'mg N/L', TP: 'mg P/L',
};
const options: Option[] = Object.keys(defaultMapping).map(name => {
  const label = name.split('__').pop()!;
  return {name, label: name.includes('__Primary1__') ? 'Primary1 · ' + label : label, unit: influentUnits[label]};
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
  const [storedMapping,setMapping]=useLiveSetting<Record<string,string>>('mapping',allDefaultMapping);
  const mapping=selectedMappings(storedMapping);
  const [influentDefaultsVersion,setInfluentDefaultsVersion]=useLiveSetting('influentDefaultsVersion',0);
  const [controlDefaultsVersion,setControlDefaultsVersion]=useLiveSetting('controlDefaultsVersion',0);
  const [selectedColumn,setSelectedColumn]=useLiveSetting('selectedColumn',defaultColumn);
  const [nodeDraft,setNodeDraft]=useLiveSetting('nodeDraft',defaultNode);
  const [selectedDo,setSelectedDo]=useLiveSetting('selectedDo',doSensorOptions[0].name);
  const [doDraft,setDoDraft]=useLiveSetting('doDraft',defaultDoMapping[doSensorOptions[0].name]);
  const [selectedControl,setSelectedControl]=useLiveSetting('selectedControl',controlSensorOptions[0].name);
  const [controlDraft,setControlDraft]=useLiveSetting('controlDraft',defaultControlMapping[controlSensorOptions[0].name]);
  const [readings,setReadings]=useLiveSetting<Reading[]>('lastSensorReadings',[]);
  const [history,setHistory]=useLiveSetting<Sample[]>('sensorHistory',[]);
  const [connected,setConnected]=useLiveSetting('sensorConnectionEnabled',false);
  const [connecting,setConnecting]=useState(false);
  const [sensorError,setSensorError]=useLiveSetting('sensorConnectionError','');
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
    if(!connected||!statusReady)return;
    let cancelled=false;
    const poll=async()=>{
      if(pollingRef.current)return;
      pollingRef.current=true;
      try{
        const selected=selectedMappings(mappingRef.current);
        const result=await json('/api/kepserver/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping:selected})});
        if(cancelled || JSON.stringify(selected)!==JSON.stringify(selectedMappings(mappingRef.current)))return;
        if(result.unavailable?.length)throw new Error(result.unavailable.map((r:{column:string;reason:string;database_error:string})=>`${r.column}: ${r.reason}; ${r.database_error}`).join('\n'));
        const receivedAt=Date.now();
        setReadings(result.readings);
        setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt:Number.isFinite(Date.parse(r.timestamp))?Date.parse(r.timestamp):receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-28800));
        setSensorError('');
      }catch(e){if(!cancelled)setSensorError(String(e));}
      finally{pollingRef.current=false;}
    };
    // Restore the previous display, then refresh it without forcing Disconnected.
    void poll();
    const timer=setInterval(()=>{void poll();},5000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[connected,statusReady]);
  function changeMapping(column:string,node:string){
    setConnected(false);setHistory([]);setSensorError('');
    setMapping(old=>({...old,[column]:node}));setReadings([]);setRun(null);
  }
  async function refresh(){
    setConnecting(true);setConnected(false);setBusy(true);setError('');setSensorError('');setRun(null);
    try {
      const selected=selectedMappings(mapping);
      setMapping(selected);
      const result=await json('/api/kepserver/snapshot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mapping:selected})});
      if(JSON.stringify(selected)!==JSON.stringify(selectedMappings(mappingRef.current)))
        throw new Error('Sensor mappings changed while connecting. Please reconnect.');
      if(result.unavailable?.length)throw new Error(result.unavailable.map((r:{column:string;reason:string;database_error:string})=>`${r.column}: ${r.reason}; ${r.database_error}`).join('\n'));
      if(!Array.isArray(result.readings) || result.readings.length!==Object.keys(selected).length ||
          !Object.entries(selected).every(([column,node])=>result.readings.some(
            (r:Reading)=>r.column===column && r.node_id===node && Number.isFinite(r.value))))
        throw new Error('Incomplete sensor snapshot; reconnect before calculating.');
      // Commit connection feedback before processing plot history.
      flushSync(()=>{setConnected(true);setConnecting(false);});
      setReadings(result.readings);
      const receivedAt=Date.now();
      setHistory(old=>[...old,...(result.readings as Reading[]).map(r=>({...r,receivedAt:Number.isFinite(Date.parse(r.timestamp))?Date.parse(r.timestamp):receivedAt}))].filter(s=>s.receivedAt>=receivedAt-3600000).slice(-28800));
    }catch(e){setConnected(false);setSensorError(String(e));}
    finally{setConnecting(false);setBusy(false);}
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
        form.append('mapping',JSON.stringify(selectedMappings(mapping)));
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
    if(!window.confirm(t('Start a new historical simulation? Results at matching timestamps for the same model will be updated. Other timestamps and raw sensor data are kept. The latest checkpoint is replaced after the first completed interval.')))return;
    setBusy(true);setError('');
    try{
      const selected=selectedMappings(mapping);
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
  // Fill all influent defaults once without overwriting custom tags or future removals.
  useEffect(()=>{
    if(!statusReady||liveActive||preparingModel||influentDefaultsVersion>=2)return;
    setMapping(old=>{
      const next={...old};
      for(const [name,node] of Object.entries(defaultMapping))
        if(typeof next[name]!=='string'||!next[name].trim())next[name]=node;
      return next;
    });
    const column=defaultMapping[selectedColumn]?selectedColumn:defaultColumn;
    setNodeDraft(mapping[column] || defaultMapping[column]);
    setConnected(false);
    setInfluentDefaultsVersion(2);
  },[statusReady,liveActive,preparingModel,influentDefaultsVersion]);
  // Populate existing browser drafts once; subsequent Remove actions stay removed.
  useEffect(()=>{
    if(!statusReady||liveActive||preparingModel||controlDefaultsVersion>=2)return;
    setMapping(old=>{
      const next={...old};
      for(const [name,node] of Object.entries(defaultControlMapping))
        if(typeof next[name]!=='string'||!next[name].trim())next[name]=node;
      return next;
    });
    setControlDraft(mapping[selectedControl] || defaultControlMapping[selectedControl] || '');
    setConnected(false);
    setControlDefaultsVersion(2);
  },[statusReady,liveActive,preparingModel,controlDefaultsVersion]);
  useEffect(()=>{
    if(!defaultMapping[selectedColumn]){
      setSelectedColumn(defaultColumn);
      setNodeDraft(mapping[defaultColumn] || '');
    }
  },[selectedColumn]);
  useEffect(()=>{
    if(!defaultControlMapping[selectedControl]){
      setSelectedControl(controlSensorOptions[0].name);
      setControlDraft(mapping[controlSensorOptions[0].name] || '');
    }
  },[selectedControl]);
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
      <details className="sensor-setup sensor-step-collapsible" aria-labelledby="sensor-step-title">
        <summary className="sensor-heading"><div><h3 id="sensor-step-title">{t("Step1: Connect sensors through KEPServer")}</h3><p>{t("Connect reads all configured influent, DO and additional control tags. Dropdowns only select the mapping to edit.")}</p></div><span className="mapping-indicator sensor-mapping-indicator" role="status">
          <span className={'sensor-status '+(connected&&!sensorError?'is-connected':'')}>{t('Sensor mappings')}: {Object.keys(mapping).length} / {Object.keys(allDefaultMapping).length}</span>
          {' · '}{t(connecting?'Checking readings':sensorError?'Data unavailable':connected?'Readings available':'Not checked')}
          {connected&&!sensorError&&<> · OPC UA: {readings.filter(r=>r.source==='opcua').length} · {t('Database fallback')}: {readings.filter(r=>r.source?.startsWith('database')).length}</>}
        </span><span className="sensor-step-chevron" aria-hidden="true">⌄</span></summary>
        {liveRun?.input_provenance&&<details className="sensor-mapping-list simulation-input-details">
          <summary>{t('Simulation interval input details')}</summary>
          <p>{t('Latest interval')}: {liveRun.input_provenance.start_ms/1000}–{liveRun.input_provenance.end_ms/1000} s · {t(liveRun.phase||liveRun.status)}</p>
          {liveRun.input_provenance.interval_start&&<p>{localCollectionTime(liveRun.input_provenance.interval_start)} → {localCollectionTime(liveRun.input_provenance.interval_end)}</p>}
          <p>{t('Times use this computer’s local timezone')}: {Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
          <table><thead><tr><th>{t('Sensor mapping')}</th><th>{t('Data source')}</th><th>{t('Model input value')}</th><th>{t('Collected from')}</th><th>{t('Collected to')}</th><th>{t('Samples')}</th></tr></thead>
          <tbody>{liveRun.input_provenance.inputs.map(r=><tr key={r.column}>
            <td><code>{r.column}</code><br/><small>{r.node_id}</small></td><td>{inputSource(r.source)}{r.original_source&&<> ({inputSource(r.original_source)})</>}</td>
            <td>{r.model_value}</td><td>{localCollectionTime(r.collected_from)}</td><td>{localCollectionTime(r.collected_to)}</td><td>{r.sample_count??'—'}</td>
          </tr>)}</tbody></table>
        </details>}
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
        <div className="sensor-actions"><button className="primary" disabled={running||!Object.values(mapping).some(Boolean)} onClick={refresh}>{t(connecting?'Connecting...':connected&&!sensorError?'Connected':'Connect')}</button><button className="secondary" disabled={!connected||busy} onClick={()=>setConnected(false)}>{t("Disconnect")}</button><span>{t("Check sensor connectivity and current readings. Plots update with simulation results.")}</span></div>
        {connected&&!sensorError&&readings.some(r=>r.source?.startsWith('database'))&&<details className="sensor-mapping-list">
          <summary>{t('Database fallback details')} ({readings.filter(r=>r.source?.startsWith('database')).length})</summary>
          <ul>{readings.filter(r=>r.source?.startsWith('database')).map(r=><li key={r.column}>
            <code>{r.column}</code> · {r.source==='database_current'?t('Database at requested time'):t('Previous available database value')}
            {' · '}{r.value}{' · '}{r.timestamp}{' · '}{t('Age (seconds):')}{Math.round(r.age_seconds||0)}
          </li>)}</ul>
        </details>}
        {sensorError&&<div className="alert" role="alert">{t("Sensor connection/read failed: ")}{t(sensorError)}</div>}
      </details>
      <section className={`sensor-setup simulation-setup ${resumeMode ? "" : "history-setup"}`} aria-labelledby="simulation-step-title">
        <div className="sensor-heading"><div><h3 id="simulation-step-title">{t("Step2: Set up real time simulation")}</h3><p>{t("Choose a simulation mode, then configure a new run or resume the latest saved simulation.")}</p></div><span className={'sensor-status '+((resumeMode?checkpointReady:modelReady)?'is-connected':'')} role="status">{t(liveActive?'Simulation active':preparingModel?'Preparing state':resumeMode?(checkpointReady?'Checkpoint ready':'No usable checkpoint'):modelReady?'Model ready':'Setup required')}</span></div>
          <label className="sensor-field simulation-mode-field"><span>{t("Simulation mode")}</span><select value={simulationMode} disabled={running} onChange={e=>setSimulationMode(e.target.value)}>
            <option value="resume">{t("Resume a saved simulation")}</option>
            <option value="history_then_live">{t("Historical data → Live")}</option>
          </select></label>
        <div className={`sensor-editor-grid sensor-input-grid ${resumeMode ? "" : "history-setup-grid"}`} style={resumeMode?{gridTemplateColumns:'1fr'}:undefined}>
        {!resumeMode&&<>
        <article className="sensor-editor history-model-card" aria-label={t("SUMO model selection")}>
          <div className="sensor-editor-title"><h4>{t("SUMO model")}</h4><span>{t("01 · Model")}</span></div>
        <label className="sensor-field"><span>{t("SUMO model")}</span>
          <select value={modelSource} disabled={running} onChange={e=>{setModelSource(e.target.value);setUploadedModel(null);setModelError('');}}>
            <option value="builtin">{t("Built-in · Cixi Eastern WWTP_20260920")}</option>
            <option value="upload">{t("Upload a SUMO model")}</option>
          </select>
        </label>
        {modelSource==='upload'&&<label className="sensor-field"><span>{t("SUMO project (.sumo, max 50 MB)")}</span><input className="sumo-file-input" type="file" accept=".sumo" disabled={running} onChange={e=>{setModelFile(e.target.files?.[0]||null);setUploadedModel(null);setModelError('');}}/></label>}
          <p className="calibration-note">{t("Use the built-in plant model or upload a compiled SUMO project that supports your sensor variables.")}</p>
          <p className="calibration-note simulation-card-footnote">{t("Prepared models are available until the backend restarts.")}</p>
        </article>
        <article className="sensor-editor history-state-card">
          <div className="sensor-editor-title"><h4>{t("Initial state")}</h4><span>{t("02 · Preparation")}</span></div>
        <label className="sensor-field"><span>{t("Steady state")}</span>
          <select value={stateMode} disabled={running} onChange={e=>{setStateMode(e.target.value);setUploadedModel(null);setModelError('');}}>
            <option value="upload">{t("Upload steady-state file")}</option>
            <option value="calculate">{t("Calculate from latest sensor data")}</option>
          </select>
        </label>
        {stateMode==='upload'?<>
          <label className="sensor-field"><span>{t("Steady-state file (.xml, max 20 MB)")}</span><input className="sumo-file-input" type="file" accept=".xml" disabled={running} onChange={e=>{setStateFile(e.target.files?.[0]||null);setStateFilename(e.target.files?.[0]?.name||'');setUploadedModel(null);setModelError('');}}/></label>
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
        <article className={`sensor-editor ${resumeMode ? "" : "history-timing-card"}`}>
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
            <ul className="calibration-note history-behavior">
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
    <section className="config-card"><div className="section-title"><div><h2>{t("Simulation results")}</h2></div><button className="secondary" disabled={!liveRun?.result?.time_h?.length||downloading} onClick={async()=>{setDownloading(true);try{const response=await fetch('/api/sumo/live/download');if(!response.ok)throw Error('Download failed');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download='sumo_live_results.csv';link.click();URL.revokeObjectURL(url);}catch(e){setError(String(e));}finally{setDownloading(false);}}}>{t("Download results CSV")}</button></div>
      <LiveSensorPlot title={t("Influent variables · simulation inputs")} groupTitle="Influent variables"
        options={influentPlotOptions} history={history} source="simulation"
        simulationResult={liveRun?.result} runId={liveRun?.id||'simulation-inputs'} />
      <LiveSensorPlot title={t("DO concentrations · simulation inputs")} groupTitle="DO concentrations"
        options={doPlotOptions} history={history} className="live-do-card" source="simulation"
        simulationResult={liveRun?.result} runId={liveRun?.id||'simulation-inputs'} />
      {comparisons?.error&&<p role="status">{t(comparisons.error)}</p>}
      {comparisons?.aggregation_seconds&&<p className="calibration-note">{t("Dotted sensor curves from ")}{t(comparisons.database || 'sumo_web_database')}{t(": recorded nitrate and MLSS/MLVSS means over ")}{t(comparisons.aggregation_seconds)}{t(" seconds, compared with corresponding simulation results. Missing measurements remain gaps.")}</p>}
      <SumoOutputDashboard localTime pollutants={realtimePollutantOptions} showInfluent={false} showDo={false} influent={influentPlotOptions} result={visualisationResult} runId={liveRun?.id||''}/>
    </section>
  </>;
}
