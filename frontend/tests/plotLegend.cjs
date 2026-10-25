const {test}=require('node:test');
const assert=require('node:assert/strict');
// Run with Node 22.18+ (native TypeScript type stripping).
function load(name){return require('../src/utils/'+name+'.ts');}
const {plotLegend}=load('plotLegend');
test('whole legend entries wrap to new rows without splitting variable names',()=>{
 const labels=Array.from({length:30},(_,i)=>`Influent Ammonia_sensor_Horiba ${i} (mg/L) [right]`);
 const wide=plotLegend(labels,1400,75),narrow=plotLegend(labels,430,75);
 assert.ok(narrow.height>wide.height);
 assert.deepEqual(narrow.names,labels);
 assert.ok(narrow.names.every(n=>!n.includes('<br>')));
 assert.ok(narrow.plotWidth>=430);
 assert.equal(narrow.names.length,labels.length);
 assert.ok(plotLegend(labels.slice(0,2),1400,75).height<wide.height);
});
test('legend layout remains finite before container width is measured',()=>{
 const layout=plotLegend(['Long variable name (mg/L)'],0,75);
 assert.ok(Number.isFinite(layout.height));assert.ok(layout.plotWidth>0);
});
test('UTC acquisition time is converted into browser local wall-clock fields',()=>{
 process.env.TZ='Australia/Brisbane';
 const {localPlotTimestamp}=load('liveSensorDisplay');
 assert.equal(localPlotTimestamp(Date.parse('2026-10-25T01:05:00+00:00')),'2026-10-25 11:05:00.000');
});

test('short entries pack tightly while an oversized label expands the scrollable canvas',()=>{
 const compact=plotLegend(['a','b','c','d'],600,75,()=>20);
 assert.equal(compact.height,35);
 const label='a very long variable name';
 const long=plotLegend([label],320,75,()=>700);
 assert.deepEqual(long.names,[label]);
 assert.equal(long.plotWidth,902);
 assert.equal(long.height,35);
});
