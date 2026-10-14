# Expanded comparison all-arms repair — Workflows#3822

Finding `4238496010`, parent-adopted P1; unchanged HEAD
`b94a4667b81ef1bf04ec01219fbe98be37ecb02e`.

The authored comparison step filtered `used_llm=false` arms before computing
all-PASS. Both native judge positions reproduced **comparison PASS / unified PASS**
with the other arm unavailable. Expanded now validates every arm against the first
two configured comparison slots before availability filtering: exact provider/model,
strict result schema, boolean `used_llm=true`, PASS, no error, exact count, no duplicates.
Invocation model overrides follow the shared builder. Missing, failed, UNKNOWN,
unsupported fallback, malformed, duplicate and extra arms remain CONCERNS.
Standard's legacy aggregation and v2 fingerprint are deliberately unchanged.

Source and consumer verifier copies are identical. Reusable input snapshot and
consumer fingerprint advance expanded v4 → v5 together. The existing manifest
entry documents the change without altering copy scope. Only pair.14's consumer
hash/history was refreshed; its root hash, original divergence review date and
entire previous history remain intact. No execution-context divergence changed.

## Actual production RED → GREEN

All pytest commands used the cached locked SDK environment, offline:

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/workflows/test_verifier_expanded_comparison.py -k 'each_arm_blocks_pass and used-false and not used-false-pass' -q -o addopts= --junitxml=evidence/issue-3820/expanded-comparison-mutation-red.xml
```

- Original, unmodified production workflow before repair: exit **1**, **2 failed**,
  56 deselected; both failures showed actual `verdict=PASS`, `unified=PASS`.
  Raw: `expanded-comparison-original-red.{txt,xml}`.
- Deliberately restored the original filtering logic **in the actual production
  workflow**, changing only the comparison aggregation block: exit **1**,
  **2 failed**, 68 deselected. Raw: `expanded-comparison-mutation-red.{txt,xml}`.
- Restored the repaired workflow **byte-for-byte**, then ran the same command
  with `--junitxml=evidence/issue-3820/expanded-comparison-restored-green.xml`:
  exit **0**, **2 passed**, 68 deselected. Raw: `expanded-comparison-restored-green.{txt,xml}`.

The test intercepts only the provider CLI's JSON. The complete authored comparison
shell, real parser/imports, GITHUB_ENV profile propagation, GITHUB_OUTPUT and unified
verdict shell execute. This is behavioral RED, not a collection/import failure.
The source integration cases additionally run real evaluate/compare code with
controlled invocation failures or PASS responses before applying real coverage
floors and those same workflow shells.

| SHA256 binding | Digest |
|---|---|
| Original workflow | `caac7552e8857597c395f30317fe99cedd720a374eb438fc15fe00fd1075bdb9` |
| Mutated production workflow | `c62e9c9fd49cf4a73fbe9568108c14fa0b74f72bcaedd8f6dcdd7376dfb8d4b4` |
| Repaired and byte-identically restored workflow | `07f26802c94547fe245d3890e98a1eae4c21beba8f9a3bcacf7b35728936e5f0` |
| Final regression test file, identical during mutation RED/restored GREEN | `398572a051b86fbad858f44cc07379dce11c3b0bc3351e4fbec861c05da6c071` |
| Source and identical consumer verifier | `5315ff4583dec4a3b461448c291b4354751f2afc145e20499382948582b10865` |

`expanded-comparison-proof.json` retains the exact command arrays, exit codes and
raw RED/GREEN text/JUnit hashes. `expanded-comparison-verification.json` binds the
final validation logs/JUnit and source/configuration files by SHA256.

## Bounded final validation

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/workflows/test_verifier_expanded_comparison.py tests/workflows/test_verifier_evidence_profile.py tests/workflows/test_verifier_terminal_disposition.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_template_drift_allowlist.py tests/test_workflow_guide_verifier_sections.py -q -o addopts= --junitxml=evidence/issue-3820/expanded-comparison-regression-final.xml
```

Exit **0**, **552 passed, 19 skipped** in 51.22s; final text/JUnit retained.
The new **70 passing** workflow cases cover both native positions with missing,
unused (including false+PASS), CONCERNS/FAIL/UNKNOWN/ERROR, native-count error,
unsupported fallback, malformed/empty fields, invalid JSON/empty output,
non-boolean flags, wrong model, duplicate/extra arms and all-PASS. They also cover
registry slot identity/order, invocation overrides, source evaluate/compare failure
integration, required-evidence/changed-code floors, unified CI floors, standard
legacy behavior and profile/fingerprint integration (42 existing profile cases).
The native suite contributes **278 passing, 18 parameter-inapplicable skips**;
the remaining skip is the owner-local authenticated capture, not configured here.

The first supplemental regression attempt had two failures in newly authored
required-evidence fixtures: their context omitted the production evidence inventory.
Those fixtures were corrected to the existing production-shaped context; no
production evidence rule changed. Initial logs remain `expanded-comparison-regression.{txt,xml}`.
Initial Ruff import-spacing failures were corrected; its original log is retained.

The same uv prefix (through `python`) ran:

```sh
python -m ruff check scripts/langchain/pr_verifier.py templates/consumer-repo/scripts/langchain/pr_verifier.py tests/workflows/test_verifier_expanded_comparison.py tests/workflows/test_verifier_evidence_profile.py
python -m black --check --target-version py312 scripts/langchain/pr_verifier.py templates/consumer-repo/scripts/langchain/pr_verifier.py tests/workflows/test_verifier_expanded_comparison.py tests/workflows/test_verifier_evidence_profile.py
python scripts/check_template_drift.py --allowlist config/template-drift-allowlist.txt
```

All exit **0** (`ruff-verified`, `black-final`, `template-drift` logs). Drift:
**6 in sync, 20 allowlisted, 0 unallowlisted**. Also exit **0**:

```sh
actionlint -shellcheck= -pyflakes= .github/workflows/reusable-agents-verifier.yml templates/consumer-repo/.github/workflows/agents-verifier.yml
git diff --check
```

Actionlint's external shellcheck/pyflakes integrations were disabled; Ruff and
actual shell execution provide the bounded checks above. No CI/coverage floor,
lockfile, routing registry or automation configuration was changed.

## Changed paths and preservation

- `.github/workflows/reusable-agents-verifier.yml`
- `scripts/langchain/pr_verifier.py`
- `templates/consumer-repo/scripts/langchain/pr_verifier.py`
- `templates/consumer-repo/.github/workflows/agents-verifier.yml`
- `.github/sync-manifest.yml`
- `config/template-drift-allowlist.txt`
- `docs/WORKFLOW_GUIDE.md`
- `docs/ops/CONSUMER_REPO_MAINTENANCE.md`
- `tests/workflows/test_verifier_evidence_profile.py`
- new `tests/workflows/test_verifier_expanded_comparison.py`
- new `evidence/issue-3820/expanded-comparison-*` proof artifacts and this note.

`expanded-comparison-preservation.json` verifies all other baseline files from a
2,681-file inventory remain byte-identical, including **all 22 prior untracked
artifacts**, and the allowlist's prior history is retained. HEAD is unchanged.
No commit, push, GitHub access/write, review request, model assessment, live provider
call, automation change, PR#3821 write or historical mutation script was performed.

## Limits and ownership

This proves bounded local aggregation/source behavior. Hosted capacity and provider
acceptance remain **UNKNOWN/NONPASS** pending actual hosted receipts. Independent
Sol Medium assessment `02bfc1a8851d2936752346e87da8732c24fa358442fe464fb5c64acde7b15e03`
covered the capacity function only; it is not aggregation, whole-PR or provider
acceptance. No full suite or full grammar matrix ran. The parent remains sole
publication, merge and reviewer owner.
