const assert=require('assert'),fs=require('fs'),R=require('./static/receipt.js');
const raw=JSON.parse(fs.readFileSync('real-check-evidence.json'));
const a=R.seal(raw[0],raw[0][0].input),b=R.seal(raw[1],raw[1][0].input);
const c=R.compare(a,b);assert.equal(c.verdict_before,'POLICY_VIOLATION');assert.equal(c.verdict_after,'PASS');assert.equal(c.changes.length,1);assert.equal(c.changes[0].field,'second_tool');assert(c.composite_before>.95);
assert.throws(()=>R.seal(raw[0].slice(0,-1),a.input));
const copy=()=>JSON.parse(JSON.stringify(raw[0]));let x=copy();x[2].run_id='wrong';assert.throws(()=>R.seal(x,a.input));
x=copy();x[3].at_ns=0;assert.throws(()=>R.seal(x,a.input));
assert.throws(()=>R.seal(raw[0],b.input));
x=copy();x[4].score.composite=null;assert.throws(()=>R.seal(x,a.input));
assert(R.compare(a,a).interpretation.includes('repeatability'));
const multi=JSON.parse(JSON.stringify(b));multi.input.unknown=true;assert(R.compare(a,multi).interpretation.includes('Multiple'));
x=copy();const sealed=R.seal(x,a.input);x[0].input.second_tool='mutated';assert.equal(sealed.input.second_tool,'deny_0');
console.log('13 receipt/comparison assertions passed using two real checker runs');
let contradictions=0;
for(const verdict of ['PASS','POLICY_VIOLATION','UNKNOWN_TRAJECTORY','MISSING_RUBRIC_FINGERPRINT']){
 for(const ok of [false,true])for(const exit_code of [0,2]){
  const e=copy();Object.assign(e.at(-1).result,{verdict,ok});e.at(-1).exit_code=exit_code;
  const consistent=ok===(verdict==='PASS')&&exit_code===(ok?0:2);
  if(consistent)R.seal(e,a.input);else {assert.throws(()=>R.seal(e,a.input),/Contradictory/);contradictions++;}
 }
}
x=copy();x.at(-1).result.verdict='UNRECOGNIZED';assert.throws(()=>R.seal(x,a.input),/Unknown/);
for(const composite of [-.1,1.1]){x=copy();x.at(-1).score.composite=composite;assert.throws(()=>R.seal(x,a.input),/range/);}
console.log(contradictions+' contradictory triples rejected, 4 consistent triples accepted, unknown verdict and 2 invalid ranges rejected');
