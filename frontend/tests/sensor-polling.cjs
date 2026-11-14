const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {stripTypeScriptTypes}=require('node:module');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=readFileSync(join(__dirname,'../src/components/RealTimeSumo.tsx'),'utf8');
const start=source.indexOf('    if(!connected||!statusReady)return;');
const end=source.indexOf('  },[connected,statusReady]);',start);
async function test(fail){
  let finish, calls=0;
  const timers=new Map();let id=0;
  const ctx={connected:true,statusReady:true,pollingRef:{current:false},mappingRef:{current:{Q:'tag'}},
    selectedMappings:m=>m,json:()=>{calls++;return new Promise((resolve,reject)=>{finish=()=>fail?reject(new Error('offline')):resolve({readings:[]});});},
    setTimeout:(cb,delay)=>{assert.equal(delay,5000);timers.set(++id,cb);return id;},clearTimeout:n=>timers.delete(n),
    setReadings:()=>{},setHistory:()=>{},setSensorError:()=>{}};
  vm.createContext(ctx);
  vm.runInContext(stripTypeScriptTypes('this.cleanup=(()=>{'+source.slice(start,end)+'})();'),ctx);
  assert.equal(calls,1);assert.equal(timers.size,0,'No timer while a read is pending');
  finish();await new Promise(r=>setImmediate(r));
  assert.equal(timers.size,1,'Schedule only after success or failure');
  const next=[...timers.values()][0];timers.clear();next();assert.equal(calls,2);
  ctx.cleanup();finish();await new Promise(r=>setImmediate(r));
  assert.equal(timers.size,0,'Unmount/disconnect must not restart polling');
}
(async()=>{await test(false);await test(true);console.log('2 polling lifecycle checks passed');})().catch(e=>{console.error(e);process.exitCode=1;});
