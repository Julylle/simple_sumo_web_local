const {test}=require('node:test');
const assert=require('node:assert/strict');
const {localPlotTimestamp}=require('../src/utils/liveSensorDisplay.ts');

test('Shanghai history input, database UTC and plot timestamp describe the same interval',()=>{
 const original=process.env.TZ;
 try{
  process.env.TZ='Asia/Shanghai';
  const start=new Date('2026-01-01T08:00');
  assert.equal(start.toISOString(),'2026-01-01T00:00:00.000Z');
  const end=new Date(start.getTime()+5*60000);
  assert.equal(localPlotTimestamp(end.getTime()),'2026-01-01 08:05:00.000');
  assert.equal(localPlotTimestamp(Date.parse('2026-01-01T00:05:00.123456+00:00')),'2026-01-01 08:05:00.123');
 }finally{if(original===undefined)delete process.env.TZ;else process.env.TZ=original;}
});
test('browser local formatting respects the offset on each date, including DST',()=>{
 const original=process.env.TZ;
 try{
  process.env.TZ='Australia/Sydney';
  assert.equal(localPlotTimestamp(Date.parse('2026-01-01T00:00:00Z')),'2026-01-01 11:00:00.000');
  assert.equal(localPlotTimestamp(Date.parse('2026-07-01T00:00:00Z')),'2026-07-01 10:00:00.000');
 }finally{if(original===undefined)delete process.env.TZ;else process.env.TZ=original;}
});
