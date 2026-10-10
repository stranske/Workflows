# Exact-model native capacity recovery — 2026-10-10

Source implementation and local validation are complete. **Live provider capacity
and verifier acceptance remain UNKNOWN/NONPASS until authenticated expanded
verification supplies valid native receipts, complete evidence and actual verdicts.**
No live count, model generation, GitHub write, commit, push, fleet change or
campaign scheduling action was performed by this offload.

## Scope and implementation

- Base/unchanged HEAD: `96528ac6b7888f4add72c72799128371c5230da2`.
- Expanded evaluate, each comparison arm and schema repair prepare only exact
  `gpt-5.6-terra` for Responses using a shallow client copy. The authenticated SDK
  objects, credentials, base URL, timeout and retry settings are retained. An
  absent output ceiling becomes 128000; explicit ceilings are preserved.
- Exact `claude-sonnet-5-5` retains Messages and its configured output ceiling.
  Each preflight retrieves exact Models API metadata through the same SDK root,
  validates model identity and positive integer input/output limits, then counts
  the complete Messages request. No OpenAI request uses the Anthropic counter.
- Source-owned facts use the owner's 2026-10-10 official-document capture:
  [Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
  (context 1050000/input 922000/output 128000),
  [Sonnet](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
  (nonbatch context 1000000/output 128000), and the native
  [Models API](https://platform.claude.com/docs/en/api/models/retrieve).
  [Responses counting](https://developers.openai.com/api/docs/guides/token-counting)
  establishes the supported native count shape and complete output-token reserve.
- Conservative policy is unchanged: `input_tokens + actual output reserve <=
  input bound`, even when that input bound is input-only. Terra at the full 128000
  reserve therefore admits at most 794000 input tokens. Sonnet uses the smaller
  native input/documented context bound. No model substitution, guessed limits,
  approximate count, truncation, evidence waiver or acceptance change occurs.
- Unknown exact models, foreign/custom transports, SDK/counter-root mismatches,
  query extensions, payload/model or profile identity mismatches, unsupported
  request fields, malformed/unavailable metadata/counts, output overflow and
  input overflow fail closed. Expanded generation auth failures cannot resolve
  an alternate judge. Existing SDK retries remain bounded by caller settings.
- Receipts bind provider/model, fact provenance, native endpoint and SHA256 of
  the complete generation request. A request changed during counting is refused.
- Shared builders are unchanged; standard keeps the original client, request
  bytes, auth fallback and schema-repair behavior. Standard fingerprint remains
  `bounded-native-capacity-v2`; expanded becomes `bounded-native-capacity-v3`.

## Deliberate RED / byte-identical restored GREEN

Tests construct the actual verifier-balanced registry selections with dummy
credentials, without modifying those selections. They cover evaluate, comparison
and schema repair for both providers. Only count/metadata/generation results are
simulated; they are not live verdicts.

1. Before repair, the six configured-client behavior regressions failed with the
   original missing-profile block. Command:
   `python -m pytest tests/scripts/test_native_capacity_recovery.py -q -o addopts=
   --junitxml=evidence/issue-3820/native-capacity-red.xml`
   Exit **1**, **6 failed**; transcript `native-capacity-red.txt`.
2. After repair, deliberately reintroduced the production failure at the start
   of `_native_capacity_contract` in `scripts/langchain/pr_verifier.py`:

   ```python
   if getattr(client, "profile", None) is None:
       raise InputCapacityError("model-specific capacity profile unavailable")
   ```

   Command:
   `python -m pytest tests/scripts/test_native_capacity_recovery.py::test_configured_native_expanded_reaches_count_and_generation -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-mutation-red.xml`
   Exit **1**, **6 failed** during the production mutation.
3. Removed exactly that mutation with `apply_patch`, verified byte-identical
   restoration, and reran the identical test target with JUnit path
   `native-capacity-restored-green.xml`. Exit **0**, **6 passed**.

Production script SHA256:

| State | SHA256 |
| --- | --- |
| Original base | `cd868298de417cd944d8e887827dbac55f7a4bd1ada987ce2f9498471af05c12` |
| Repaired before mutation | `97627c429bc2c020062ad98213b6b948aa144ec6dad755d7d8fc1ad7a9462874` |
| Deliberately broken | `ae0533523141bc120a4b77f8279a47bd6e38e85d416a7487fab2aac68c76ed1d` |
| Restored/final source and template | `97627c429bc2c020062ad98213b6b948aa144ec6dad755d7d8fc1ad7a9462874` |

Shared `tools/langchain_client.py` SHA256 is unchanged from base:
`7acec3daa1e48025d0d53d10b0c2fea6d2fc4aea1622323981ca8d8ed73c25d6`.

## Completed checks

- Native suite:
  `python -m pytest tests/scripts/test_native_capacity_recovery.py -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-green.xml`
  — exit **0**, **124 passed, 6 skipped**. Six skips are Anthropic-only metadata
  cases under the OpenAI parameter. Covers actual SDK HTTP serialization over
  `httpx.MockTransport`, matching count/generation native paths, roles/input,
  instructions/system, tools, reasoning/thinking, response formats, output
  preservation, exact boundaries, identity/transport failures, repair and standard
  compatibility. Real SDK generation and response parsing run on the HTTP fixture.
- Bounded broader regression (19 files, explicit argument list below), with
  `-n 4 -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-focused-regression.xml`
  — exit **0**, **4501 passed, 8 skipped**. Besides the six provider-specific
  skips, authenticated capture replay requires the owner's capture directory and
  live manifest issue-reference validation requires a GitHub token.
- Final workflow fingerprint check after multiline-only workflow formatting and
  adding runtime standard/expanded fingerprint checks:
  `python -m pytest tests/workflows/test_verifier_evidence_profile.py -q -o addopts= --junitxml=evidence/issue-3820/native-capacity-workflow.xml`
  — exit **0**, **40 passed**.
- `python -m black --check --target-version py312 <seven changed Python files>`
  — exit **0**. `python -m ruff check <same files>` — exit **0**. Files are the
  source/template verifier, new scripts conftest/native suite, recovery suite,
  capacity fakes and workflow evidence-profile suite. Transcripts retained.
- `actionlint -shellcheck= -pyflakes= .github/workflows/reusable-agents-verifier.yml templates/consumer-repo/.github/workflows/agents-verifier.yml`
  — exit **0**. Embedded Python behavior is covered by workflow tests.
- `python scripts/validate_template_sync.py` — exit **0**;
  verifier source/template byte equality is also checked directly and by tests.
  `git diff --check` — exit **0**. Changed YAML parses successfully.
- Inspected `scripts/sync_templates.sh`; did **not** invoke its broad copy/remove
  loop. Used `apply_patch` for the bounded source/template changes. Existing
  manifest ownership covers both workflow/template and verifier delivery; no new
  production file or delivery-scope change was introduced.

Broader regression arguments (following `python -m pytest`):

```text
tests/scripts/test_pr_verifier_prompt_coverage.py
tests/scripts/test_pr_verifier_config_and_report.py
tests/scripts/test_pr_verifier_recovery.py
tests/scripts/test_pr_verifier_structured_output.py
tests/scripts/test_pr_verifier_compare.py
tests/scripts/test_pr_verifier_comparison_report.py
tests/scripts/test_pr_verifier_fallback.py
tests/scripts/test_pr_verifier_issue_creation.py
tests/scripts/test_pr_verifier_infra_detection.py
tests/scripts/test_pr_verifier_sync_manifest.py
tests/scripts/test_pr_verifier_chain_depth.py
tests/scripts/test_pr_verifier_evidence_alternatives.py
tests/scripts/test_native_capacity_recovery.py
tests/workflows/test_verifier_evidence_profile.py
tests/tools/test_langchain_client.py
tests/scripts/test_validate_template_sync.py
tests/scripts/test_sync_manifest_compiler.py
tests/scripts/test_sync_manifest_docs.py
tests/workflows/test_sync_manifest_delivery.py
```

An initial all-`test_pr_verifier*.py` attempt was interrupted after **4868 passed**
in 99.28 seconds (shell exit **130**), because unrelated destination/body grammar
cross-products dominate that suite. Its transcript/JUnit remain as
`native-capacity-regression.*`; it is **not** a completed full-suite PASS. The
19-file bounded suite above completed. Broad restricted-assessor tests were not run.

## Evidence hashes and remaining limits

| Transcript | SHA256 |
| --- | --- |
| `native-capacity-red.txt` | `8eea4e5c9700964101cbcb789a1cd01b2c8aed67ba2071031eaa52149b4e571a` |
| `native-capacity-mutation-red.txt` | `7c9c2a71b909e94e07e1c31e031b6e5cbfc28b0664ad216c8e9ee762a2f38b53` |
| `native-capacity-restored-green.txt` | `58d5a409d060413c8d9ff6a6294be4ed9734708c5bc72f1548afafded130f173` |
| `native-capacity-green.txt` | `0e115e76f0a2a13d7074622373e342a21a584000658d3288cb222a336d514041` |
| `native-capacity-focused-regression.txt` | `2db60cd7c9390fc907ed5680a86ad30ab94dea5cb4dd9d0e7d4ebae7f36393b6` |
| `native-capacity-workflow.txt` | `1b64970264403ccf3711b75db613430e80bcdf7743af344bfe49b0ad8b6cecf2` |

Local installed versions: langchain-openai **1.3.2**, langchain-anthropic **1.4.6**,
openai **2.32.0**, anthropic **0.96.0**, pytest **9.1.1**, Black **26.5.1**, Ruff
**0.16.7**. The local LangChain versions are older than this repository's declared
optional dependency minima; hosted dependency resolution and private SDK payload
API compatibility remain live validation gaps. Missing/malformed future SDK
capabilities fail closed. Parser/response fakes use an explicit test-only contract
fixture; configured-adapter/native HTTP regressions do not bypass production binding.

No authenticated provider calls were attempted. Live exact-model access, Sonnet
metadata, native counts on full captured production payloads, transport success,
actual generation, full retrieval/evidence floors and both provider verdicts remain
unverified. Count PASS is neither model generation nor acceptance. Parent retains
hosted verification and publication ownership; no source delivery/deployment or
provider UNKNOWN resolution is claimed here.

## Changed paths

```text
.github/sync-manifest.yml
.github/workflows/reusable-agents-verifier.yml
docs/WORKFLOW_GUIDE.md
docs/ci/WORKFLOWS.md
docs/ops/CONSUMER_REPO_MAINTENANCE.md
scripts/langchain/pr_verifier.py
templates/consumer-repo/.github/workflows/agents-verifier.yml
templates/consumer-repo/scripts/langchain/pr_verifier.py
tests/scripts/conftest.py
tests/scripts/test_native_capacity_recovery.py
tests/scripts/test_pr_verifier_recovery.py
tests/scripts/verifier_capacity_fakes.py
tests/workflows/test_verifier_evidence_profile.py
evidence/issue-3820/native-capacity-recovery.md
evidence/issue-3820/native-capacity-*.txt
evidence/issue-3820/native-capacity-*.xml
```

The pre-existing untracked `capacity-recovery-brief.md` was preserved unchanged.

## Source-owner publication notes

The owner inspected the complete patch and corrected the documentation's stale
claim that bundled profiles are always absent: hosted SDK 1.4.1 can supply Terra
facts, but those alone do not establish the native count contract. The existing
#3821 deterministic fixture repair will be reconciled before publication.

Deliberate RED and restored GREEN raw transcripts and JUnit are committed without
altering their bytes. They contain pytest traceback trailing whitespace; the
worker's pre-staging diff-check result covered tracked source changes, not these
then-untracked logs. Whole staged diff-check cleanliness is therefore not claimed.
The large focused/full-interrupted JUnit files and ancillary lint logs remain
durable owner-local evidence, not committed acceptance deliverables. The committed
focused transcript and this document retain their actual scope and interrupted
full-suite status. No live provider PASS is claimed.
