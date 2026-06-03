const fs = require('fs');
const code = fs.readFileSync('frontend/js/dashboard.js','utf8');
const lines = code.split(/\r?\n/);
const startLine = 6450;
const endLine = 6552;
let text = lines.slice(startLine-1, endLine).join('\n');
let state='normal';
let stack=[];
let line= startLine;
let col=0;
for (let i=0;i<text.length;i++){
  let ch=text[i];
  if(ch=='\n'){line++;col=0;continue;} else col++;
  if(state==='line_comment'){ if(ch==='\n'){state='normal';} continue; }
  if(state==='block_comment'){ if(ch==='*' && text[i+1]=='/'){ state='normal'; i++; col++; } continue; }
  if(state==='single'){
    if(ch==='\\'){ i++; col++; continue; }
    if(ch==="'"){ state='normal'; }
    continue;
  }
  if(state==='double'){
    if(ch==='\\'){ i++; col++; continue; }
    if(ch==='"'){ state='normal'; }
    continue;
  }
  if(state==='template'){
    if(ch==='\\'){ i++; col++; continue; }
    if(ch==='`'){ state='normal'; stack.pop(); continue; }
    if(ch==='${'){/* impossible */}
    if(ch==='\$' && text[i+1]==='{'){ stack.push('${'); i++; col++; continue; }
    if(ch==='}' && stack[stack.length-1]==='${'){ stack.pop(); continue; }
    continue;
  }
  if(ch==='/' && text[i+1]=='/'){ state='line_comment'; i++; col++; continue; }
  if(ch==='/' && text[i+1]=='*'){ state='block_comment'; i++; col++; continue; }
  if(ch==="'"){ state='single'; continue; }
  if(ch==='"'){ state='double'; continue; }
  if(ch==='`'){ state='template'; stack.push('`'); continue; }
  if(ch==='('||ch==='{'||ch==='['){ stack.push(ch); continue; }
  if(ch===')'){ if(stack.pop()!=='('){ console.log('mismatch ) at', line, col); break;} continue; }
  if(ch==='}'){ if(stack.length && stack[stack.length-1]==='${'){ stack.pop(); continue;} if(stack.pop()!=='{'){ console.log('mismatch } at', line, col); break;} continue; }
  if(ch===']'){ if(stack.pop()!=='['){ console.log('mismatch ] at', line, col); break;} continue; }
}
console.log('stack after segment', stack);
