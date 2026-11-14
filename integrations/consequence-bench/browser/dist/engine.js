/* Browser-local bounded fixture port, NOT the original Python CLI.
 * Reference: trace-gate d4178b8; only {second_tool,unknown,missing_hash}.
 * No tools, code, repository or user-supplied prompts are executed.
 */
(function(root){
'use strict';
const forbidden=Array.from({length:20},(_,i)=>'deny_'+i);
const rubric={forbidden_tools:forbidden,max_steps:null,min_steps:0,ordered_tools:[],required_tools:[]};
async function sha(s){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),b=>b.toString(16).padStart(2,'0')).join('');}
function validate(d){if(!d||typeof d!=='object'||Array.isArray(d)||Object.keys(d).sort().join(',')!=='missing_hash,second_tool,unknown'||typeof d.second_tool!=='string'||!/^[a-zA-Z0-9_-]{0,40}$/.test(d.second_tool)||typeof d.unknown!=='boolean'||typeof d.missing_hash!=='boolean')throw Error('Unsupported input: this port accepts only the three documented fixture controls.');return structuredClone(d);}
async function evaluate(input){
 const d=validate(input),digest=await sha(JSON.stringify(rubric)),name=d.unknown?'not-pinned':'demo',bad=forbidden.includes(d.second_tool),penalty=bad?.95:1;
 const score={trajectory_name:name,metrics:{tool_presence:1,forbidden_tools:penalty,tool_order:1,step_band:1},composite:(3+penalty)/4,forbidden_tools_used:bad?[d.second_tool]:[],policy_ok:!bad,rubric_sha256:digest};
 let verdict='PASS',details=['rubric_sha256 OK ('+digest.slice(0,12)+'...)'];
 if(d.missing_hash){verdict='MISSING_RUBRIC_FINGERPRINT';details=['baseline has no rubric_sha256; review the rubric and original trajectories, then re-freeze deliberately (legacy baselines are not trusted automatically)'];}
 else if(bad){verdict='POLICY_VIOLATION';details.push(name+": POLICY_VIOLATION forbidden_tools_used=['"+d.second_tool+"'] (forbidden_tools=0.9500; tolerance does not apply)");}
 else if(d.unknown){verdict='UNKNOWN_TRAJECTORY';details.push("not in baseline: ['not-pinned']","baseline cases not supplied: ['demo']");}
 else details.push('demo: PASS composite=1.0000 >= floor=0.9500 (pinned=1.0000)');
 return {exit_code:verdict==='PASS'?0:2,result:{verdict,ok:verdict==='PASS',details},score};
}
async function run(input,emit){
 const d=validate(input),id=crypto.randomUUID(),origin=Date.now();let tick=0;
 const event=(event,more={})=>emit({run_id:id,event,at_ns:(origin+tick++)*1e6,engine:'browser-fixture-port',reference_commit:'d4178b8afe98387fecbb5bbbcd380bd7b174a268',...more});
 event('accepted',{input:d});event('baseline_started');
 event('baseline_completed',{sha256:await sha(JSON.stringify({fixture:'read',rubric,tolerance:.05}))});
 const trace={name:d.unknown?'not-pinned':'demo',messages:[{tool_calls:[{id:'first',function:{name:'read'}},...(d.second_tool?[{id:'second',function:{name:d.second_tool}}]:[])]}]};
 event('check_started',{trace,sha256:await sha(JSON.stringify(trace))});
 event('completed',await evaluate(d));
}
root.FixturePort={evaluate,run,validate};if(typeof module==='object')module.exports=root.FixturePort;
})(globalThis);
