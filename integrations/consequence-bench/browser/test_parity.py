import json
import random
import string
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "python"))
from app import run_check  # noqa: E402 - explicit sibling reference source

random.seed(1411)
tools = (
    [""]
    + [f"deny_{i}" for i in range(20)]
    + ["read", "deny_20", "deny_00", "DENY_0", "x" * 40, "_", "-"]
)
# Every boolean combination and all 20 forbidden names; representatives of the
# infinite allowed-name equivalence class, plus seeded random valid strings.
cases = [
    dict(second_tool=t, unknown=u, missing_hash=m)
    for t in tools
    for u in (False, True)
    for m in (False, True)
]
for _ in range(60):
    cases.append(
        dict(
            second_tool="".join(
                random.choices(string.ascii_letters + string.digits + "_-", k=random.randint(0, 40))
            ),
            unknown=random.choice([False, True]),
            missing_hash=random.choice([False, True]),
        )
    )
expected = []
for d in cases:
    es = []
    run_check(d, es.append)
    e = es[-1]
    expected.append({k: e[k] for k in ("exit_code", "result", "score")})
js = """const {webcrypto}=require('node:crypto');
globalThis.crypto=webcrypto;
const p=require('./dist/engine.js');
let s='';
process.stdin.on('data',x=>s+=x);
process.stdin.on('end',async()=>{
console.log(JSON.stringify(await Promise.all(JSON.parse(s).map(p.evaluate))))});
"""
r = subprocess.run(
    ["node", "-e", js],
    input=json.dumps(cases),
    text=True,
    capture_output=True,
    cwd=ROOT,
    check=True,
)
actual = json.loads(r.stdout)
for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
    assert a == e, (i, cases[i], a, e)
report = {
    "cases": len(cases),
    "comparison": (
        "exact result (verdict/ok/details), score (all metrics/policy/fingerprint), exit code"
    ),
    "passed": True,
    "scope": (
        "All boolean combinations, every forbidden name, boundary/equivalence "
        "representatives and 60 seeded valid names. Not exhaustive over all strings "
        "or arbitrary checker input. Event IDs, timestamps, baseline-byte hashes "
        "intentionally not compared."
    ),
}
(ROOT / "parity-result.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
