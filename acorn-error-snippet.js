const fs = require('fs');
const acorn = require('acorn');
const code = fs.readFileSync('frontend/js/dashboard.js','utf8');
try {
  acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  console.log('PARSE_OK');
} catch (e) {
  console.log('ERROR', e.loc.line, e.loc.column, e.pos, e.message);
  const start = Math.max(0, e.pos-80);
  const end = Math.min(code.length, e.pos+80);
  console.log('SNIPPET:');
  console.log(JSON.stringify(code.slice(start,end)));
  console.log('---');
  const lines = code.slice(start,end).split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    console.log((i+1)+': '+ lines[i]);
  }
}
