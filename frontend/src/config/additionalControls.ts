// Source: Julylle/Sumo_web/demo_MLE/cx_opcua1124.csv.
export const defaultControlMapping: Record<string,string> = {
  Sumo__Plant__Sideflowdivider3__param__Qpumped_target: 'ns=2;s=SiemensEth.PLC204.F_Q2',
  Sumo__Plant__Carbon1__param__Q: 'ns=2;s=SiemensEth.PLC200.I_carbon_flow',
  Sumo__Plant__Carbon2__param__Q: 'ns=2;s=SiemensEth.PLC200.II_carbon_flow',
  Sumo__Plant__Metal1__param__Q: 'ns=2;s=SiemensEth.PLC204.HDC_AlSO4_flow',
};
export const controlSensorOptions = Object.keys(defaultControlMapping).map(name => ({
  name, label: `${name.split('__')[2]} · ${name.split('__').pop()}`, unit: 'm3/d',
}));
