# Automated Autofix & Type Hygiene Pipeline

This repository includes an extended **autofix** workflow that standardises style and performs *lightweight* type hygiene automatically on pull requests. The Gate summary job invokes the reusable composite whenever a PR opts in via the `autofix:clean` label.

## What It Does (Scope)
1. Code formatting & style
- Early `ruff check --fix --exit-zero` sweep that runs before the heavier composite so trivial whitespace/import issues are cleaned even when later phases short-circuit. The step installs the pinned Ruff version when `.github/workflows/autofix-versions.env` is present and otherwise falls back to the latest release.【F:.github/workflows/reusable-18-autofix.yml†L231-L275】
  - Full composite run covering `ruff`, `black`, `isort`, and `docformatter` with both safe and targeted lint passes.【F:.github/actions/autofix/action.yml†L34-L110】
   - `black` (code formatting)
   - `isort` (import sorting where unambiguous)
   - `docformatter` (docstring wrapping)
2. Type stub installation
   - Runs `mypy --install-types --non-interactive` to fetch missing third‑party stubs where available.
3. Targeted type hygiene
   - Executes `scripts/auto_type_hygiene.py` which injects `# type: ignore[import-untyped]` ONLY for a small allowlist of third‑party imports (default: `yaml`).
   - Idempotent: re-running does not duplicate ignores.
4. Warm mypy cache
   - Invokes a non-blocking mypy run so subsequent CI/type checks are faster.

If any step produces changes, the workflow auto‑commits them back to the PR branch with a conventional message (e.g. `chore(autofix): style + type hygiene`).

## Result Labels & Status Comment
- Same-repo branches that receive an autofix commit automatically gain the `autofix:applied` label; forked PRs receive `autofix:patch` when an artifact is uploaded.【F:.github/workflows/reusable-18-autofix.yml†L520-L644】【F:.github/workflows/reusable-18-autofix.yml†L675-L785】
- Runs that finish clean (no diff) toggle `autofix:clean`, while any unresolved diagnostics append `autofix:debt` alongside the primary outcome label.【F:.github/workflows/reusable-18-autofix.yml†L632-L785】
- Every execution updates a single status comment with an **Autofix result** block that lists the applied labels so reviewers can confirm the outcome at a glance.【F:.github/workflows/reusable-18-autofix.yml†L520-L671】【F:scripts/build_autofix_pr_comment.py†L230-L275】

## What It Intentionally Does NOT Do
- It does **not** attempt deep structural refactors or resolve complex type inference issues.
- It does **not** add stubs for internal modules or apply `# type: ignore` broadly.
- It does **not** silence genuine semantic/type errors (e.g. wrong argument counts, incompatible assignments).
- It does **not** enforce exhaustive strict mypy modes across legacy areas not yet migrated.

This narrow scope keeps the automation safe, deterministic, and low‑noise.

## Extending the Allowlist
The allowlist for untyped third‑party imports lives in `scripts/auto_type_hygiene.py`:
```python
ALLOWLIST = {"yaml"}
```
To add another untyped module (e.g. `fastapi` if desired):
1. Edit the set to include the module root name.
2. Run:
   ```bash
   python scripts/auto_type_hygiene.py --check
   ```
3. Commit the resulting changes (if any).

Prefer adding *only* modules that reliably lack published stubs or where partial typing would otherwise generate persistent noise.

## Local Developer Workflow
During active development:
```bash
./scripts/dev_check.sh --changed --fix   # ultra-fast sanity (2-5s)
./scripts/validate_fast.sh --fix         # adaptive validation (5-30s)
./scripts/run_tests.sh                   # full test suite (15-25s)
```
Before pushing a feature branch:
```bash
./scripts/validate_fast.sh --fix
./scripts/run_tests.sh
```
If CI leaves an autofix commit on your branch, **pull/rebase** before adding further changes.

## When To Escalate Beyond Automation
Open a focused PR (or issue) for:
- Introducing or refactoring complex protocols / generics.
- Replacing dynamic imports with explicit optional dependency shims.
- Tightening mypy configuration (e.g. enabling `disallow-any-generics`).
- Broad import hygiene sweeps beyond the allowlist.

## Design Principles
| Principle | Rationale |
|-----------|-----------|
| Idempotent | Re-running produces no further diffs when clean. |
| Minimal Surface | Only low-risk fixes applied automatically. |
| Deterministic | Output stable across environments. |
| Transparent | All mutations committed with explicit chore message. |
| Extensible | Allowlist easily adjusted with single source of truth. |

## Troubleshooting
| Symptom | Likely Cause | Action |
|---------|--------------|-------|
| Repeated autofix commits | Unformatted notebooks (black lacks jupyter extra) | Install `black[jupyter]` locally or exclude notebooks. |
| New mypy errors after a rebase | Upstream typing tightened | Resolve manually; avoid blanket `# type: ignore` unless justified. |
| Missing ignore for known untyped lib | Not in allowlist | Add to `ALLOWLIST` in script, run autofix locally. |
| CI autofix skipped | No diff produced | Confirm local environment replicates tool versions. |

## Acceptance criteria traceability

| Acceptance criterion | Implementation checkpoints |
|----------------------|----------------------------|
| Safe fixes only (formatting, imports, trivial lint) | Early Ruff sweep runs before the composite autofix to catch cosmetic diffs, then the composite restricts itself to formatter and lint hygiene tooling.【F:.github/workflows/reusable-18-autofix.yml†L231-L475】【F:.github/actions/autofix/action.yml†L34-L110】 |
| Labels applied correctly based on outcome | Result blocks enumerate the applied labels and the outcome label manager toggles `autofix:applied`, `autofix:clean`, `autofix:patch`, and `autofix:debt` based on change detection and residual diagnostics.【F:.github/workflows/reusable-18-autofix.yml†L520-L785】【F:tests/test_build_autofix_pr_comment.py†L68-L206】 |
| PR description comment summarising what changed | The consolidated PR comment always embeds the Autofix result block (when provided) so reviewers see the commit or patch link alongside the label summary, with regression tests locking the behaviour in place.【F:scripts/build_autofix_pr_comment.py†L230-L275】【F:tests/test_build_autofix_pr_comment.py†L68-L206】 |

## Verification scenarios

Run these quick checks whenever the Gate summary job’s autofix lane changes to confirm Issue #2649’s safeguards remain in place:

### Same-repo opt-in
1. Open a branch in the main repository with a deliberate lint issue (for example, reorder an import) and add the `autofix:clean` label.
2. Verify the Gate summary job triggers exactly one `apply` job once Gate succeeds and cancels any superseded runs when you push extra commits or re-run the workflow from the UI.
3. Confirm the comment updated in place under the `<!-- autofix-status: DO NOT EDIT -->` marker shows the applied commit link and an "Autofix result" section.

### Fork opt-in
1. From a fork, open a PR with the `autofix:clean` label and a trivially fixable lint issue.
2. Ensure the workflow uploads an `autofix-patch-pr-<number>` artifact, applies the `autofix:patch` label, and the status comment explains how to apply the patch locally.
3. Download and apply the patch with `git am` to confirm it replays cleanly, then push manually to complete the fix.

### Label outcomes
1. Re-run the workflow on a clean branch (no staged lint issues) and verify the status comment reports “No changes required” with the `autofix:clean` label.【F:.github/workflows/reusable-18-autofix.yml†L646-L673】【F:.github/workflows/reusable-18-autofix.yml†L675-L785】
2. Introduce a trivial lint (e.g. reorder imports) and confirm the rerun pushes a commit, applies `autofix:applied`, and lists the label in the comment.【F:.github/workflows/reusable-18-autofix.yml†L520-L575】【F:.github/workflows/reusable-18-autofix.yml†L675-L785】
3. If the run leaves residual diagnostics, expect `autofix:debt` to accompany either result label.【F:.github/workflows/reusable-18-autofix.yml†L632-L785】

### Tests-only cosmetic sweep
1. Ensure the `autofix:clean` label is present to activate the tests-only mode for the run.【F:.github/workflows/reusable-18-autofix.yml†L6-L334】
2. Confirm Ruff only operates on paths within `tests/` and the guard fails if non-test files change.【F:.github/workflows/reusable-18-autofix.yml†L277-L360】
3. Check the automation posts the dedicated tests-only summary comment enumerating the modified test files.【F:.github/workflows/reusable-18-autofix.yml†L899-L964】

### Label gating sanity check
1. Remove the `autofix:clean` label (or open a fresh PR without it) and trigger the workflow via the **Re-run** button.
2. Confirm the `apply` job is skipped and no new comments are posted, demonstrating the label gate is working as expected.

### Demo PR verification (acceptance scenario)
To replicate Issue #2724’s acceptance criteria end-to-end:

1. Push a same-repo branch that intentionally violates a simple Ruff rule (for example, add trailing whitespace to a Python file).
2. Open a pull request targeting the default branch and add the opt-in autofix label (`autofix:clean`).
3. Observe the Gate summary job run; once complete it should:
   - Install Ruff, apply the safe `ruff check --fix --exit-zero` sweep, and commit cosmetic fixes back to the branch.【F:.github/workflows/reusable-18-autofix.yml†L231-L575】
   - Apply the `autofix:applied` label (and remove any stale `autofix:clean`) when the commit lands.【F:.github/workflows/reusable-18-autofix.yml†L520-L575】【F:.github/workflows/reusable-18-autofix.yml†L675-L785】
   - Update the status comment with an **Autofix result** block summarising the labels and linking to the commit.【F:.github/workflows/reusable-18-autofix.yml†L520-L671】【F:scripts/build_autofix_pr_comment.py†L230-L275】
4. If no diff is produced (for example, after re-running on a clean branch) expect the workflow to reapply `autofix:clean` and report “No changes required.” in the same status comment block.【F:.github/workflows/reusable-18-autofix.yml†L646-L673】【F:.github/workflows/reusable-18-autofix.yml†L675-L785】

## Future Enhancements (Optional Backlog)
- Add metrics: record autofix delta lines per run.
- Dry-run mode for PR comments instead of commits (toggle by label).
- Expand hygiene to detect *unused* ignores and prune them automatically.

---
Maintainers: keep this doc aligned with any future changes to `.github/actions/autofix/action.yml` or `scripts/auto_type_hygiene.py` so contributors understand the automation contract.
