const fs = require('fs'), vm = require('vm'), assert = require('assert');
const code = fs.readFileSync(__dirname+'/../UiSafe.js','utf8').replace(/^\.pragma library\s*/, '');
const ui = {}; vm.createContext(ui); vm.runInContext(code,ui);
for (const input of ['<img src="https://invalid/x">','&lt;img src=x&gt;','<svg/onload=bad>','A\nB']) {
  assert(!/[<>&\x00-\x1f]/.test(ui.plain(input)));
}
assert.equal(ui.validLink('javascript:alert(1)','fr24'),false);
assert.equal(ui.validLink('file:///etc/passwd','adsbx'),false);
assert.equal(ui.validLink('https://www.flightradar24.com.evil.invalid/data/aircraft/a','fr24'),false);
assert(ui.validLink('https://www.flightradar24.com/data/aircraft/n123ab','fr24'));
assert(ui.validLink('https://globe.adsbexchange.com/?icao=abc123','adsbx'));
assert(!ui.validLink('https://globe.adsbexchange.com/?icao=abc123&other=bad','adsbx'));
const sample={state:'ok',generatedAt:100,nearest:{positionTime:100}};
assert(ui.current(sample,110));assert(!ui.current(sample,121));
assert(!ui.current({...sample,state:'paused'},101));
for(const file of ['PlainText.qml','BarWidget.qml','AircraftCard.qml']) {
  const s=fs.readFileSync(__dirname+'/../'+file,'utf8');
  if(file==='PlainText.qml')assert(s.includes('textFormat: Text.PlainText'));
  else assert(!/(^|\n)\s*Text\s*\{/.test(s),'Use the PlainText component for network and file data');
}
console.log('UI safety: markup, URL allowlists, stale data and plain-text sinks passed');

for (const value of [1,2,70,100]) assert.equal(ui.rangeMiles(value),value);
for (const value of [0,101,1.5,null,true,'1',NaN,Infinity]) assert.equal(ui.rangeMiles(value),70);
