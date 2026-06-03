const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
for (let mid = 6460; mid <= 6520; mid += 2) {
  const segment = lines.slice(start-1, mid).join('\n');
  const code = 'async function f() {\n' + segment + '\n}';
  try {
    acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
    console.log('OK through', mid);
  } catch (e) {
    console.log('FAIL through', mid, '->', e.loc.line, e.loc.column, e.message);
    break;
  }
}
