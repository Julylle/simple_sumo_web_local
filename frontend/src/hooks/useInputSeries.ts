import { useEffect, useState } from "react";
import { uploadInputSeries } from "../api/client";
import type { InputSeriesInfo, InputSeriesKey } from "../api/client";

const storageKey = "mle-input-series-v1";
export function useInputSeries() {
  const [selected, setSelected] = useState<Partial<Record<InputSeriesKey, InputSeriesInfo>>>(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) ?? "{}"); } catch { return {}; }
  });
  const [defaults, setDefaults] = useState<Partial<Record<InputSeriesKey, InputSeriesInfo>>>({});
  const [errors, setErrors] = useState<Partial<Record<InputSeriesKey, string>>>({});
  const [uploading, setUploading] = useState<Partial<Record<InputSeriesKey, boolean>>>({});
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(selected)); }
    catch { setLoadError("Browser storage unavailable. Uploads are saved on the server, but this selection cannot survive a refresh."); }
  }, [selected]);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/input-series/defaults", { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("Could not load built-in input series");
      const values = await response.json();
      if (!controller.signal.aborted) { setDefaults(values); setLoadError(""); }
    }).catch(error => { if (!controller.signal.aborted) setLoadError(String(error)); });
    return () => controller.abort();
  }, [attempt]);
  async function upload(key: InputSeriesKey, file: File) {
    setUploading(current => ({ ...current, [key]: true }));
    setErrors(current => ({ ...current, [key]: "" }));
    try {
      const info = await uploadInputSeries(key, file);
      setSelected(current => ({ ...current, [key]: info }));
    } catch (error) { setErrors(current => ({ ...current, [key]: error instanceof Error ? error.message : "Import failed" })); }
    finally { setUploading(current => ({ ...current, [key]: false })); }
  }
  function restore(key: InputSeriesKey) {
    setSelected(current => { const next = { ...current }; delete next[key]; return next; });
    setErrors(current => ({ ...current, [key]: "" }));
  }
  const ids = Object.fromEntries(Object.entries(selected).filter(([, info]) => info?.id).map(([key, info]) => [key, info!.id!]));
  return { selected, defaults, errors, uploading, upload, restore, ids, loadError,
    pending: Object.values(uploading).some(Boolean), retry: () => setAttempt(value => value + 1) };
}
export type InputSeriesControls = ReturnType<typeof useInputSeries>;
