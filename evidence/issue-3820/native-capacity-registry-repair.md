# Native capacity registry repair — Workflows#3822

Codex P2 finding `4238556720`; parent-adopted configuration maintenance only.
Unchanged HEAD: `fbb4e424d29f3f51058b247e2be390093dca299d`. Parent remains sole publication and acceptance owner.

## Source change and scope

The existing v2 `config/model_registry.json` model rows now carry optional
`native_capacity` metadata for exactly OpenAI `gpt-5.6-terra` and Anthropic
`claude-sonnet-5-5`. No new model, limit, selection, source claim or provider was
added. After removing these two optional objects, the complete registry equals
HEAD's registry, including all facts, selections and history. Existing registry
loaders/freshness/promotion tooling permit optional row metadata; no schema or
selection-policy migration was needed. The manifest already manages config and
helper, and `scripts/sync_templates.sh` uses the compiled manifest, so only the
three touched exact root/template pairs were copied; no broad sync was run.

`tools.llm_registry.native_capacity_facts_for` performs a separate strict exact
provider/model lookup. Missing/unreadable/non-object/wrong-schema config,
non-finite JSON, duplicate JSON keys or exact identities, noncanonical providers,
blocked/unregistered selected entries, absent/unknown fields, bad limit types,
provider-wrong transports, custom endpoints, and invalid official provenance/date
bindings fail closed. Config cannot import SDK types or choose arbitrary counter
methods/URLs. Validation checks structure and official model-bound provenance;
it cannot independently prove the numerical truth of newly authored config.
Capacity maintenance still requires reviewed official evidence.

The verifier consumes those validated facts while retaining its exact adapter/SDK
checks, authenticated root/counter/payload binding, input-field coverage, actual
native counts, request SHA256/change guard, and independent positive integer
input/context/output limits. Terra's three facts remain input 922000, context
1050000, output 128000; its unset output default comes from the same configured
output fact and explicit output is preserved. Sonnet still retrieves exact native
Models metadata on each preflight; only documented context 1000000/output 128000
are configured, with output bounded by native metadata too. Configured input
substitutes for Sonnet metadata are rejected. Standard never consults these facts
and retains request bytes, defaults and invocation behavior. Shared client builders,
routing and model selection are unchanged. Unknown future models gain no inferred
capacity support; exact catalogue entries without facts remain unsupported.

Root/template config, helper and verifier are identical. Existing manifest scope
is retained and descriptions updated. Expanded input snapshot/consumer fingerprint
advance v5 → v6 together; standard remains v2. Pair.14's **normalized** template
hash is refreshed, preserving its root hash, original review date and entire prior
history. No workflow was renamed and no aggregation logic was changed.

## Actual production/config RED → byte-identically restored GREEN

Before repair, the new absent-selected-entry check failed twice: the literal
production branches still counted/generated with an unregistered selected model.
Command (the wrapper subsequently printed the raw log):

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/scripts/test_native_capacity_registry.py -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-registry-original-red.xml
```

Raw `native-capacity-registry-original-red.{txt,xml}`: **2 failed**, both
`DID NOT RAISE InputCapacityError`, rather than an import or collection failure.

For the final deliberate break, removed both `native_capacity` objects from the
**actual production `config/model_registry.json`**, leaving all code and tests
unchanged. The real configured adapters still resolved, but the production guard
refused generation in evaluate, compare and actual schema repair for both providers.
Ran:

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/scripts/test_native_capacity_recovery.py -k configured_native_expanded_reaches_count_and_generation -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-registry-final-mutation-red.xml
```

Exit **1**, **6 failed**, zero collection errors. Restored the exact saved production
config bytes and ran the identical selector with JUnit
`native-capacity-registry-final-restored-green.xml`: exit **0**, **6 passed**.
The real production metadata/count/generation paths are exercised with simulated
provider responses; no live provider call was made.

| Binding | SHA256 |
|---|---|
| Repaired/restored production config and template | `6f5dc7c505dde55565458f24d6f34b8a7dcda453e88dcddb75b732515f91e09d` |
| Deliberately mutated production config | `b31cafac904272deac2f6e574b9e91a35581bc1e275daad36c8da466cb0e8c6c` |
| Repaired/restored helper and template | `f6082dfa4269950828baf30a59301a559226899fc5a5d5e818be549921991a90` |
| Repaired/restored verifier and template | `892d992e8fe614a05373219eb5aaa9173e5ba8b92105774b62f070e2979264e5` |
| Native tests, unchanged during RED/GREEN and from HEAD | `3cef9527c8d1a775a859ad1bc37a6705770ffb8f648e8e0c077d14e747625ee4` |
| New registry tests, unchanged during final RED/GREEN | `dd2b6d1fc8b4dcdec60540275474fb17ac9c3cb75d380890ead7114e90a767cc` |

[Final RED/GREEN proof](native-capacity-registry-final-proof.json) records exact
command arrays, exit codes, JUnit summaries, source/config/test before/restored
hashes and raw log/XML hashes. The earlier mutation proof is also retained.

## Bounded final validation

Every Python command uses the locked cached **offline** uv prefix shown above.

- Original bounded regression: **552 passed, 19 skipped** in 52.44s. All **70**
  all-arms cases still pass and that test file remains byte-identical. The original
  historical 552-pass text/XML/proof artifacts also remain byte-identical.
- Registry/config/selection/template supplement: **358 passed, 2 skipped** in
  7.45s, including **178 passing new registry cases**. Checks cover exact lookup,
  supported versus unregistered identities, every independent documented limit's
  missing/malformed types, missing/duplicate/provider-wrong facts and transports,
  official provenance, dynamic configured bounds/defaults, supported native
  generation, standard unchanged even with an unreadable capacity registry, and
  source/template/manifest parity. Existing native tests retain SDK MockTransport
  count/generation, all three operation paths, independent limits, metadata failures
  and no alternate-provider fallback coverage.
- After correcting the allowlist's initial raw-versus-normalized hash mistake,
  narrow allowlist tests: **6 passed**. Drift: **6 in sync, 20 allowlisted,
  0 unallowlisted**; template sync passes.
- Final Ruff, Black (six Python files), actionlint on the two fingerprint workflows,
  and `git diff --check`: all exit **0**. Actionlint's external shellcheck/pyflakes
  integrations were disabled, as in the preserved prior bounded proof.

Exact final regression command:

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/workflows/test_verifier_expanded_comparison.py tests/workflows/test_verifier_evidence_profile.py tests/workflows/test_verifier_terminal_disposition.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_template_drift_allowlist.py tests/test_workflow_guide_verifier_sections.py -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-registry-final-regression.xml
```

Exact final supplement command:

```sh
uv run --offline --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/scripts/test_native_capacity_registry.py tests/tools/test_llm_registry_selection.py tests/test_llm_registry_malformed_input.py tests/test_check_model_registry_freshness.py tests/scripts/test_validate_template_sync.py tests/scripts/test_sync_manifest_compiler.py tests/workflows/test_workflow_llm_installs.py -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-registry-final-config.xml
```

[Verification receipt](native-capacity-registry-verification.json) retains all
final validation commands, summaries, skip reasons and file/artifact hashes.
The 19 regression skips are 18 provider-inapplicable matrix cases and the absent
owner-local authenticated capture. The two supplement skips are existing
agent-high-privilege pip-cache checks; the affected cache behavior was not changed.
No broad/full grammar suite was run. Initial test/lint/drift logs are preserved;
three new-test context-manager lint warnings and the mechanical normalized-hash
error were corrected before final verification.

## Preservation, changed paths and limits

The [preservation receipt](native-capacity-registry-preservation.json) retains
all **2706** baseline file hashes: **2692** remain unchanged,
and only the 14 intended existing files changed. All **22** prior
untracked owner artifacts and all historical issue-3820 evidence are unchanged.
`tests/workflows/test_verifier_expanded_comparison.py` remains
`398572a051b86fbad858f44cc07379dce11c3b0bc3351e4fbec861c05da6c071`.
Shared `tools/langchain_client.py`, model selection policy JSON, slots, lockfile,
pyproject, existing mutation scripts and owner brief remain unchanged.

Existing changed paths:

- `.github/sync-manifest.yml`
- `.github/workflows/reusable-agents-verifier.yml`
- `config/model_registry.json`
- `config/template-drift-allowlist.txt`
- `docs/MODEL_SELECTION_POLICY.md`
- `docs/WORKFLOW_GUIDE.md`
- `docs/ops/CONSUMER_REPO_MAINTENANCE.md`
- `scripts/langchain/pr_verifier.py`
- `templates/consumer-repo/.github/workflows/agents-verifier.yml`
- `templates/consumer-repo/config/model_registry.json`
- `templates/consumer-repo/scripts/langchain/pr_verifier.py`
- `templates/consumer-repo/tools/llm_registry.py`
- `tests/workflows/test_verifier_evidence_profile.py`
- `tools/llm_registry.py`

New paths: `tests/scripts/test_native_capacity_registry.py`, this report and
`evidence/issue-3820/native-capacity-registry-*` evidence artifacts.

HEAD remains `fbb4e424d29f3f51058b247e2be390093dca299d`. No commit, push, GitHub
operation, review/assessor task, automation write or PR#3821 change was performed.
These results prove bounded local source/config behavior only. **Live provider
capacity remains UNKNOWN; provider acceptance remains UNKNOWN/NONPASS.** No hosted
execution/deployment, actual new authenticated native counts or either provider
verdict is established. Parent owns publication, review/disposition and continuation.
