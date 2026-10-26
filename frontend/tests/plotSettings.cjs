const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readPlotSetting, writePlotSetting, validChoices, validCards, validViewport, stringList} = require('../src/utils/plotSettings.ts');

function storage() {
  const entries = new Map();
  global.localStorage = {getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value)};
  return entries;
}
test('fresh reads restore choices, hidden traces, custom cards and all zoom axes', () => {
  storage();
  const choices = {selection: ['Q','TCOD'], secondary: true, right: ['Q']};
  const viewport = {xaxis: ['2026-10-26 09:00', '2026-10-26 10:00'], yaxis: [0,20], yaxis2: [100,200]};
  for (const [key, value, fallback, valid] of [
    ['live:influent:choices', choices, null, validChoices],
    ['live:influent:viewport:date', viewport, {}, validViewport],
    ['live:influent:hidden', ['TCOD'], [], stringList],
    ['live:outputs:cards', {ids: [1,3], nextId: 4}, {ids: [], nextId: 1}, validCards],
  ]) {
    writePlotSetting(key, value);
    assert.deepEqual(readPlotSetting(key, fallback, valid), value);
  }
  // Selecting no variables is an explicit preference, not "select all".
  writePlotSetting('empty', {...choices, selection: []});
  assert.deepEqual(readPlotSetting('empty', null, validChoices).selection, []);
});
test('chart identities and local-time versus elapsed-time axes stay separate; reset survives reload', () => {
  storage();
  writePlotSetting('live:comparison:1:viewport:date', {xaxis: [1,2]});
  for (const key of ['offline:comparison:1:viewport:date', 'live:comparison:2:viewport:date', 'live:comparison:1:viewport:linear']) {
    assert.deepEqual(readPlotSetting(key, {}, validViewport), {});
  }
  writePlotSetting('live:comparison:1:viewport:date', {});
  assert.deepEqual(readPlotSetting('live:comparison:1:viewport:date', null, validViewport), {});
});
test('damaged or outdated storage falls back without overwriting saved data during load', () => {
  const entries = storage();
  const fallback = {selection: null, secondary: false, right: []};
  for (const raw of ['{', 'null', '{}', '{"selection":[4],"secondary":true,"right":[]}']) {
    entries.set('sumo-plots:v1:choices', raw);
    assert.deepEqual(readPlotSetting('choices', fallback, validChoices), fallback);
    assert.equal(entries.get('sumo-plots:v1:choices'), raw);
  }
  assert.equal(validCards({ids: [1,1], nextId: 2}), false);
  assert.equal(validCards({ids: [3], nextId: 3}), false);
  assert.equal(validViewport({yaxis: [null, 2]}), false);
});
test('unavailable browser storage never interrupts plot updates', () => {
  global.localStorage = {getItem() {throw Error('denied')}, setItem() {throw Error('quota')}};
  assert.deepEqual(readPlotSetting('choices', [], stringList), []);
  assert.doesNotThrow(() => writePlotSetting('choices', ['Q']));
  delete global.localStorage;
  assert.deepEqual(readPlotSetting('choices', [], stringList), []);
});
