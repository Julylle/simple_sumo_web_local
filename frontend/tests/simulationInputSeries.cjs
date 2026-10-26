const {test}=require('node:test');
const assert=require('node:assert/strict');
const {simulationInputSeries}=require('../src/utils/simulationInputSeries.ts');
const q='Sumo__Plant__Influent__param__Q';
const doKey='Sumo__Plant__CSTR3_5__param__SO2';
const series={time_h:[1/60,2/60],sensor_timestamps:['2026-10-26T00:01:00Z','2026-10-26T00:02:00Z'],
 variables:{[q]:[1000,2000,9999],[doKey]:[1.5,2.5,9],effluent:[5,6]}};
test('charts show only processed input points with the output timestamps and no double scaling',()=>{
 const result=simulationInputSeries(series,[q,doKey]);
 assert.deepEqual(result.time_h,series.time_h);
 assert.deepEqual(result.sensor_timestamps,series.sensor_timestamps);
 assert.deepEqual(result.variables,{[q]:[1000,2000],[doKey]:[1.5,2.5]});
});
test('new completed intervals extend both input charts while saved results remain usable',()=>{
 const next={...series,time_h:[...series.time_h,3/60],sensor_timestamps:[...series.sensor_timestamps,'2026-10-26T00:03:00Z']};
 assert.equal(simulationInputSeries(next,[q]).variables[q].length,3);
 assert.equal(simulationInputSeries(series,[q]).variables[q].length,2);
 assert.deepEqual(simulationInputSeries(JSON.parse(JSON.stringify(series)),[doKey]).variables[doKey],[1.5,2.5]);
});
test('no result stays empty; absent timestamps and missing data do not become current readings or zero',()=>{
 assert.deepEqual(simulationInputSeries(undefined,[q]).time_h,[]);
 const result=simulationInputSeries({time_h:[0,1],variables:{[q]:[NaN,1]}},[q,doKey]);
 assert.deepEqual(result.sensor_timestamps,[null,null]);
 assert.deepEqual(result.variables,{[q]:[null,1],[doKey]:[null,null]});
});
