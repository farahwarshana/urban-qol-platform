const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
for (let mid = 6463; mid <= 6552; mid++) {
  const segment = lines.slice(start-1, mid).join('\n');
  const code = 'async function f() {\n' + segment + '\n}';
  try {
    acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  } catch (e) {
    console.log('FAIL through', mid, '->', e.loc.line, e.loc.column, e.message);
    break;
  }
}
console.log('done');
