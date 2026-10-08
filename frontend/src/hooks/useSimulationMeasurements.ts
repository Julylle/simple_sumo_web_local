import { useState } from "react";
import { uploadSimulationMeasurements } from "../api/client";
import type { MeasurementUpload } from "../api/client";

export function useSimulationMeasurements() {
  const [data, setData] = useState<MeasurementUpload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file: File) {
    if (busy) return;
    setError("");
    setData(null);
    if (!file.name.toLowerCase().endsWith(".xlsx") || file.size > 5 * 1024 * 1024) {
      setError("Choose an .xlsx workbook under 5 MB.");
      return;
    }
    setBusy(true);
    try { setData(await uploadSimulationMeasurements(file)); }
    catch (error: unknown) { setError(error instanceof Error ? error.message : "Upload failed"); }
    finally { setBusy(false); }
  }

  return { data, busy, error, upload, clear: () => { setData(null); setError(""); } };
}
