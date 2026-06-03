const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
const end = 6551; // inclusive line where template literal ends
const segment = lines.slice(start-1, end).join('\n');
const code = 'async function f() {\n' + segment + '\n}';
try {
  acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  console.log('OK this exact grid segment');
} catch (e) {
  console.log('FAIL', e.loc.line, e.loc.column, e.message);
  const pos = e.pos;
  const snippetStart = Math.max(0, pos-80);
  const snippetEnd = Math.min(code.length, pos+80);
  console.log('pos', pos);
  console.log('context lines around error:');
  const ctx = code.slice(snippetStart, snippetEnd);
  console.log(ctx);
  console.log('---');
  const before = code.slice(0, pos);
  const linesBefore = before.split(/\r?\n/);
  console.log('before line count', linesBefore.length);
}
