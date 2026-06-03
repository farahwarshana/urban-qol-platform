const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
const end = 6463;
const segment = lines.slice(start-1, end).join('\n');
const code = 'async function f() {\n' + segment + '\n}';
try {
  acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  console.log('OK this exact segment');
} catch (e) {
  console.log('FAIL', e.loc.line, e.loc.column, e.message);
}
