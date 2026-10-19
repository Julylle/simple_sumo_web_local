import zhCN from 'plotly.js/lib/locales/zh-cn';
import type { Config } from 'plotly.js';
import type { Language } from './i18n';

export function plotLocale(language: Language): Partial<Config> {
  return { locale: language === 'zh' ? 'zh-cn' : 'en', locales: { 'zh-cn': zhCN } };
}
