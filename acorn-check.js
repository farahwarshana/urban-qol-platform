const fs = require('fs');
const acorn = require('acorn');
const code = fs.readFileSync('frontend/js/dashboard.js','utf8');
try {
  acorn.parse(code, {ecmaVersion:'latest', sourceType:'script'});
  console.log('PARSE_OK');
} catch (e) {
  console.log('ERROR', e.loc.line, e.loc.column, e.message);
}
