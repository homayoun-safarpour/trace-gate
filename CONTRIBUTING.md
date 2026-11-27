# Contributing

Public repo: https://github.com/homayoun-safarpour/trace-gate

## Local loop

These are the commands CI runs.

```bash
python -m pip install -r requirements-ci.txt
python -m ruff check src tests scripts integrations
python -m build --no-isolation
python -m pip install --no-index --no-deps --force-reinstall dist/*.whl
python scripts/verify_distribution.py --dist-dir dist
```

## Pull requests

1. One change per pull request.
2. A named pytest lock if you add a README claim.
3. Open a PR against `main`. Do not leave work only on a long-lived branch.
