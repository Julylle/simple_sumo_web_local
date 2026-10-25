import { useEffect, useState } from 'react';

// Best-effort browser drafts. Simulation results are owned by the backend.
export function useLiveSetting<T>(name: string, fallback: T) {
  const key = `sumo-live:v1:${name}`;
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw !== null) {
        const saved = JSON.parse(raw);
        if (saved !== null && typeof saved === typeof fallback &&
            Array.isArray(saved) === Array.isArray(fallback)) return saved as T;
      }
    } catch { /* Storage may be disabled or contain an invalid draft. */ }
    return fallback;
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(value)); }
    catch { /* Browser quotas must not interrupt a server-side simulation. */ }
  }, [key, value]);
  return [value, setValue] as const;
}
