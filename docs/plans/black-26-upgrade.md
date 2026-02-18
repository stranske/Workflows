# Black 26 Alignment Plan

**Tracking issue:** https://github.com/stranske/Workflows/issues/1540

## Goal
Bring every registered consumer repository up to the same formatter pin that the Workflows repo already enforces (`BLACK_VERSION=26.1.0` in `.github/workflows/autofix-versions.env`). This eliminates recurring drift in sync PRs and keeps the lint/format checks reproducible.

## Consumer repo status snapshot (2026-02-18)

| Repo | Local path | Current pin | Evidence | Notes |
| --- | --- | --- | --- | --- |
| Travel-Plan-Permission | `../Travel-Plan-Permission` | ✅ `black>=26.1.0` (`pyproject.toml` line 32) & lockfile pin | `rg "black" pyproject.toml requirements.lock` | Already aligned; use as verification baseline after automation runs. |
| Template | `../Template` | ✅ `black==26.1.0` in dev extras + `[tool.black]` (pyproject lines 26/92) | `rg "black" pyproject.toml requirements-dev.lock` | Added pin + config via Template commit (local changes ready to push). |
| Counter_Risk | `../Counter_Risk` | ⚠️ `black==24.10.0` across `pyproject.toml`, `requirements.lock`, `requirements-dev.lock` | `rg "black"` | Upgrade blocker; recent rollbacks (see `agents/autofix_pr104_*` notes) need a follow-up fix after verifying Python 3.11 compatibility. |
| trip-planner | `../trip-planner` | 🚫 no formatter dependency or config | `pyproject.toml` only lists ruff/mypy/pytest | Need to add `black==26.1.0` dev extra and wire into CI scripts; also ensure `scripts/check_test_dependencies.sh` installs it. |
| Manager-Database | `../Manager-Database` | ✅ `black==26.1.0` (`pyproject.toml` line 33, `requirements.lock`) | `rg "black" pyproject.toml requirements.lock` | No change required besides verifying once automation lands. |
| Portable-Alpha-Extension-Model | `../Portable-Alpha-Extension-Model` | ⚠️ Mixed: `requirements.lock` pin 26.1.0 but `requirements-dev.txt` still 24.4.2 | `rg "black" requirements-dev.txt requirements.lock` | Need to update dev requirements + Makefile bootstrap to 26.1.0 so local workflows stop flipping the version. |
| Trend_Model_Project | `../Trend_Model_Project` | ✅ `black==26.1.0` everywhere | `pyproject.toml` line 104, `requirements.lock` line 31 | Already aligned. |
| Collab-Admin | `../Collab-Admin` | 🚫 no formatter dependency | `pyproject.toml` lacks any black entry | Add dev extra + CI wiring so maintainers have a consistent formatter. |
| Template consumer list extras (REGISTERED_CONSUMER_REPOS) | `.github/workflows/maint-68-sync-consumer-repos.yml` | includes `stranske/Collab-Admin`, `Counter_Risk`, `Manager-Database`, `Portable-Alpha-Extension-Model`, `Travel-Plan-Permission`, `Trend_Model_Project`, `trip-planner`, `Template` | lines 72-79 | Use this authoritative list when scheduling upgrades / automation runs. |

## Prep actions to perform before touching repos

1. **Capture automation hooks**
   - `maint-52-sync-dev-versions.yml` already reads `REGISTERED_CONSUMER_REPOS`. We will extend its script to fail if a repo still pins `<26`. (Prep task: confirm script path `scripts/sync_dev_dependencies.py` handles formatter drift gracefully.)
   - Draft a helper script (e.g. `scripts/black_upgrade/report.py`) that reads each repo’s `pyproject.toml` / `requirements*.txt` and prints detected pins. (Not yet implemented; placeholders left in this plan.)

2. **Define repo-specific upgrade steps**
   - **Template:** add `"black==26.1.0"` to `[project.optional-dependencies.dev]` and ensure `.github/workflows/pr-00-gate.yml` calls `black --check .`.
   - **Counter_Risk:** reproduce the Python 3.11 install error cited in `agents/autofix_pr104_*`, then bump pins + rerun `scripts/sync_dev_dependencies.py --check`. We may need to patch any legacy import incompatibilities before repinning.
   - **trip-planner & Collab-Admin:** create `requirements-dev.txt` (if absent) with Black 26, update CI to install it, and add a `[tool.black]` section with the shared settings (line length 100).
   - **Portable-Alpha-Extension-Model:** align `requirements-dev.txt`, Makefile bootstrap, and any docs that still instruct developers to install `black==24.4.2`.

3. **Documentation & comms**
   - Update `docs/ops/CONSUMER_REPO_MAINTENANCE.md` with a short “Formatter upgrade checklist” once the rollout completes.
   - Add a reminder in `CLAUDE.md` near the consumer repo section so agents know to run `make format` / `black .` after the new pins land.

4. **Verification plan**
   - After each repo upgrade, run `uv run black --check .` and the relevant GitHub Actions workflow locally (`act` or `gh workflow run pr-00-gate.yml`) to ensure no new drifts.
   - Re-run Workflows’ `maint-68-sync-consumer-repos` dry run to confirm no formatter diffs remain.

## Next steps (actionable checklist)

1. [ ] Create stats script to emit current formatter pins per repo (source: this doc).
2. [x] Update `Template` repo dev dependencies + add `[tool.black]` block.
3. [ ] Prep Counter_Risk regression repro instructions (document in the issue) before attempting the bump.
4. [ ] Add `black==26.1.0` to `trip-planner` and `Collab-Admin` dev extras + CI workflows.
5. [ ] Align Portable-Alpha-Extension-Model’s `requirements-dev.txt` and Makefile.
6. [ ] Trigger `maint-52-sync-dev-versions` after all repos land to verify no `--check` drift.
7. [ ] Close issue #1540 once every repo row above is ✅.
