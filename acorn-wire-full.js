const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 5954;
const end = 6583;
const segment = lines.slice(start-1, end).join('\n');
const code = segment;
try {
  acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  console.log('OK full wireTabSwitching segment');
} catch (e) {
  console.log('FAIL', e.loc.line, e.loc.column, e.message);
  const pos = e.pos;
  const snippetStart = Math.max(0, pos-80);
  const snippetEnd = Math.min(code.length, pos+80);
  console.log('pos', pos);
  console.log('context:', code.slice(snippetStart, snippetEnd));
}
