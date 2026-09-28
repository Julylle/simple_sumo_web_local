import { useState } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import type { WorkspaceTab } from './components/Sidebar';
import { Placeholder } from './components/EmptyState';
import { SimulationConfiguration } from './components/SimulationConfiguration';
import { SimulationResults } from './components/SimulationResults';
import { useSimulation } from './hooks/useSimulation';
import './style.css';

const tabLabels: Record<WorkspaceTab, string> = {
  simulation: 'Simulation',
  comparison: 'Comparison',
  history: 'Run history',
};

export default function App() {
  const [tab, setTab] = useState<WorkspaceTab>('simulation');
  const { parameters, data, busy, error, dirty, updateParameter, run, reset } = useSimulation();

  async function handleRun() {
    if (await run()) setTab('simulation');
  }

  return (
    <div className="app-shell">
      <Header />
      <Sidebar tab={tab} onTabChange={setTab} />
      <main className="workspace">
        <div className="breadcrumb">
          Models <span>/</span> ODE Demo <span>/</span> {tabLabels[tab]}
        </div>
        {tab === 'simulation' && <>
    <section className="page-head"><div><h1>Real-time Simulation</h1><p>Configure boundary and operating conditions, run the server-side model, and inspect approved outputs.</p></div><div className="run-controls">{dirty&&<span className="dirty">● Parameters changed</span>}<button className="secondary" onClick={reset} disabled={busy}>Reset</button><button className="primary" onClick={handleRun} disabled={busy}><span>{busy?'◌':'▶'}</span>{busy?'Running model…':'Run simulation'}</button></div></section>
    {error&&<div className="alert"><b>Simulation failed</b><span>{error}</span></div>}

          <SimulationConfiguration parameters={parameters} onChange={updateParameter} />
          <SimulationResults data={data} parameters={parameters} />
        </>}
        {tab === 'comparison' && <Placeholder
          title="Scenario comparison"
          text="This workspace is reserved for comparing multiple saved simulation runs. The current MVP keeps only the latest run in the browser."
        />}
        {tab === 'history' && <Placeholder
          title="Run history"
          text="Run history will be connected to a server-side store (and optionally OpenSearch) without exposing private model files or raw datasets."
        />}
      </main>
    </div>
  );
}
