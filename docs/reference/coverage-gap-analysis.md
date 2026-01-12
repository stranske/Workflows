# Coverage Gap Analysis

This page is a durable checklist for answering two questions:

1. “What’s currently under-tested?”
2. “What’s the fastest path to improving coverage without writing fragile tests?”

Coverage numbers and the “lowest coverage files” list change frequently, so this doc avoids hard-coded snapshots.
Use the artifacts and config files below as the source of truth.

## Source of truth

- **Coverage baseline policy**: [config/coverage-baseline.json](../../config/coverage-baseline.json)
	- This is what guard workflows compare against.
- **Local coverage outputs** (common defaults): `coverage.json` and `coverage-output.txt` in the repo root.
	- Treat these as *generated* artifacts; they may be stale until you rerun tests.
- **CI coverage artifacts**: the Gate workflow (and its summary job) uploads coverage bundles; prefer CI artifacts when troubleshooting branch-protection failures.

## How to generate a fresh report locally

From the repo root:

```bash
pytest tests/ --cov=scripts --cov-report=term-missing
```

Notes:

- The `Cover` column highlights per-file coverage; focus on large, low-coverage modules first.
- If you want the repository’s canonical “kitchen sink” validation, run `./scripts/check_branch.sh`.

## How to pick targets (high leverage)

Start with code that is:

- **Pure or deterministic** (formatters, parsers, data transforms)
- **Frequently executed** (Gate summary helpers, CI summary builders)
- **High statement count** (a modest percentage gain can translate into many covered statements)

Avoid writing tests that overfit:

- **GitHub API behavior** (mock at the HTTP boundary or encapsulate API calls)
- **Shell subprocess output** (prefer asserting on structured return values)
- **Timestamps/randomness** (inject clocks/seed values)

## Testing patterns

- **File system**: use `tmp_path` and operate on real files/directories.
- **Environment variables**: use `monkeypatch.setenv()`.
- **Subprocess**: mock `subprocess.run` / `subprocess.check_output` (assert arguments + return codes).
- **Network**: mock `requests` (or use `responses`) at the boundary.

### Test naming convention

- `scripts/foo.py` → `tests/scripts/test_foo.py`
