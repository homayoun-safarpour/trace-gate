const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ids=['tool','unknown','missing','controls','timeline','run','result','json','current','explain','identity','pin','export','pins','comparison'];
const nodes=Object.fromEntries(ids.map(id=>[id,{value:id==='tool'?'deny_0':'',checked:false,textContent:'',dataset:{},disabled:false,listeners:{},children:[],addEventListener(k,f){this.listeners[k]=f},replaceChildren(){this.children=[]},append(x){this.children.push(x)}}]));
const samples=JSON.parse(fs.readFileSync('real-check-evidence.json'));let mode='good',resolve,downloads=0;
const context={document:{getElementById:id=>nodes[id],createElement:()=>({textContent:'',click(){downloads++}})},TextDecoder,JSON,Date,Error,Receipt:require('./static/receipt.js'),Blob,URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){}},setTimeout(fn){fn()},
fetch:async()=>{if(mode==='refuse')return {ok:false,status:429};const rows=samples[nodes.tool.value==='read'?1:0];return {ok:true,body:{getReader(){let n=0;return {async read(){if(mode==='pending')await new Promise(r=>resolve=r);n++;return n===1?{value:Buffer.from(rows.map(x=>JSON.stringify(x)).join('\n')+'\n'),done:false}:{done:true};}};}}};}};
vm.runInNewContext(fs.readFileSync('static/app.js','utf8'),context);
const submit=()=>nodes.controls.listeners.submit({preventDefault(){}});
(async()=>{await submit();assert.equal(nodes.result.textContent,'POLICY_VIOLATION');assert.equal(nodes.pin.disabled,false);nodes.pin.listeners.click();assert(nodes.pins.textContent.includes('deny_0'));nodes.export.listeners.click();assert.equal(downloads,1);
nodes.tool.value='read';nodes.tool.listeners.input();assert(nodes.pin.disabled);assert(nodes.export.disabled);assert.equal(nodes.result.dataset.ok,undefined);nodes.export.listeners.click();assert.equal(downloads,1);
await submit();nodes.pin.listeners.click();assert(nodes.comparison.textContent.includes('POLICY_VIOLATION → PASS'));assert(nodes.comparison.textContent.includes('second_tool'));
mode='refuse';await submit();assert.equal(nodes.result.textContent,'NOT VERIFIED');assert(nodes.export.disabled);
mode='pending';const p=submit();await new Promise(r=>setImmediate(r));nodes.tool.listeners.input();mode='good';resolve();await p;assert.equal(nodes.result.textContent,'INPUT CHANGED · RUN AGAIN');assert(nodes.export.disabled);
console.log('14 mock-DOM UI assertions passed; not browser verification');})();
