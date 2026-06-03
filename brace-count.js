const fs = require('fs');
const source = fs.readFileSync('frontend/js/dashboard.js','utf8');
const lines = source.split(/\r?\n/);
const startLine = 5954;
const endLine = 6578;
const text = lines.slice(startLine-1, endLine).join('\n');
let state = 'normal';
let quote = null;
let paren = 0, brace = 0, brack = 0;
let line = startLine;
for (let i = 0; i < text.length; i++) {
  const ch = text[i];
  const next = text[i+1];
  if (ch === '\n') { line++; continue; }
  if (state === 'normal') {
    if (ch === '/' && next === '/') { state = 'line'; i++; continue; }
    if (ch === '/' && next === '*') { state = 'block'; i++; continue; }
    if (ch === '"' || ch === "'") { state='string'; quote=ch; continue; }
    if (ch === '`') { state='template'; continue; }
    if (ch === '(') paren++;
    if (ch === ')') paren--;
    if (ch === '{') brace++;
    if (ch === '}') brace--;
    if (ch === '[') brack++;
    if (ch === ']') brack--;
  } else if (state === 'line') {
    if (ch === '\n') state='normal';
  } else if (state === 'block') {
    if (ch === '*' && next === '/') { state='normal'; i++; continue; }
  } else if (state === 'string') {
    if (ch === '\\') { i++; continue; }
    if (ch === quote) { state='normal'; quote=null; continue; }
  } else if (state === 'template') {
    if (ch === '\\') { i++; continue; }
    if (ch === '`') { state='normal'; continue; }
    if (ch === '$' && next === '{') { brace++; i++; continue; }
  }
  if (paren < 0 || brace < 0 || brack < 0) {
    console.log('NEGATIVE at', line, 'ch', ch, 'paren', paren, 'brace', brace, 'brack', brack, 'state', state);
    break;
  }
  if (line === 6576 || line === 6577 || line === 6578) {
    console.log('at line', line, 'paren', paren, 'brace', brace, 'brack', brack, 'state', state);
  }
}
console.log('final line', line, 'paren', paren, 'brace', brace, 'brack', brack, 'state', state);
