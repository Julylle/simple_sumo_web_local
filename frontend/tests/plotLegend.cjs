const {test}=require('node:test');
const assert=require('node:assert/strict');
// Run with Node 22.18+ (native TypeScript type stripping).
function load(name){return require('../src/utils/'+name+'.ts');}
const {plotLegend}=load('plotLegend');
test('more legend rows reserve more space; narrow cards wrap long labels',()=>{
 const labels=Array.from({length:30},(_,i)=>`Influent Ammonia_sensor_Horiba ${i} (mg/L) [right]`);
 const wide=plotLegend(labels,1400,75),narrow=plotLegend(labels,430,75);
 assert.ok(narrow.height>wide.height);
 assert.ok(narrow.names.every(n=>n.includes('<br>')));
 assert.equal(narrow.names.length,labels.length);
 assert.ok(plotLegend(labels.slice(0,2),1400,75).height<wide.height);
});
test('legend layout remains finite before container width is measured',()=>{
 const layout=plotLegend(['Long variable name (mg/L)'],0,75);
 assert.ok(Number.isFinite(layout.height));assert.ok(layout.cellWidth>0);
});
test('UTC acquisition time is converted into browser local wall-clock fields',()=>{
 process.env.TZ='Australia/Brisbane';
 const {localPlotTimestamp}=load('liveSensorDisplay');
 assert.equal(localPlotTimestamp(Date.parse('2026-10-25T01:05:00+00:00')),'2026-10-25 11:05:00.000');
});
