import { useEffect, useRef, useState } from 'react';
import { SumoOutputDashboard } from './SumoOutputDashboard';

type InputOption = { name: string; label: string; unit: string };
type UploadedInput = { id: string; filename: string; count: number; end_h: number; columns: string[] };
type Run = { id: string; status: 'running' | 'completed' | 'failed'; error?: string;
  phase?: string; progress_pct?: number; simulated_h?: number; duration_h?: number;
  result?: { time_h: number[]; variables: Record<string, number[]> } };
async function request(url: string, init?: RequestInit): Promise<Run> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `SUMO request failed (${response.status})`);
  return body;
}
export function SumoSimulation() {
  const [inputMenuOpen, setInputMenuOpen] = useState(false);
  const inputMenuRef = useRef<HTMLDivElement>(null);
  const [inputOptions, setInputOptions] = useState<InputOption[]>([]);
  const [inputColumns, setInputColumns] = useState<string[]>([
    'Sumo__Plant__Influent__param__TKN', 'Sumo__Plant__Influent__param__TCOD',
  ]);
  const [optionsError, setOptionsError] = useState('');
  const [templateBusy, setTemplateBusy] = useState(false);
  const [uploaded, setUploaded] = useState<UploadedInput | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [duration, setDuration] = useState('168');
  const [run, setRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const busy = starting || run?.status === 'running';
  const inputMenuDisabled = busy || uploading || templateBusy || !inputOptions.length;
  useEffect(() => {
    if (inputMenuDisabled) setInputMenuOpen(false);
  }, [inputMenuDisabled]);
  useEffect(() => {
    if (!inputMenuOpen) return;
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !inputMenuRef.current?.contains(event.target)) setInputMenuOpen(false);
    }
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [inputMenuOpen]);
  const progress = starting ? 0 : run?.progress_pct ?? 0;
  const phase = starting ? 'Submitting simulation...' : ({ starting: 'Initializing SUMO...', simulating: 'Simulating',
    finalizing: 'Saving and validating results...', completed: 'Simulation complete', failed: 'Simulation failed' }[run?.phase ?? ''] ?? 'Ready to simulate');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/sumo/input-options', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Could not load influent parameters. Refresh to retry.');
      const options: InputOption[] = await response.json();
      if (!controller.signal.aborted) setInputOptions(options);
    }).catch(e => { if (!controller.signal.aborted) setOptionsError(e instanceof Error ? e.message : 'Could not load parameters.'); });
    return () => controller.abort();
  }, []);
  function selectInput(name: string, checked: boolean) {
    setInputColumns(current => checked ? [...current, name] : current.filter(column => column !== name));
    setUploaded(null);
    setUploadError('');
  }
  async function downloadTemplate() {
    if (!inputColumns.length || templateBusy) return;
    setTemplateBusy(true); setUploadError('');
    try {
      const response = await fetch('/api/sumo/input-template', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ columns: inputColumns }) });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not generate template.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'Sumo__Plant__Influent__param.csv';
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setUploadError(e instanceof Error ? e.message : 'Template download failed.'); }
    finally { setTemplateBusy(false); }
  }
  useEffect(() => {
    if (run?.status !== 'running') return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request(`/api/sumo/runs/${run!.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(next);
        setError('');
        if (next.status === 'running') timer = setTimeout(poll, 2000);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : 'Could not read SUMO status');
          timer = setTimeout(poll, 5000);
        }
      }
    }
    timer = setTimeout(poll, 1000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [run?.id, run?.status]);
  async function upload(file: File) {
    setUploadError(''); setUploaded(null);
    if (!file.name.toLowerCase().endsWith('.csv') || file.size > 1024 * 1024) {
      setUploadError('Choose a CSV file no larger than 1 MB.'); return;
    }
    setUploading(true);
    try {
      const query = new URLSearchParams({ filename: file.name });
      inputColumns.forEach(column => query.append('columns', column));
      const response = await fetch(`/api/sumo/input?${query}`, {
        method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: file,
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'CSV upload failed');
      setUploaded(body);
    } catch (e) { setUploadError(e instanceof Error ? e.message : 'CSV upload failed'); }
    finally { setUploading(false); }
  }
  async function download() {
    if (run?.status !== 'completed' || downloading) return;
    setDownloading(true); setError('');
    try {
      const response = await fetch(`/api/sumo/runs/${run.id}/download`);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? 'Result download failed');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `sumo_results_${run.id}.csv`;
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'Result download failed'); }
    finally { setDownloading(false); }
  }
  async function start() {
    if (busy || uploading || uploadError || !uploaded) return;
    setStarting(true); setError('');
    try { setRun(await request('/api/sumo/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_h: Number(duration), input_id: uploaded.id, input_columns: inputColumns }) })); }
    catch (e) { setError(e instanceof Error ? e.message : 'SUMO failed'); }
    finally { setStarting(false); }
  }
  return <>
    <section className="page-head"><div><h1>SUMO Offline Simulation</h1><p>Cixi Eastern WWTP </p></div></section>
    <section className="config-card">
      <div className="section-title">
        <div><h2>Simulation settings</h2>
      {/* <p>Uses the model's saved operating parameters and the supplied influent TKN / COD time series.</p> */}
        </div>
      </div>
      {/* <p className="calibration-note">Results include influent NH4-N, TKN and COD, and effluent NH4-N and NOx-N. Concentrations are in mg/L.</p> */}
      <section className="sumo-influent-inputs" aria-labelledby="sumo-influent-title">
        <h3 id="sumo-influent-title">Step1: Select parameters and download the template</h3>
        <div className="calibration-note">
          <p>Upload a completed template for the selected parameters before running. Changing the selection requires a new upload.</p>
        </div>
        <div className="sumo-input-toolbar">
        <div className="sumo-input-dropdown" ref={inputMenuRef}
          onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setInputMenuOpen(false); }}
          onKeyDown={event => {
            if (event.key === 'Escape' && inputMenuOpen) {
              setInputMenuOpen(false);
              inputMenuRef.current?.querySelector('button')?.focus();
              event.stopPropagation();
            }
          }}>
          <button type="button" className="sumo-input-trigger" disabled={inputMenuDisabled}
            aria-expanded={inputMenuOpen} aria-controls="sumo-influent-options"
            onClick={() => setInputMenuOpen(current => !current)}>
            <span>{inputColumns.length ? `${inputColumns.length} influent parameters selected` : 'Select influent parameters to update'}</span>
            <span aria-hidden="true">{inputMenuOpen ? '\u25B4' : '\u25BE'}</span>
          </button>
          {inputMenuOpen && <fieldset id="sumo-influent-options" className="sumo-input-options" disabled={inputMenuDisabled}>
            <legend>Select influent parameters to update</legend>
            {inputOptions.map(option => <label key={option.name}>
              <input type="checkbox" checked={inputColumns.includes(option.name)}
                onChange={event => selectInput(option.name, event.target.checked)} />
              <span><code>{option.name}</code><small>{option.unit}</small></span>
            </label>)}
          </fieldset>}
        </div>
          <button className="secondary" disabled={busy || uploading || templateBusy || !inputColumns.length || !inputOptions.length}
            onClick={downloadTemplate}>{templateBusy ? 'Generating template...' : 'Download data template'}</button>
        </div>
        {!!inputColumns.length && <p className="calibration-note">Selected: {inputColumns.map(name => name.split('__').pop()).join(', ')}</p>}
        {optionsError && <div className="alert" role="alert">{optionsError}</div>}
        {!inputOptions.length && !optionsError && <p role="status">Loading influent parameters...</p>}
        <h3 id="sumo-upload-title" className="sumo-step-title">Step2: Upload completed CSV template</h3>
        <div className="measurement-actions">
          <label htmlFor="sumo-influent-csv">
            <input id="sumo-influent-csv" type="file" accept=".csv,text/csv"
              disabled={busy || uploading || templateBusy || !inputColumns.length || !inputOptions.length}
              onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ''; }} />
          </label>
        </div>
        {!inputColumns.length && <p role="status">Select at least one influent parameter.</p>}
      </section>
      {uploading ? <p role="status">Uploading and validating CSV...</p> : uploaded
        ? <p className="measurement-ready" role="status">Selected: {uploaded.filename} | {uploaded.count} rows | Last input: {uploaded.end_h.toFixed(2)} h</p>
        : null}
      {uploadError && <div className="alert" role="alert">{uploadError}</div>}
        <h3 id="sumo-duration-title" className="sumo-step-title">Step3: Set up simulation duration</h3>
      <label className="field"><span className="field-label">Duration (hours)</span>
        <div className="input-wrap"><input type="number" min="1" max="168" step="any" value={duration} disabled={busy} onChange={e => setDuration(e.target.value)} /></div></label>
      <p><button className="primary" onClick={start} disabled={busy || uploading || !!uploadError || !uploaded || !duration.trim() || !Number.isFinite(Number(duration)) || Number(duration) < 1 || Number(duration) > 168}>{busy ? 'Running SUMO…' : 'Run SUMO'}</button></p>
      <div className="sumo-progress">
        <div className="sumo-progress-label"><span role="status">{phase}</span><b>{Math.floor(progress)}%</b></div>
        <progress max="100" value={progress} aria-label="Simulation progress" />
        <p>{(starting ? 0 : run?.simulated_h ?? 0).toFixed(2)} / {starting ? Number(duration) : run?.duration_h ?? Number(duration)} simulated hours</p>
        <small>Progress follows model simulation time. Results appear after saving and validation.</small>
      </div>
      {(error || run?.error) && <div className="alert" role="alert">{error || run?.error}</div>}
    </section>
    <section className="config-card">
      <div className="section-title"><div><h2>Output variables visualisation</h2><p>Select output variables and compare their changes over simulation time.</p></div>
        <button className="secondary" disabled={run?.status !== 'completed' || starting || downloading} onClick={download}>
          {downloading ? 'Downloading...' : 'Download results CSV'}
        </button></div>
      <p className="calibration-note">Download includes all recorded samples, timestamps, input assignments and output variables for the completed run.</p>
      <SumoOutputDashboard influent={inputColumns.map(key => ({key,
        label: `Influent ${key.split('__').pop()}`, unit: inputOptions.find(o => o.name === key)?.unit ?? ''}))}
        result={run?.result} runId={run?.id ?? ''} />
    </section>
  </>;
}
