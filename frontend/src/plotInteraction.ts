import type { Config, Layout } from 'plotly.js';
import type { Language } from './i18n';
import { plotLocale } from './plotLocale';

// Keep this revision independent of incoming data, run IDs and selections.
// Plotly retains each mounted chart's user ranges across react() updates.
export const plotInteractionLayout: Partial<Layout> = {
  uirevision: 'preserve-user-viewport',
  dragmode: 'zoom',
  // Live updates should not animate the axes underneath a drag gesture.
  transition: { duration: 0 },
};

export function plotInteractionConfig(language: Language): Partial<Config> {
  return {
    ...plotLocale(language),
    displaylogo: false,
    displayModeBar: true,
    responsive: true,
    modeBarButtons: [['toImage', 'resetScale2d', 'zoom2d']],
    // Only the explicit reset button should restore the full view.
    doubleClick: false,
    // Do not accidentally change the range while scrolling the page.
    scrollZoom: false,
    showTips: false,
    toImageButtonOptions: { format: 'png', filename: 'simulation-chart', scale: 2 },
  };
}
