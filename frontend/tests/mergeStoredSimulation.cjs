const {test}=require('node:test');
const assert=require('node:assert/strict');
const {mergeStoredSimulation}=require('../src/utils/mergeStoredSimulation.ts');
test('database history joins live samples with UTC deduplication and live priority',()=>{
 const key='Sumo__Plant__CSTR3_4__SNOx';
 const stored={[key]:{timestamps:['2026-10-26T08:00:00Z','2026-10-26T08:01:00Z'],values:[0,2]}};
 const live={time_h:[0,1,2],sensor_timestamps:['2026-10-26T16:00:00+08:00','2026-10-26T16:01:00+08:00','2026-10-26T08:02:00Z'],variables:{[key]:[null,3,4]}};
 const series=mergeStoredSimulation(stored,live)[key];
 assert.deepEqual(series.values,[0,3,4]);
 assert.equal(series.timestamps.length,3);
 assert.equal(series.timestamps[2],'2026-10-26T08:02:00.000Z');
 assert.deepEqual(stored[key].values,[0,2]);
});
test('without database data normal live plotting remains available',()=>{
 assert.deepEqual(mergeStoredSimulation(undefined,{time_h:[],variables:{}}),{});
});
