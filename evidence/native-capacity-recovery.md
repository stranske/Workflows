# Native capacity recovery — reviewer remedy adopted

Workflows#3822 Codex finding `4238407535` is correct: committed source
`c5e4fe99ddaf87f98c7eb5d2d6dcabf749409bfb` reserved Terra's output twice,
rejecting valid native inputs above 794000 with the full 128000 output ceiling.
The source repair independently enforces:

- Terra: native input <= **922000**, native input + actual request output ceiling
  <= **1050000**, and output <= **128000**.
- Sonnet: native input <= **exact Models API max_input_tokens**, native input +
  actual request output ceiling <= **1000000**, and output <= both the exact
  Models API and documented **128000** ceilings.

Real native contracts require explicit positive integer input/context/output
facts. The conservative fallback applies only to legacy synthetic unit contracts
without a context fact. Missing or malformed real facts, counts or actual request
output limits remain fail-closed. The existing exact-model/transport binding and
same-payload native count/generation check remain enforced. Standard is unchanged;
expanded fingerprints advance to `bounded-native-capacity-v4` to invalidate the
old input contract.

[Production RED/restored GREEN and validation](issue-3820/native-context-window-repair.md)
record the new proof. The earlier
[native recovery evidence](issue-3820/native-capacity-recovery.md) retains its
historical hashes, results and publication notes; its conservative sum policy and
v3 fingerprint are superseded by this reviewer remedy. Its old SDK-version gap is
addressed locally by the locked newer SDK tests, not by live provider acceptance.

**Provider capacity and acceptance remain UNKNOWN/NONPASS.** No authenticated
provider calls, GitHub/review/automation changes, commits or pushes were made.
Parent-owned metadata changes were preserved byte-for-byte. Exact-head review,
publication, merge, live provider validation and fleet continuation remain with
the parent.

## Changed paths in this offload

```text
.github/sync-manifest.yml
.github/workflows/reusable-agents-verifier.yml
docs/WORKFLOW_GUIDE.md
docs/ci/WORKFLOWS.md
docs/ops/CONSUMER_REPO_MAINTENANCE.md
scripts/langchain/pr_verifier.py
templates/consumer-repo/.github/workflows/agents-verifier.yml
templates/consumer-repo/scripts/langchain/pr_verifier.py
tests/scripts/test_native_capacity_recovery.py
tests/workflows/test_verifier_evidence_profile.py
evidence/native-capacity-recovery.md
evidence/issue-3820/native-capacity-recovery.md
evidence/issue-3820/native-context-window-repair.md
evidence/issue-3820/native-context-window-*.txt
evidence/issue-3820/native-context-window-*.xml
```

The wildcard artifacts contain new local diagnostics, deliberate RED/restored
GREEN, final native/regression/capture JUnit and lint/parity transcripts. Parent
owns selection of raw diagnostics for publication. Existing parent changes to
`config/template-drift-allowlist.txt`, `pyproject.toml`, `requirements.lock` and
the old untracked artifacts are excluded from this offload's changes.
