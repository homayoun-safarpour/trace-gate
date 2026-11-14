'use strict';
const $=id=>document.getElementById(id);let events=[],version=0,currentReceipt=null,pinned=[];
function invalidate(){currentReceipt=null;$('pin').disabled=true;$('export').disabled=true;delete $('result').dataset.ok;}
function changed(){version++;invalidate();$('result').textContent='INPUT CHANGED · RUN AGAIN';$('explain').textContent='Previous evidence does not describe these edits.';$('current').textContent='read'+($('tool').value?' → '+$('tool').value:'');}
for(const id of ['tool','unknown','missing'])$(id).addEventListener('input',changed);
$('controls').addEventListener('submit',async e=>{
 e.preventDefault();const v=version;const submitted={second_tool:$('tool').value,unknown:$('unknown').checked,missing_hash:$('missing').checked};invalidate();events=[];$('timeline').replaceChildren();$('run').disabled=true;$('result').textContent='REQUESTING';$('json').textContent='[]';
 const labels={accepted:'Request accepted',baseline_started:'Freezing baseline',baseline_completed:'Baseline frozen',check_started:'Checker started',completed:'Checker completed',error:'Check failed'};
 function accept(x){events.push(x);$('json').textContent=JSON.stringify(events,null,2);const li=document.createElement('li');li.textContent=(labels[x.event]||x.event)+(x.at_ns?' · '+new Date(x.at_ns/1e6).toLocaleTimeString():'');$('timeline').append(li);if(x.run_id)$('identity').textContent='Run '+x.run_id;
 
 if(x.event==='error'&&v===version)$('result').textContent='ERROR · NO VERIFIED RESULT';}
 try{await FixturePort.run(submitted,accept);const receipt=Receipt.seal(events,submitted);if(v===version){currentReceipt=receipt;const end=receipt.events.at(-1);$('result').textContent=end.result.verdict;$('result').dataset.ok=String(end.result.ok);$('explain').textContent='Fresh browser-port check, reference exit code '+end.exit_code+'. Composite '+end.score.composite+'. Policy violations are not waived by the average.';$('pin').disabled=false;$('export').disabled=false;}}
 catch(err){if(v===version){invalidate();$('result').textContent='NOT VERIFIED';$('explain').textContent=err.message;}}
 finally{$('run').disabled=false;}
});

$('pin').addEventListener('click',()=>{
 if(!currentReceipt)return;
 if(pinned.some(r=>r.run_id===currentReceipt.run_id))return;
 pinned.push(currentReceipt);pinned=pinned.slice(-2);
 $('pins').textContent=pinned.map((r,i)=>(i?'B':'A')+' · '+r.run_id+' · '+JSON.stringify(r.input)).join('\n');
 if(pinned.length===2){const c=Receipt.compare(...pinned);$('comparison').textContent=c.verdict_before+' → '+c.verdict_after+'\nComposite: '+c.composite_before+' → '+c.composite_after+'\nChanged inputs: '+JSON.stringify(c.changes,null,2)+'\n'+c.interpretation;}
 $('pin').disabled=true;
});
$('export').addEventListener('click',()=>{
 if(!currentReceipt)return;
 const blob=new Blob([JSON.stringify(currentReceipt,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='trace-gate-'+currentReceipt.run_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
