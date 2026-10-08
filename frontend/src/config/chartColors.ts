// Plotly's default palette, keyed by the ASM variable order so filtering does
// not change a variable's color and both workspace charts remain consistent.
const palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"];
const soluble = ["N2", "N2O", "NH", "NH2OH", "NO", "NO2", "NO3", "O", "S"];
const biomass = ["AOB", "H", "I", "NOB"];

export function variableColor(name: string): string {
  const match = /^([SX])([1-5])(.+)$/.exec(name);
  if (!match) return palette[0];
  const [, phase, tank, component] = match;
  const components = phase === "S" ? soluble : biomass;
  const componentIndex = components.indexOf(component);
  if (componentIndex < 0) return palette[0];
  const index = (phase === "S" ? 0 : 45) + (Number(tank) - 1) * components.length + componentIndex;
  return palette[index % palette.length];
}
