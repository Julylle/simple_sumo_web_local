import type { Layout } from 'plotly.js';

// Plotly also uses these values when exporting standalone PNGs.
export const scientificPlotGrid = '#e0e9ed';

export const scientificPlotLayout: Partial<Layout> = {
  paper_bgcolor: '#ffffff',
  plot_bgcolor: '#f8fafb',
  font: {
    family: 'Instrument Sans, Segoe UI, Microsoft YaHei, sans-serif',
    size: 12,
    color: '#425866',
  },
  hoverlabel: {
    bgcolor: '#ffffff',
    bordercolor: '#d4e0e6',
    font: { size: 12 },
  },
};
