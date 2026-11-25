"""Record synthetic CLI results and render a compact dependency-free SVG proof.

Run after installing the reviewed package. Recorded tools are never executed.
This is a small acceptance demo, not a safety or competitor benchmark.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path


def _run(*args):
    completed = subprocess.run(
        [sys.executable, "-m", "tracegate.cli", *map(str, args)],
        text=True, capture_output=True, timeout=30, check=False,
    )
    if completed.returncode not in (0, 2) or not completed.stdout:
        raise RuntimeError(completed.stderr or "CLI did not produce a result")
    return completed.returncode, json.loads(completed.stdout)


def capture_demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="trace-gate-proof-") as temporary:
        work = Path(temporary)

        def write(name, data):
            path = work / name
            path.write_text(json.dumps(data), encoding="utf-8")
            return path

        rubric = write("rubric.json", {
            "forbidden_tools": [f"deny_{i}" for i in range(20)],
        })
        clean_data = {"name": "demo", "messages": [{"tool_calls": [
            {"id": "first", "function": {"name": "read"}},
        ]}]}
        good = write("clean.json", clean_data)
        bad = write("forbidden-second.json", {"name": "demo", "messages": [{"tool_calls": [
            {"id": "first", "function": {"name": "read"}},
            {"id": "second", "function": {"name": "deny_0"}},
        ]}]})
        clean_data["name"] = "not-pinned"
        unknown = write("unknown.json", clean_data)
        baseline = work / "baseline.json"
        freeze = subprocess.run(
            [sys.executable, "-m", "tracegate.cli", "freeze", str(good),
             "--rubric", str(rubric), "--out", str(baseline), "--tolerance", "0.05"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if freeze.returncode != 0:
            raise RuntimeError(freeze.stdout + freeze.stderr)
        legacy_data = json.loads(baseline.read_text(encoding="utf-8"))
        del legacy_data["rubric_sha256"]
        legacy = write("legacy.json", legacy_data)
        cases = []
        for label, traces, pin in (
            ("Clean recorded trace", [good], baseline),
            ("Forbidden second call", [bad], baseline),
            ("Known + unknown cases", [good, unknown], baseline),
            ("Legacy pin without hash", [good], legacy),
        ):
            status, result = _run("check", *traces, "--rubric", rubric,
                                  "--baseline", pin, "--json")
            _, score = _run("score", traces[0], "--rubric", rubric, "--json")
            cases.append({"label": label, "exit_code": status,
                          "first_case_score": score[0], "result": result})
        return {"fixture_kind": "synthetic", "forbidden_name_count": 20,
                "quality_floor": 0.95, "cases": cases}


def render_svg(proof: dict) -> str:
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="600" '
        'viewBox="0 0 1080 600" role="img" aria-labelledby="title desc">',
        '<title id="title">A passing average does not waive policy</title>',
        '<desc id="desc">Real CLI results from four synthetic cases. Clean evidence passes; '
        'a forbidden second call, an unknown case and a missing fingerprint all exit 2.</desc>',
        '<rect width="1080" height="600" rx="20" fill="#0c1726"/>',
        '<g font-family="system-ui, sans-serif" fill="#e7eff9">',
        '<text x="40" y="48" font-size="15" fill="#99b8d7">TRACE-GATE / SYNTHETIC CLI PROOF</text>',
        '<text x="40" y="94" font-size="31" font-weight="700">'
        'A passing average does not waive policy.</text>',
        '<text x="40" y="128" font-size="18" fill="#a9bbcf">'
        '20 forbidden names · quality floor 0.9500 · no model calls</text>',
    ]
    for index, case in enumerate(proof["cases"]):
        y = 162 + index * 82
        result = case["result"]
        color = "#8ce8b1" if result["ok"] else "#ffb4a7"
        label = escape(case["label"])
        verdict = escape(result["verdict"])
        score = case["first_case_score"]["composite"]
        lines.extend([
            f'<rect x="32" y="{y}" width="1016" height="70" rx="10" fill="#17283c"/>',
            f'<text x="48" y="{y + 28}" font-size="19">{label}</text>',
            f'<text x="48" y="{y + 53}" font-size="15" fill="#a9bbcf">'
            f'First case composite: {score:.4f}</text>',
            f'<text x="425" y="{y + 32}" font-family="monospace" '
            f'font-size="18" fill="{color}">{verdict}</text>',
            f'<text x="950" y="{y + 32}" font-size="18" fill="{color}">'
            f'exit {case["exit_code"]}</text>',
        ])
    lines += [
        '<text x="40" y="526" font-size="17">'
        'Forbidden second call: deny_0. Composite 0.9875 exceeds the floor; '
        'the gate still refuses.</text>',
        '<text x="40" y="558" font-size="15" fill="#a9bbcf">'
        'Reproduce: python scripts/render_gate_demo.py · Recorded JSON only, '
        'not proof of agent safety.</text>',
        '</g></svg>',
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    proof = capture_demo()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "gate-proof.json").write_text(json.dumps(proof, indent=2) + "\n",
                                                encoding="utf-8")
    (args.out_dir / "gate-proof.svg").write_text(render_svg(proof), encoding="utf-8")
    for case in proof["cases"]:
        print(f"{case['label']}: {case['result']['verdict']} (exit {case['exit_code']})")


if __name__ == "__main__":
    main()
