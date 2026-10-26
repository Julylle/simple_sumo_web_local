import type { Viewport } from './plotViewport';

const prefix = 'sumo-plots:v1:';
export function readPlotSetting<T>(key: string, fallback: T, valid: (value: unknown) => value is T): T {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(prefix + key) ?? 'null');
    return valid(value) ? value : fallback;
  } catch { return fallback; }
}
export function writePlotSetting<T>(key: string, value: T) {
  try { localStorage.setItem(prefix + key, JSON.stringify(value)); }
  catch { /* Disabled or full storage must not interrupt the simulation UI. */ }
}
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);
export const stringList = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(item => typeof item === 'string');
export type PlotChoices = {selection: string[] | null; secondary: boolean; right: string[]};
export const validChoices = (value: unknown): value is PlotChoices => object(value) &&
  (value.selection === null || stringList(value.selection)) && typeof value.secondary === 'boolean' && stringList(value.right);
export type PlotCards = {ids: number[]; nextId: number};
export const validCards = (value: unknown): value is PlotCards => object(value) &&
  Array.isArray(value.ids) && value.ids.every(id => Number.isSafeInteger(id) && id > 0) &&
  new Set(value.ids).size === value.ids.length && Number.isSafeInteger(value.nextId) &&
  (value.nextId as number) > Math.max(0, ...value.ids);
export const validViewport = (value: unknown): value is Viewport => object(value) &&
  Object.entries(value).every(([axis, range]) => ['xaxis', 'yaxis', 'yaxis2'].includes(axis) &&
    Array.isArray(range) && range.length === 2 && range.every(bound =>
      typeof bound === 'string' || (typeof bound === 'number' && Number.isFinite(bound))));
