const fs = require('fs');
const acorn = require('acorn');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 5954;
for (let end = 5960; end <= 6578; end += 10) {
  const segment = lines.slice(start-1, end).join('\n');
  const code = 'function test() {\n' + segment + '\n}';
  try {
    acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
    console.log('OK through', end);
  } catch (e) {
    console.log('FAIL at', end, '->', e.loc ? `${e.loc.line}:${e.loc.column}` : e.message);
    break;
  }
}
