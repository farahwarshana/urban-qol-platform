const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
const end = 6551;
const segment = lines.slice(5954-1, start-1).concat(['          gridTabContent.innerHTML = "REPLACED";']).concat(lines.slice(end)).join('\n');
try {
  acorn.parse(segment, {ecmaVersion:'latest', sourceType:'script'});
  console.log('OK with placeholder replacement');
} catch (e) {
  console.log('FAIL', e.loc.line, e.loc.column, e.message);
}
