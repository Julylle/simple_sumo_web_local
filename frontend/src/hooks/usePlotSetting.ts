import { useCallback, useRef, useState, type SetStateAction } from 'react';
import { readPlotSetting, writePlotSetting } from '../utils/plotSettings';

/** Persist on user actions, not mount: delayed results cannot overwrite preferences. */
export function usePlotSetting<T>(key: string, fallback: T, valid: (value: unknown) => value is T) {
  const [state, setState] = useState(() => ({key, value: readPlotSetting(key, fallback, valid)}));
  const current = useRef(state);
  if (current.current.key !== key) {
    current.current = {key, value: readPlotSetting(key, fallback, valid)};
  }
  const setValue = useCallback((action: SetStateAction<T>) => {
    const previous = current.current.value;
    const value = typeof action === 'function' ? (action as (value: T) => T)(previous) : action;
    if (value === previous) return;
    current.current = {key, value};
    writePlotSetting(key, value);
    setState(current.current);
  }, [key]);
  return [current.current.value, setValue] as const;
}
