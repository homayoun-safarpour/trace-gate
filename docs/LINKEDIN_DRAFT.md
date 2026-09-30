# LinkedIn draft (public-safe) - trace-gate first-screen restyle 2026-09-30

Field pain first. Homayoun posts himself.

Paste verified 2026-09-30 on `examples/trajectories/support_regress.json`:
verdict: REGRESSION
exit 2

---

Paste block (copy from the next line to the URL):

Pytest can be green while your agent starts calling a forbidden tool.

trace-gate scores a trajectory JSON against a frozen baseline. No LLM in CI.

The stranger run is the regression, not the pass:

git clone https://github.com/homayoun-safarpour/trace-gate
cd trace-gate && pip install -e .
trace-gate check examples/trajectories/support_regress.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json

verdict: REGRESSION
  support-agent-good: REGRESSION composite=0.5000 < floor=0.9500 (pinned=1.0000, tol=0.05)

Exit 2 fails the job. Exit 0 is PASS. If someone edits the rubric without re-freezing, that is RUBRIC_DRIFT, also exit 2.

The limit: it does not grade free-text replies. It checks tools, order, and a pinned composite.

Repo:
https://github.com/homayoun-safarpour/trace-gate
