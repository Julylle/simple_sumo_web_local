import { useSyncExternalStore } from 'react';
import { zh } from './zh';

export type Language = 'en' | 'zh';
const storageKey = 'model-platform-language';
let language: Language = 'en';
try { if (localStorage.getItem(storageKey) === 'zh') language = 'zh'; } catch { /* Storage is optional. */ }
const listeners = new Set<() => void>();
function updateDocument() {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.title = language === 'zh' ? '活性污泥模型模拟' : 'Activated Sludge Model Simulation';
}
updateDocument();
export function setLanguage(next: Language) {
  language = next;
  try { localStorage.setItem(storageKey, next); } catch { /* Keep the session preference. */ }
  updateDocument();
  listeners.forEach(listener => listener());
}
export function useLanguage() {
  return useSyncExternalStore(callback => { listeners.add(callback); return () => { listeners.delete(callback); }; }, () => language);
}

// Accept render values as well as text; React elements and numeric data pass through unchanged.
export function t<T>(value: T): T {
  if (language !== 'zh' || typeof value !== 'string') return value;
  const text = value.trim().replace(/\s+/g, ' ');
  let translated = zh[text];
  if (!translated) {
    translated = text
      .replace(/^Error: (.+)$/, (_, detail: string) => `错误：${t(detail)}`)
      .replace(/^Sensor comparisons from (.+) unavailable\. (.+)$/, (_, database: string, detail: string) => `无法从 ${database} 读取传感器对比数据。${t(detail)}`)
      .replace(/^Request failed \((\d+)\)$/, '请求失败（$1）')
      .replace(/^Remove (Sumo__.+)$/, '移除 $1')
      .replace(/^· (\d+) loaded intervals remaining$/, '· 剩余 $1 个已加载区间')
      .replace(/^([\d.]+) min$/, '$1 分钟')
      .replace(/^([\d.]+) s$/, '$1 秒')
      .replace(/^(CSTR\d+_\d+) nitrate · sensor$/, '$1 硝酸盐 · 传感器')
      .replace(/^SUMO rejected command: (.+)$/, 'SUMO 拒绝执行命令：$1')
      .replace(/^OPC UA unavailable; live simulation stopped: (.+)$/, (_, detail: string) => `OPC UA 不可用，实时模拟已停止：${t(detail)}`)
      .replace(/^History data missing at (.+): (.+)$/, '历史数据缺失，时间 $1：$2')
      .replace(/^Influent (.+)$/, '进水 $1')
      .replace(/^Comparison (\d+)$/, '对比图 $1')
      .replace(/^(\d+) influent parameters selected$/, '已选择 $1 个进水参数')
      .replace(/^Aerobic (\d+) airflow rate$/, '好氧池 $1 曝气量')
      .replace(/^Import (.+) Excel time series$/, (_, label: string) => `导入 ${t(label)} Excel 时间序列`)
      .replace(/^(.*) · Simulated$/, '$1 · 模拟值')
      .replace(/^(.*) · Measured$/, '$1 · 实测值')
      .replace(/^(.*) · Before calibration$/, '$1 · 校准前')
      .replace(/^(.*) · After calibration$/, '$1 · 校准后')
      .replace(/^(.*) \[right\]$/, '$1 [右轴]')
      .replace(/^SUMO request failed \((\d+)\)$/, 'SUMO 请求失败（$1）')
      .replace(/^Could not load calibration parameters \((\d+)\)$/, '无法加载校准参数（$1）')
      .replace(/^(Upload failed|Import failed|Auto-calibration failed|Simulation failed) \((\d+)\)$/, (_, label: string, code: string) => `${t(label)}（${code}）`)
      .replace(/^Calibration parameter (.+)$/, '校准参数 $1')
      .replace(/^CSV line (\d+): (.+)$/, (_, line: string, detail: string) => `CSV 第 ${line} 行：${t(detail)}`);
  }
  return (translated === text && !zh[text] ? value : `${value.match(/^\s*/)?.[0] ?? ''}${translated}${value.match(/\s*$/)?.[0] ?? ''}`) as T;
}
