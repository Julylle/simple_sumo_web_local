// Node 22.18+ supports these erasable TypeScript helpers directly.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {updateViewport,axisViewport}=require('../src/utils/plotViewport.ts');
test('zoom in/out and pan retain date, left and secondary axis ranges',()=>{
 let state=updateViewport({}, {'xaxis.range[0]':'2026-10-26 10:00','xaxis.range[1]':'2026-10-26 11:00','yaxis.range[0]':1,'yaxis.range[1]':5,'yaxis2.range':[10,20]});
 assert.deepEqual(axisViewport(state,'xaxis'),{autorange:false,range:['2026-10-26 10:00','2026-10-26 11:00']});
 state=updateViewport(state, {'yaxis.range':[-1,8]});
 assert.deepEqual(state.yaxis,[-1,8]);
 assert.deepEqual(state.yaxis2,[10,20]);
 assert.equal(axisViewport(state,'yaxis2').autorange,false);
});
test('data refresh, resize and drag mode events never clear a selected viewport',()=>{
 const state=updateViewport({}, {'xaxis.range':[1,2],'yaxis.range':[3,4]});
 for(const event of [{},{autosize:true},{width:700,height:500},{dragmode:'pan'}])assert.strictEqual(updateViewport(state,event),state);
 const layout=axisViewport(state,'xaxis');layout.range[0]=999;
 assert.deepEqual(state.xaxis,[1,2]);
});
test('Reset restores auto-ranging; a single-axis reset leaves other axes intact',()=>{
 const state=updateViewport({}, {'xaxis.range':[1,2],'yaxis.range':[3,4]});
 const reset=updateViewport(state, {'xaxis.autorange':true});
 assert.deepEqual(axisViewport(reset,'xaxis'),{autorange:true});
 assert.deepEqual(reset.yaxis,[3,4]);
 assert.deepEqual(axisViewport({},'yaxis2'),{autorange:true});
});
test('partial updates keep the opposite bound; malformed values are ignored',()=>{
 const state=updateViewport({}, {'xaxis.range':[1,2]});
 assert.deepEqual(updateViewport(state,{'xaxis.range[0]':0}).xaxis,[0,2]);
 assert.strictEqual(updateViewport(state,{'xaxis.range':[NaN,Infinity]}),state);
});
