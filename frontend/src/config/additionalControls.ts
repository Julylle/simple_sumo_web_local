// Source: Julylle/Sumo_web/demo_MLE/cx_opcua1124.csv.
export const defaultControlMapping: Record<string,string> = {
  Sumo__Plant__Sideflowdivider3__param__Qpumped_target: 'ns=2;s=SiemensEth.PLC204.F_Q2',
  Sumo__Plant__Carbon1__param__Q: 'ns=2;s=SiemensEth.PLC200.I_carbon_flow',
  Sumo__Plant__Carbon2__param__Q: 'ns=2;s=SiemensEth.PLC200.II_carbon_flow',
  Sumo__Plant__Metal1__param__Q: 'ns=2;s=SiemensEth.PLC204.HDC_AlSO4_flow',
  Sumo__Plant__WAS_1__param__Qpumped_target: "ns=2;s=SiemensEth.PLC200.I_Q_WAS",
  Sumo__Plant__WAS_2__param__Qpumped_target: "ns=2;s=GEeth.PLC147.II_Q_WAS",
  Sumo__Plant__Clarifier1__param__Qsludge_target: "ns=2;s=Omron_PLC.PLC4.RAS_flow_Q_I",
  Sumo__Plant__Clarifier2__param__Qsludge_target: "ns=2;s=GEeth.PLC147.RAS_flow_Q_II",
  Sumo__Plant__MLR1_1__param__Qpumped_target: "ns=2;s=SiemensEth.PLC200.MLR _Flow_I_1",
  Sumo__Plant__MLR1_2__param__Qpumped_target: "ns=2;s=SiemensEth.PLC200.MLR _Flow_I_2",
  Sumo__Plant__Switchcontroller2__param__CVtreshold: "ns=2;s=MySQL.SWC1.parm_mlvss.parm_mlvss__1_",
  Sumo__Plant__Switchcontroller3__param__CVtreshold: "ns=2;s=MySQL.SWC3.parm_mlvss.parm_mlvss__1_",
  Sumo__Plant__Sideflowdivider9__param__Qpumped_target: "ns=2;s=GEeth.PLC128.Influent_flow_Q1",
};
export const controlSensorOptions = Object.keys(defaultControlMapping).map(name => ({
  name, label: `${name.split('__')[2]} · ${name.split('__').pop()}`, unit: name.endsWith('__CVtreshold') ? 'mg VSS/L' : 'm3/d',
}));
