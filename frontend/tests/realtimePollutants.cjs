const {test}=require('node:test');
const assert=require('node:assert/strict');
const {pollutantOptions,realtimePollutantOptions}=require('../src/components/sumoOutputs.ts');
test('Realtime removes reactor COD/TP, retains effluent values and adds four anoxic N outputs',()=>{
 const keys=realtimePollutantOptions.map(o=>o.key);
 assert.equal(keys.some(key=>/CSTR.*__(TCOD|TP)$/.test(key)),false);
 for(const name of ['TCOD','TP'])assert.ok(keys.includes(`Sumo__Plant__Effluent1__${name}`));
 for(const tank of [3,4])for(const name of ['SNHx','SNOx'])assert.ok(keys.includes(`Sumo__Plant__CSTR${tank}_4__${name}`));
 assert.ok(pollutantOptions.some(o=>o.key==='Sumo__Plant__CSTR3_10__TCOD'));
});
test('only the two confirmed nitrate sensors are offered with simulation counterparts',()=>{
 const sensors=realtimePollutantOptions.filter(o=>o.compareTo);
 assert.equal(sensors.length,2);
 assert.deepEqual(sensors.map(o=>o.compareTo),['Sumo__Plant__CSTR3_4__SNOx','Sumo__Plant__CSTR3_10__SNOx']);
 for(const sensor of sensors)assert.ok(realtimePollutantOptions.some(o=>o.key===sensor.compareTo));
});
