import { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';

type UploadedInput = { id: string; filename: string; count: number; end_h: number };
type Run = { id: string; status: 'running' | 'completed' | 'failed'; error?: string;
  phase?: string; progress_pct?: number; simulated_h?: number; duration_h?: number;
  result?: { time_h: number[]; variables: Record<string, number[]> } };
const labels: Record<string, string> = { influent_nh4: 'Influent NH4-N', influent_tkn: 'Influent TKN',
  influent_cod: 'Influent COD', effluent_nh4: 'Effluent NH4-N', effluent_nox: 'Effluent NOx-N' };
async function request(url: string, init?: RequestInit): Promise<Run> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `SUMO request failed (${response.status})`);
  return body;
}
export function SumoSimulation() {
  const [uploaded, setUploaded] = useState<UploadedInput | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [selected, setSelected] = useState<string[]>(Object.keys(labels));
  const [view, setView] = useState<'separate' | 'overlay'>('separate');
  const [duration, setDuration] = useState('168');
  const [run, setRun] = useState<Run | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const busy = starting || run?.status === 'running';
  const progress = starting ? 0 : run?.progress_pct ?? 0;
  const phase = starting ? 'Submitting simulation...' : ({ starting: 'Initializing SUMO...', simulating: 'Simulating',
    finalizing: 'Saving and validating results...', completed: 'Simulation complete', failed: 'Simulation failed' }[run?.phase ?? ''] ?? 'Ready to simulate');
  const colors = ['#2563eb', '#7c3aed', '#d97706', '#059669', '#dc2626'];
  function traces(keys: string[]) {
    return keys.map(key => ({ x: run?.result?.time_h ?? [], y: run?.result?.variables[key] ?? [],
      type: 'scatter' as const, mode: 'lines' as const, name: labels[key] ?? key,
      line: { color: colors[Object.keys(labels).indexOf(key)], width: 2 },
      hovertemplate: '%{x:.2f} h | %{y:.3f} mg/L<extra>%{fullData.name}</extra>' }));
  }
  function chart(keys: string[], overlay = false) {
    return <Plot data={traces(keys)} layout={{ autosize: true, height: overlay ? 460 : 290,
      xaxis: { title: { text: 'Time (h)' }, gridcolor: '#edf0f3' },
      yaxis: { title: { text: 'Concentration (mg/L)' }, gridcolor: '#edf0f3', rangemode: 'tozero' },
      showlegend: overlay, legend: { orientation: 'h' }, margin: { t: 20, b: overlay ? 100 : 55, l: 65, r: 20 },
      hovermode: 'x unified' }} config={{ responsive: true, displaylogo: false,
        toImageButtonOptions: { format: 'png', filename: `sumo-${keys.join('-')}`, scale: 2 } }}
      useResizeHandler style={{ width: '100%' }} />;
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
      const response = await fetch(`/api/sumo/input?filename=${encodeURIComponent(file.name)}`, {
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
    if (busy || uploading || uploadError) return;
    setStarting(true); setError('');
    try { setRun(await request('/api/sumo/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_h: Number(duration), input_id: uploaded?.id ?? null }) })); }
    catch (e) { setError(e instanceof Error ? e.message : 'SUMO failed'); }
    finally { setStarting(false); }
  }
  return <>
    <section className="page-head"><div><h1>SUMO Offline Simulation</h1><p>Cixi Eastern WWTP · Dynamic simulation from the saved steady state</p></div></section>
    <section className="config-card">
      <div className="section-title"><div><h2>Simulation settings</h2><p>Uses the model's saved operating parameters and the supplied influent TKN / COD time series.</p></div></div>
      <p className="calibration-note">Results include influent NH4-N, TKN and COD, and effluent NH4-N and NOx-N. Concentrations are in mg/L.</p>
      <div className="measurement-actions">
        <label htmlFor="sumo-influent-csv">Upload Sumo__Plant__Influent__param.csv
          <input id="sumo-influent-csv" type="file" accept=".csv,text/csv" disabled={busy || uploading}
            onChange={event => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = ''; }} />
        </label>
        <button className="secondary" disabled={busy || uploading || (!uploaded && !uploadError)}
          onClick={() => { setUploaded(null); setUploadError(''); }}>Use default CSV</button>
      </div>
      <p className="calibration-note">UTF-8 CSV, max 1 MB. Columns: <code>sim_time_ms</code>, <code>Sumo__Plant__Influent__param__TKN</code>, <code>Sumo__Plant__Influent__param__TCOD</code>. Start at 0; times must increase in multiples of 300000 ms (5 minutes). Concentrations: mg/L. The last value is held until the simulation ends.</p>
      {uploading ? <p role="status">Uploading and validating CSV...</p> : uploaded
        ? <p className="measurement-ready" role="status">Selected: {uploaded.filename} | {uploaded.count} rows | Last input: {uploaded.end_h.toFixed(2)} h</p>
        : <p className="calibration-note">Using default Sumo__Plant__Influent__param.csv.</p>}
      {uploadError && <div className="alert" role="alert">{uploadError}</div>}
      <label className="field"><span className="field-label">Duration (hours, 1–168)</span>
        <div className="input-wrap"><input type="number" min="1" max="168" step="any" value={duration} disabled={busy} onChange={e => setDuration(e.target.value)} /></div></label>
      <p><button className="primary" onClick={start} disabled={busy || uploading || !!uploadError || !duration.trim() || !Number.isFinite(Number(duration)) || Number(duration) < 1 || Number(duration) > 168}>{busy ? 'Running SUMO…' : 'Run SUMO'}</button></p>
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
      <div className="sumo-output-controls">
        <fieldset><legend>Output variables (mg/L)</legend>
          {Object.entries(labels).map(([key, label]) => <label key={key}>
            <input type="checkbox" checked={selected.includes(key)} onChange={e => setSelected(current =>
              e.target.checked ? [...current, key] : current.filter(item => item !== key))} />{label}
          </label>)}
        </fieldset>
        <div className="measurement-actions" role="group" aria-label="Plot layout">
          <button className={view === 'separate' ? 'primary' : 'secondary'} aria-pressed={view === 'separate'} onClick={() => setView('separate')}>Separate plots</button>
          <button className={view === 'overlay' ? 'primary' : 'secondary'} aria-pressed={view === 'overlay'} onClick={() => setView('overlay')}>Overlay plots</button>
        </div>
      </div>
      {!selected.length && <p role="status">Select at least one output variable to display.</p>}
      {!!selected.length && !run?.result && <div className="empty"><b>{busy ? 'Waiting for simulation results' : 'No simulation results yet'}</b><span>Run SUMO to populate the selected output plots.</span></div>}
      {run?.result && !!selected.length && (view === 'overlay' ? chart(selected, true) :
        <div className="sumo-plots">{selected.map(key => <article className="chart-card" key={key}>
          <div className="chart-head"><h3>{labels[key]}</h3><span className="chart-chip">mg/L</span></div>
          {chart([key])}
        </article>)}</div>)}
    </section>
  </>;
}
