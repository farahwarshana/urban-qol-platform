const fs = require('fs');
const acorn = require('acorn');
const source = fs.readFileSync('frontend/js/dashboard.js','utf8');
const startMarker = 'gridTabContent.innerHTML = `';
const start = source.indexOf(startMarker);
if (start === -1) { console.error('start marker not found'); process.exit(1); }
let i = start + startMarker.length;
let depth = 1;
let state = 'template';
let braceDepth = 0;
for (; i < source.length; i++) {
  const ch = source[i];
  const next = source[i+1];
  if (state === 'template') {
    if (ch === '\\') { i++; continue; }
    if (ch === '$' && next === '{') { state = 'template_expr'; braceDepth = 0; i++; continue; }
    if (ch === '`') { depth--; i++; break; }
    continue;
  }
  if (state === 'template_expr') {
    if (ch === '\\') { i++; continue; }
    if (ch === '"' || ch === "'") {
      const quote = ch;
      i++;
      while (i < source.length) {
        if (source[i] === '\\') { i += 2; continue; }
        if (source[i] === quote) break;
        i++;
      }
      continue;
    }
    if (ch === '`') {
      state = 'template';
      continue;
    }
    if (ch === '{') braceDepth++;
    if (ch === '}') {
      if (braceDepth === 0) { state = 'template'; continue; }
      braceDepth--;
    }
    continue;
  }
}
const end = i;
if (end >= source.length) {
  console.error('no closing backtick found');
  process.exit(1);
}
const template = source.slice(start, end);
console.log('template length', template.length);
try {
  const parsed = acorn.parse('const _x = ' + template + ';', {ecmaVersion:'latest', sourceType:'script'});
  console.log('parsed OK');
} catch (e) {
  console.log('parse fail', e.loc.line, e.loc.column, e.message);
  const lines = template.split(/\r?\n/);
  const ctxLine = e.loc.line;
  const from = Math.max(0, ctxLine-3);
  const to = Math.min(lines.length, ctxLine+2);
  for (let li = from; li < to; li++) {
    console.log((li+1)+': '+lines[li]);
  }
}
