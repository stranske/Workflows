# Native input/context repair — 2026-10-10

Workflows#3822, Codex finding `4238407535`; base and unchanged HEAD:
`c5e4fe99ddaf87f98c7eb5d2d6dcabf749409bfb`. Source repair only, no commits or
pushes. [Reviewer adoption and current contract](../native-capacity-recovery.md).

## Production RED / byte-identical restored GREEN

The new matrix constructs the real configured Terra/Sonnet adapters with dummy
credentials. Only provider metadata/count/generation results are simulated.
Evaluate, compare and actual schema-repair callbacks all exercise the production
capacity guard. Existing tests also execute the actual native SDK serialization
and response parsing through `httpx.MockTransport`.

After the repaired native suite passed, deliberately restored the production bug
in `scripts/langchain/pr_verifier.py`:

```diff
-        if tokens > window or tokens + output > context:
+        if tokens + output > window:
```

Ran the following command while the mutation was present:

```sh
uv run --isolated --no-project --python /opt/anaconda3/bin/python3 --with-requirements requirements.lock python -m pytest tests/scripts/test_native_capacity_recovery.py -k 'operations_matrix and openai and (formerly or boundary) and not metadata' -q -o addopts= --junitxml=evidence/issue-3820/native-context-window-mutation-red.xml
```

Exit **1**: **12 failed**, 284 deselected. These are valid Terra inputs
**794001, 858001, 922000** with full 128000 output, and **922000** with explicit
64000 output, across evaluate/compare/schema repair. The failures occur in the
production guard before generation. Transcript: `native-context-window-mutation-red.txt`.

Removed exactly the mutation with `apply_patch`; restored SHA256 equals the
pre-mutation source and consumer template. Repeated the identical test selector
with JUnit `native-context-window-restored-green.xml`: exit **0**, **12 passed**,
284 deselected. Transcript: `native-context-window-restored-green.txt`.

| Production state | SHA256 |
| --- | --- |
| Original committed source | `97627c429bc2c020062ad98213b6b948aa144ec6dad755d7d8fc1ad7a9462874` |
| Repaired before mutation | `f72882b91613c9489a19ab3797d07d13fcea9934a994ce6207ba0c0dd1fd487b` |
| Deliberately broken | `9735811093f96ef3619a60051b748fd6bc8723ba8e3ac140542f94024378a957` |
| Restored source and template | `f72882b91613c9489a19ab3797d07d13fcea9934a994ce6207ba0c0dd1fd487b` |

| Transcript | SHA256 |
| --- | --- |
| Mutation RED | `48868fecfe23fc52df5e9d16ef68824628309ac699010566dec2ae29e79e6da0` |
| Restored GREEN | `dfdd2f1bd3bdb4a57ff9a42d783c248d3f22347e60a44b49a54f931d1e5fc330` |
| Bounded regression | `0847c3ab0342f76de7b368cb22dd72989645dc19ad4c3f1e495fe036bce89659` |

## Completed validation

All Python commands use the exact `uv run --isolated --no-project --python
/opt/anaconda3/bin/python3 --with-requirements requirements.lock` prefix. Versions:
langchain-openai **1.4.1**, langchain-anthropic **1.5.4**, openai **2.48.0**,
anthropic **0.120.0**, pytest **9.1.1**, Black **26.10.0**, Ruff **0.16.10**.

- Native suite (`python -m pytest tests/scripts/test_native_capacity_recovery.py
  -q -o addopts=`): exit **0**, **278 passed, 18 skipped**. Skips are six existing
  Anthropic-only metadata cases plus twelve new Anthropic-only matrix cases under
  the OpenAI parameter. Logs/JUnit: `native-context-window-native.{txt,xml}`.
- Narrow native/capacity/workflow regression: `python -m pytest` with the explicit
  paths below, `-q -o addopts= --junitxml=evidence/issue-3820/native-context-window-regression.xml`:
  exit **0**, **735 passed, 20 skipped**. The additional skips are owner-local
  capture replay and live manifest issue-reference validation without a GitHub
  token. Logs/JUnit: `native-context-window-regression.{txt,xml}`.
- Separately replayed the immutable owner-local capture with
  `VERIFIER_RECOVERY_CAPTURE_DIR=/Users/teacher/.codex/automations/sync-dependency-pr-closer/worktrees/maint71-targeted-disposition-20261004/evidence/run-38059805990/comparison-results-38059805990`
  and `python -m pytest tests/scripts/test_pr_verifier_recovery.py::test_authenticated_capture_replay
  -q -o addopts=`: exit **0**, **1 passed**. Logs/JUnit:
  `native-context-window-capture.{txt,xml}`. This reads an old authenticated
  capture; it makes no live provider call and retains the evidence floor.
- `python -m ruff check` and `python -m black --check --target-version py312`
  on the source/template verifier, native suite and workflow profile suite:
  both exit **0**. Logs: `native-context-window-{ruff,black}.txt`.
- `python scripts/validate_template_sync.py`: exit **0**; direct source/template
  byte parity and manifest ownership tests also pass. Log:
  `native-context-window-parity.txt`.
- `actionlint -shellcheck= -pyflakes= .github/workflows/reusable-agents-verifier.yml
  templates/consumer-repo/.github/workflows/agents-verifier.yml`: exit **0**.
  Log: `native-context-window-actionlint.txt` (empty successful output).
- `git diff --check`: exit **0**. Full grammar suite was not rerun.

Regression paths:

```text
tests/scripts/test_native_capacity_recovery.py
tests/scripts/test_pr_verifier_recovery.py
tests/scripts/test_pr_verifier_config_and_report.py
tests/scripts/test_pr_verifier_structured_output.py
tests/scripts/test_pr_verifier_compare.py
tests/scripts/test_pr_verifier_comparison_report.py
tests/scripts/test_pr_verifier_fallback.py
tests/scripts/test_pr_verifier_sync_manifest.py
tests/workflows/test_verifier_evidence_profile.py
tests/tools/test_langchain_client.py
tests/scripts/test_validate_template_sync.py
tests/scripts/test_sync_manifest_compiler.py
tests/scripts/test_sync_manifest_docs.py
tests/workflows/test_sync_manifest_delivery.py
```

The coherent matrix checks exact input and combined-context boundaries and +1
overflows, smaller actual output, independent output overflow, Sonnet metadata
smaller/larger input bounds, missing/malformed context facts and actual payload
output limits, and receipts containing independent actual limits. It asserts no
generation on invalid capacity and matching native input/model at generation.
Existing unknown-model/transport/count failures and standard byte/behavior tests
remain green. Legacy synthetic fixtures retain their conservative fallback.

## Preservation and limits

Parent-owned changes were not edited; start/end SHA256 values match:

| Path | SHA256 |
| --- | --- |
| `config/template-drift-allowlist.txt` | `a5cb4f651e51f6053cbabb9ca93c831b7add90d4134bbee5c797d8acb0d1a518` |
| `pyproject.toml` | `e2e44246c722f6de4b6aa1b3d8d834824dee896e83472d3eb725f3656c7a9ddd` |
| `requirements.lock` | `bcb8ec1960b67c94112ebfdc8dbe57f35f7c4b038e543482f63cc23d830be879` |

Shared `tools/langchain_client.py` remains unchanged at
`7acec3daa1e48025d0d53d10b0c2fea6d2fc4aea1622323981ca8d8ed73c25d6`.
Existing native-capacity historical evidence/results were preserved; the existing
brief and prior untracked artifacts were not edited. Source, consumer template,
contract docs, sync-manifest coverage comments and expanded workflow fingerprints
were updated together. No production file was added to consumer delivery scope.

**Live provider capacity and verifier acceptance remain UNKNOWN/NONPASS.**
No GitHub/review/automation/assessor changes or authenticated provider calls were
made. The repair does not establish deployment, native counts on the new full
production payload, actual generation or either provider's verdict. Parent owns
publication, exact-head review/disposition, merge and live provider/fleet continuation.
