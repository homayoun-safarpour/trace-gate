'use strict';
(function(root){
const stages=['accepted','baseline_started','baseline_completed','check_started','completed'];
function seal(events,input){
 if(events.length!==stages.length||events.some((e,i)=>e.event!==stages[i]))throw Error('Incomplete or unexpected event sequence');
 const id=events[0].run_id;if(!id||events.some(e=>e.run_id!==id))throw Error('Mixed run identities');
 if(events.some((e,i)=>!Number.isFinite(e.at_ns)||(i&&e.at_ns<events[i-1].at_ns)))throw Error('Invalid event ordering');
 const accepted=events[0].input;
 if(!accepted||Object.keys(input).some(k=>accepted[k]!==input[k])||Object.keys(accepted).length!==3)throw Error('Input binding mismatch');
 const end=events.at(-1);
 if(!end.result||typeof end.result.verdict!=='string'||typeof end.result.ok!=='boolean'||!Number.isFinite(end.score?.composite)||![0,2].includes(end.exit_code))throw Error('Invalid completed checker result');
 const verdicts=new Set(['PASS','INVALID_REPORT','DUPLICATE_TRAJECTORY','POLICY_VIOLATION','INVALID_BASELINE','MISSING_BASELINE','MISSING_RUBRIC_FINGERPRINT','REPORT_RUBRIC_MISMATCH','RUBRIC_DRIFT','UNKNOWN_TRAJECTORY','MISSING_TRAJECTORY','REGRESSION']);
 if(!verdicts.has(end.result.verdict))throw Error('Unknown checker verdict');
 const passed=end.result.verdict==='PASS';
 if(end.result.ok!==passed||end.exit_code!==(passed?0:2))throw Error('Contradictory verdict, ok flag or exit code');
 if(end.score.composite<0||end.score.composite>1)throw Error('Invalid composite range');
 return JSON.parse(JSON.stringify({schema:'trace-gate-comparison-receipt/v1',scope:'Local post-run check of synthetic recorded traces; no tools executed; not a safety certificate',input,run_id:id,events}));
}
function compare(a,b){
 const changes=Object.keys(a.input).filter(k=>a.input[k]!==b.input[k]).map(k=>({field:k,before:a.input[k],after:b.input[k]}));
 const x=a.events.at(-1),y=b.events.at(-1);
 return {changes,verdict_before:x.result.verdict,verdict_after:y.result.verdict,composite_before:x.score.composite,composite_after:y.score.composite,
 interpretation:changes.length===1?'One input field changed. These two observed checks show the consequence for this synthetic fixture, not general causality.':changes.length===0?'No input fields changed. This is a repeatability observation.':'Multiple input fields changed. Do not attribute the verdict change to one field.'};
}
const api={seal,compare};if(typeof module!=='undefined')module.exports=api;root.Receipt=api;
})(globalThis);
