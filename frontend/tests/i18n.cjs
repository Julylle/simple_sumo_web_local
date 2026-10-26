const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');

function translationApp(initial='en') {
  const storage=new Map([['model-platform-language',initial]]);
  const context=vm.createContext({
    document:{documentElement:{lang:''},title:''},
    localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    useSyncExternalStore:(_subscribe,getSnapshot)=>getSnapshot(),
  });
  for(const file of ['zh.ts','i18n.ts']) {
    let code=stripTypeScriptTypes(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'));
    code=code.replace(/^import .*;\s*$/gm,'').replace(/\bexport /g,'');
    vm.runInContext(code,context);
  }
  return {context,storage,t:v=>context.t(v),setLanguage:v=>context.setLanguage(v)};
}

test('Chinese covers realtime setup, recovery, diagnostics and plot copy; English restores exactly',()=>{
  const app=translationApp();
  const samples={
    'Resume a saved simulation':'恢复已保存的模拟',
    'Historical data → Live':'历史数据 → 实时模拟',
    'Connect':'连接',
    'DO concentrations · simulation inputs':'DO 浓度 · 模型实际输入',
    'waiting_for_boundary':'等待模拟区间完成',
    'Reset axes':'重置坐标轴',
    'Plant-wide model testing':'全厂模型测试',
    'Auto-Calibration':'自动校准',
  };
  app.setLanguage('zh');
  for(const [en,zh] of Object.entries(samples))assert.equal(app.t(en),zh);
  assert.equal(app.context.document.documentElement.lang,'zh-CN');
  assert.equal(app.storage.get('model-platform-language'),'zh');
  app.setLanguage('en');
  for(const en of Object.keys(samples))assert.equal(app.t(en),en);
});

test('dynamic messages translate without changing database names, numeric values or identifiers',()=>{
  const app=translationApp('zh');
  assert.equal(app.t('Error: Sensor comparisons from sumo_web_database unavailable. MySQL login denied.'),
    '错误：无法从 sumo_web_database 读取传感器对比数据。MySQL 登录被拒绝。');
  assert.equal(app.t(' · 12 loaded intervals remaining'),' · 剩余 12 个已加载区间');
  assert.equal(app.t('CSTR3_4 nitrate · sensor'),'CSTR3_4 硝酸盐 · 传感器');
  assert.equal(app.t('5.0 min'),'5.0 分钟');
  for(const value of ['Sumo__Plant__CSTR3_4__SNOx','sumo_web_database','ns=2;s=GEeth.PLC147.II_tank3_DO1','mg/L',12.5,null])assert.equal(app.t(value),value);
  const node={value:1};assert.equal(app.t(node),node);
});

test('all static translated UI phrases have Chinese entries or are intentional technical labels',()=>{
  const app=translationApp('zh');
  const technical=new Set(['TwoDays_Subiaco_DynamicCali_20260401.xlsx','validation','dyinput','t (min)',
    'NH4-N','NO3-N','NO2-N','N2O-N','mg/L','Language / 语言','English','← MLR ·','× Q',
    'ns=2;s=...','SUMO:','S','SUMO','Python ASM','']);
  const root=path.join(__dirname,'../src');
  for(const file of ['App.tsx',...fs.readdirSync(path.join(root,'components')).filter(f=>f.endsWith('.tsx')).map(f=>'components/'+f)]){
    const source=fs.readFileSync(path.join(root,file),'utf8');
    for(const match of source.matchAll(/\bt\(("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\)/g)){
      const text=vm.runInNewContext(match[1]).trim().replace(/\s+/g,' ');
      if(!/[A-Za-z]/.test(text)||technical.has(text))continue;
      assert.notEqual(app.t(text),text,`${file}: missing translation for ${text}`);
    }
  }
});
