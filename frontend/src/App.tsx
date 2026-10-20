import { t, useLanguage } from './i18n';
import { RealTimeSumo } from "./components/RealTimeSumo";
import { SumoSimulation } from "./components/SumoSimulation";
import { CalibrationParameters } from "./components/CalibrationParameters";
import { CalibrationComparison } from "./components/CalibrationComparison";
import { useState } from "react";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import type { WorkspaceTab } from "./components/Sidebar";
import { Placeholder } from "./components/EmptyState";
import { SimulationConfiguration } from "./components/SimulationConfiguration";
import { ProcessConfiguration } from "./components/ProcessConfiguration";
import { SimulationResults } from "./components/SimulationResults";
import { useSimulation } from "./hooks/useSimulation";
import type { OxygenMode } from "./api/client";
import "./style.css";

const tabLabels: Record<WorkspaceTab, string> = {
  simulation: "Simulation",
  "auto-calibration": "Auto-Calibration",
  history: "Run history",
  sumo: "Offline SUMO",
  "realtime-sumo": "Real-time SUMO",
};

export default function App() {
  useLanguage();
  const [tab, setTab] = useState<WorkspaceTab>("sumo");
  const { inputSeries, parameters, data, busy, error, dirty, updateParameter, run, reset, calibration, calibrationError, calibrationLoaded, updateCalibration, retryCalibration,
    runAutoCalibration, autoCalibrationBusy, autoCalibrationError, autoCalibrationComplete,
    measurements, measurementBusy, measurementError, uploadMeasurements, comparison,
    autoParameters, updateAutoParameter, saveCalibratedParameters, applyCalibratedParameters,
    parameterActionStatus, simulationParameterStatus, simulationMeasurements,
    oxygenMode, doSetpoints, updateOxygenMode, updateDoSetpoint } =
    useSimulation();

  async function handleRun() {
    if (await run()) setTab("simulation");
  }

  return (
    <div className="app-shell">
      <Header engine={(tab === "sumo" || tab === "realtime-sumo") ? "SUMO" : "Python"} />
      <Sidebar tab={tab} onTabChange={setTab} />
      <main className="workspace">
        <div className="breadcrumb"> {t("Models")} <span>/</span> {t((tab === "sumo" || tab === "realtime-sumo") ? "SUMO" : "Python ASM")} <span>/</span> {t(tabLabels[tab])}
        </div>
        <div hidden={tab !== "sumo"}><SumoSimulation /></div>
        {tab === "realtime-sumo" && <RealTimeSumo />}
        {tab === "simulation" && (
          <>
            <section className="page-head">
              <div>
                <h1>{t("Process modelling demo")}</h1>
                <p> {t("Configure boundary and operating conditions, run the server-side model, and inspect approved outputs.")} </p>
              </div>
            </section>
            {error && (
              <div className="alert">
                <b>{t("Simulation failed")}</b>
                <span>{t(error)}</span>
              </div>
            )}

            <ProcessConfiguration parameters={parameters} onChange={updateParameter} inputSeries={inputSeries} busy={busy} />
            <SimulationConfiguration
              parameters={parameters}
              onChange={updateParameter}
              busy={busy}
              dirty={dirty}
              onRun={handleRun}
              onReset={reset}
            />
            {simulationParameterStatus && <p role="status" className="measurement-ready">{t(simulationParameterStatus)}</p>}
            <SimulationResults data={data} parameters={parameters} measurements={simulationMeasurements} calibrationPanel={
              <CalibrationParameters parameters={calibration} loaded={calibrationLoaded}
                error={calibrationError} busy={busy} onChange={updateCalibration} onRetry={retryCalibration} />
            } />
          </>
        )}
        {tab === "auto-calibration" && (
          <>
            <section className="page-head">
              <div>
                <h1>{t("Auto-Calibration")}</h1>
                <p>{t("Upload measured data, calibrate kinetic parameters, and compare model predictions with observations.")}</p>
              </div>
              <button className="primary" onClick={runAutoCalibration} disabled={busy || measurementBusy || !measurements || !calibrationLoaded || !!calibrationError}>
                {t(autoCalibrationBusy ? t("Calibrating…") : t("Run auto-calibration"))}
              </button>
            </section>
            <section className="config-card">
              <div className="chart-head"><div><h3>{t("Oxygen control")}</h3><p>{t("Select the oxygen mode used throughout auto-calibration and its comparison curves.")}</p></div></div>
              <div className="measurement-actions" role="group" aria-label={t("Oxygen control mode")}>
                {([['do_setpoint', t('DO setpoint')], ['constant_kla', t('Constant KLa')], ['calculated_kla', t('Calculated KLa')]] as [OxygenMode, string][]).map(([value, label]) => (
                  <button key={value} className={oxygenMode === value ? "primary" : "secondary"} aria-pressed={oxygenMode === value}
                    disabled={busy} onClick={() => updateOxygenMode(value)}>{t(label)}</button>
                ))}
              </div>
              {oxygenMode === "do_setpoint" ? <>
                <p className="calibration-note">{t("Hold each tank at the specified DO. KLa parameters remain unchanged because oxygen transfer is not used in this mode.")}</p>
                <div className="fields">
                  {doSetpoints.map((value, index) => <label className="field" key={index}>
                    <span className="field-label">{t("Tank")} {t(index + 1)} DO (mg/L)</span>
                    <div className="input-wrap"><input type="number" min="0" max="8" step="any" value={value} disabled={busy}
                      onChange={event => updateDoSetpoint(index, event.target.value)} /></div>
                  </label>)}
                </div>
              </> : <p className="calibration-note">{t(oxygenMode === "constant_kla"
                ? t("Use kla1O2, kla2O2 and kla3O2 from the parameter table as time-constant KLa values (1/day). They are optimized during calibration; DO is calculated dynamically.")
                : t("Scale kla1O2, kla2O2 and kla3O2 with uploaded airflow relative to its initial average. KLa varies with time and DO is calculated dynamically."))}</p>}
            </section>
            <section className="config-card measurement-upload">
              <div className="chart-head"><div><h3>{t("Measured data")}</h3><p>{t("Upload an Excel workbook to run dynamic auto-calibration.")}</p></div></div>
              <p className="calibration-note">{t("Use the format of")} <code>TwoDays_Subiaco_DynamicCali_20260401.xlsx</code>: <b>validation</b> {t("for tank measurements and")} <b>dyinput</b> {t("for influent, flows and aeration. Both sheets use")} <b>t (min)</b>{t(", starting at 0.")}</p>
              <div className="measurement-actions">
                <label htmlFor="calibration-workbook">{t("Upload measured data (.xlsx, max 5 MB)")} <input id="calibration-workbook" type="file" accept=".xlsx" disabled={busy || measurementBusy}
                    onChange={event => { const file = event.target.files?.[0]; if (file) void uploadMeasurements(file); event.target.value = ""; }} />
                </label>
                <a href="/api/calibration-measurements/template" download>{t("Download Excel template")}</a>
              </div>
              <p className="calibration-note">{t("Concentrations: mg/L. dyinput flows: plant-wide L/s; airflow: m³/h. Include O2, NH4-N, NO2-N and NO3-N for tanks 1–5; N2O-N is optional. Blank measurements are allowed.")}</p>
              {measurementBusy && <p role="status">{t("Uploading and validating workbook…")}</p>}
              {measurementError && <div className="alert" role="alert">{t(measurementError)}</div>}
              {measurements && <p className="measurement-ready" role="status">{t("Loaded:")} <b>{measurements.filename}</b> · {measurements.time_h.length} {t("timestamps ·")} {t(measurements.time_h[measurements.time_h.length - 1].toFixed(2))} h · {Object.keys(measurements.variables).length} {t("measurement series")}</p>}
            </section>
            {autoCalibrationError && <div className="alert" role="alert"><b>{t("Auto-calibration failed")}</b><span>{t(autoCalibrationError)}</span></div>}
            {autoCalibrationBusy && <p role="status">{t("Optimization is running. This may take several minutes.")}</p>}
            {autoCalibrationComplete && <p role="status">{t("Calibration complete. Save the optimized parameters or update Simulation to use them in your next run.")}</p>}
            <div className="measurement-actions">
              <button className="secondary" disabled={!autoCalibrationComplete || busy} onClick={saveCalibratedParameters}>{t("Save parameters (.json)")}</button>
              <button className="primary" disabled={!autoCalibrationComplete || busy}
                onClick={() => { if (applyCalibratedParameters()) setTab("simulation"); }}>{t("Update parameters to Simulation")}</button>
              {parameterActionStatus && <span role="status">{t(parameterActionStatus)}</span>}
            </div>
            <section className="chart-grid">
            <CalibrationComparison measurements={measurements} result={comparison} current={autoCalibrationComplete} />
            <CalibrationParameters parameters={autoParameters} loaded={calibrationLoaded}
              error={calibrationError} busy={busy} onChange={updateAutoParameter} onRetry={retryCalibration}
              description={t("Edit initial values, then Run auto-calibration. Values outside the script's search bounds are clipped for the initial guess.")} />
            </section>
          </>
        )}
        {tab === "history" && (
          <Placeholder
            title={t("Run history")}
            text={t("Run history will be connected to a server-side store (and optionally OpenSearch) without exposing private model files or raw datasets.")}
          />
        )}
      </main>
    </div>
  );
}
