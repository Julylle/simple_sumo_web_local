const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
const source = readFileSync(join(__dirname, '../src/components/RealTimeSumo.tsx'), 'utf8');
// Exercise the actual async Connect handler with transport and React setters mocked.
const handler = source.slice(source.indexOf('  async function refresh(){'), source.indexOf('  async function uploadModel(){'));
async function check(mode) {
  const events = [];
  const mapping = {flow: 'ns=2;s=flow'};
  const state = {connected:false, connecting:false};
  let resolve;
  const response = new Promise(r=>resolve=r);
  const context = {
    mapping, mappingRef:{current:mapping}, selectedMappings:m=>m,
    json:()=>response, flushSync:fn=>{fn();events.push('commit');},
    setConnected:v=>{state.connected=v;}, setConnecting:v=>{state.connecting=v;},
    setSensorError:v=>{state.error=v;},
    setBusy:()=>{}, setError:()=>{}, setRun:()=>{}, setMapping:()=>{},
    setReadings:()=>events.push('readings'), setHistory:()=>events.push('history'),
  };
  vm.createContext(context);
  vm.runInContext(stripTypeScriptTypes(handler+'\nthis.refresh=refresh;'),context);
  const pending=context.refresh();
  assert.equal(state.connecting,true);
  assert.equal(state.connected,false);
  if(mode==='changed')context.mappingRef.current={flow:'ns=2;s=other'};
  resolve({readings:mode==='incomplete'?[]:[{column:'flow',node_id:'ns=2;s=flow',value:10}]});
  await pending;
  assert.equal(state.connecting,false);
  assert.equal(state.connected,mode==='success');
  if(mode==='success')assert.deepEqual(events,['commit','readings','history']);
  else {assert.ok(state.error);assert.deepEqual(events,[]);}
}
(async()=>{for(const mode of ['success','incomplete','changed'])await check(mode);console.log('3 Connect handler checks passed');})().catch(e=>{console.error(e);process.exitCode=1;});
