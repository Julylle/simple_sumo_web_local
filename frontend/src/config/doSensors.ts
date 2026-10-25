// Source: Julylle/Sumo_web/demo_MLE/cx_opcua1124.csv
export const defaultDoMapping: Record<string,string> = {
  "Sumo__Plant__CSTR1_5__param__SO2": "ns=2;s=SiemensEth.PLC200.I_tank1_DO1",
  "Sumo__Plant__CSTR1_6__param__SO2": "ns=2;s=SiemensEth.PLC200.I_tank1_DO1",
  "Sumo__Plant__CSTR1_7__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO2",
  "Sumo__Plant__CSTR1_8__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO2",
  "Sumo__Plant__CSTR1_9__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO3",
  "Sumo__Plant__CSTR1_10__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO3",
  "Sumo__Plant__CSTR2_5__param__SO2": "ns=2;s=SiemensEth.PLC200.I_tank1_DO1",
  "Sumo__Plant__CSTR2_6__param__SO2": "ns=2;s=SiemensEth.PLC200.I_tank1_DO1",
  "Sumo__Plant__CSTR2_7__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO2",
  "Sumo__Plant__CSTR2_8__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO2",
  "Sumo__Plant__CSTR2_9__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO3",
  "Sumo__Plant__CSTR2_10__param__SO2": "ns=2;s=SiemensEth.PLC204.I_tank1_DO3",
  "Sumo__Plant__CSTR3_5__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO1",
  "Sumo__Plant__CSTR3_6__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO1",
  "Sumo__Plant__CSTR3_7__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO2",
  "Sumo__Plant__CSTR3_8__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO2",
  "Sumo__Plant__CSTR3_9__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO3",
  "Sumo__Plant__CSTR3_10__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO3",
  "Sumo__Plant__CSTR4_5__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO1",
  "Sumo__Plant__CSTR4_6__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO1",
  "Sumo__Plant__CSTR4_7__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO2",
  "Sumo__Plant__CSTR4_8__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO2",
  "Sumo__Plant__CSTR4_9__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO3",
  "Sumo__Plant__CSTR4_10__param__SO2": "ns=2;s=GEeth.PLC147.II_tank3_DO3"
};
export const doSensorOptions = Object.keys(defaultDoMapping).map(name => ({name, label: name.split("__")[2] + " · DO", unit: "mg O₂/L"}));
