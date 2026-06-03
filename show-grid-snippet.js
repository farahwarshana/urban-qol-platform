const fs = require('fs');
const lines = fs.readFileSync('frontend/js/dashboard.js','utf8').split(/\r?\n/);
const start = 6450;
const end = 6465;
const segment = lines.slice(start-1, end).join('\n');
console.log('---SEGMENT LINES---');
segment.split('\n').forEach((l,i)=>console.log((start+i)+': '+l));
console.log('---END---');
