# Exact #4509 retained-capture investigation

Checked 2026-11-10 UTC for #4630. **Outcome: 0 accepted recoveries; NON_PASS
(`UNVERIFIABLE_INPUT`).** This report recovers the exact retained inputs and
reproduces the demonstrated archive failure. It does **not** certify a complete
capture or provider acceptance. No collector defect requiring a source/template
change was demonstrated; #4624's routing implementation remains unchanged.

The operational target is an authenticated, complete #4509 capture admitted by
the existing provider-free recovery path, with actual review coverage recorded
for both `scripts/ci_history.py` and `tests/scripts/test_ci_history.py` before
claiming acceptance. The exact bounded regression command is:

```sh
PATH=/opt/anaconda3/bin:$PATH node --test .github/scripts/__tests__/agents-verifier-context.test.js .github/scripts/__tests__/verifier-cross-repository-evidence.test.js
```

Stop rule recorded before edits: at most three attempts at the same failing
recovery step, or 60 minutes of investigation. One native recovery acquisition
was attempted; it refused before evaluation. No provider was invoked, public
verification state changed, or original event rewritten. No new gate was added.
Blocking/drainable pair: retained canonical-origin admission is blocked;
authenticated archive retrieval, hashing and offline reproduction remain
available and were completed. Local archive possession does not supply the
missing native recovery authority.

## Authenticated identities

Authenticated GitHub GET observations at 2026-11-10 20:07:43–20:07:44 UTC are
retained in the [identity fixture](../../.github/scripts/__tests__/fixtures/verifier-4509-capture-identity.json).
These selected observations and immutable ZIPs are offline fixtures, not live API
responses when tests run.

| GET endpoint | Observation |
| --- | --- |
| `repos/stranske/trip-planner/actions/runs/42327976097` | 200; repository/head repository `stranske/trip-planner`, ID `993784438`; head `948406465cf7cd65d1ac92206b4514aaad455443`; attempt 1; completed/success; updated `2026-11-07T02:16:25Z` |
| `repos/stranske/Workflows/actions/runs/42327976097` | 404; wrong-repository observation, **not authoritative for consumer absence** |
| `repos/stranske/Workflows/actions/runs/42330898168` | 200; repository/head repository `stranske/Workflows`, ID `1117447156`; head `aa7fe9537cb9c448a50b51ff6eb5da162fd819b1`; attempt 1; completed/success; updated `2026-11-07T02:49:20Z`; event `pull_request_target` |

The consumer references `reusable-10-ci-python.yml@main` at
`37e230009cdba04743376410c9f72356b85fb64f` (the evaluated Workflows merge).
The verifier references `reusable-agents-verifier.yml@main` at
`dfa7743b1c22a648a49e3500c084efaf5a9880c9`.
A successful Actions conclusion does not establish a successful assessment.

The original diagnostic's **first recorded failure** is the legacy lookup of
consumer run `42327976097` under **Workflows**, failure kind `provenance`, HTTP
404. No consumer artifact/member identity or hash was obtained by that failed
lookup. Repository-aware routing was already repaired in #4624; this investigation
does not repeat that work.

## Retained verifier archive and original event

Retrieved through authenticated Actions artifact discovery/download:

- Repository/run/attempt: `stranske/Workflows` / `42330898168` / `1`.
- Artifact: `13556839741`, `comparison-results-42330898168`, 18,725 bytes;
  not expired at retrieval; API expiry `2026-11-14T02:48:31Z`.
- API digest and downloaded ZIP SHA-256 both:
  `539f5843e83cda38afc9944d7f2a705f1105fc9a53c93380885a9e6a9407de82`.
- [Unchanged retained ZIP](../../.github/scripts/__tests__/fixtures/verifier-4509-capture.zip).
  The regression uses the existing strict `readRetainedArchive` reader, validates
  context/diff/summary/result hashes, and preserves the original diagnostics.
- Original event ID:
  `872cfa6b5cc9d664566f1aa1ecb5dbeaf303b27bd5a96288414318455a343e9c`.
- Request hash: `43f3295fe15943eedad43da38f62e7ece5664b3e1f0f3ba7c1b192a494b5b817`.
- Material hash: `7d915878579030ea5e25ad96a29ecfbe9328366be332cb942cfdbc7b0e5c0e37`.
- Original evaluated merge: `37e230009cdba04743376410c9f72356b85fb64f`.

All nine original members are retained, including the empty stderr file:

| Member | Bytes | SHA-256 |
| --- | ---: | --- |
| `comparison.json` | 6531 | `d80fa4d6bcbbd6b9da438d0d246e8f895ad3fcab5b88d2f6f49c5ee7630d0e14` |
| `comparison-execution.json` | 573 | `fb92f9e07e8c7201ff2d337ca9cf1c4dc774ff444c56bbf9df16369437cf5efd` |
| `comparison-stderr.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `comparison-comment.md` | 3258 | `d9b6dcb4afe5c8c3c719fc3d5cd562501daccbbe5e1bf4e267c88ecc163be723` |
| `verifier-context.md` | 58338 | `d95aa55c4564bc68cc60e3e22d18a6df3098b4b38a76fc71ed8111dd41817718` |
| `verification-event-manifest.json` | 2323 | `c43fffea57d962f31cfcb5516fd85a846cc334a207fd6e5e57b333a7f5f7b200` |
| `verifier-diff-summary.md` | 297 | `a5f68ac896014a748afa1787e3089b41a54695cf3d220881eb2d5415a0d92971` |
| `verifier-pr-diff.patch` | 3177 | `fd6347f5a0f4b02bc203d77570f4ae619080a243d3f648af43f59ae4180458c7` |
| `verifier-input-manifest.json` | 14873 | `db3738ad7a3f1f2a5ba329bfcdf8378c853fd387bbd54b024837cd622cccf86d` |

The archive's only diagnostics are embedded in `verifier-context.md`; there is
no separate diagnostics member. Their exact JSON is also retained in the identity
fixture. The retained capture contains no raw acceptance-archive sidecars.

## First archive/member extraction failure

The first incomplete archive in those original diagnostics is:

- Repository/run: `stranske/Workflows` / `42326161711`.
- Artifact `13556090021`, `selftest-autofix-3.13`; head
  `aa7fe9537cb9c448a50b51ff6eb5da162fd819b1`.
- Authenticated metadata/download: 532,746 bytes; API digest and actual SHA-256
  `6ba8c5ffd5985b5d5cb45e74412abb7f7fddcfe282b3b57158c635293a56de2b`.
- [Unchanged first failing ZIP](../../.github/scripts/__tests__/fixtures/verifier-4509-selftest-autofix-3.13.zip).
- Original listing SHA-256:
  `708415d03d7be26b17fb565a89b7296fc786cf29ef76c1d2cea9b0c1ca98206d`.

| Member / occurrence | Original status | Authenticated extracted bytes / SHA-256 |
| --- | --- | --- |
| `pytest-junit.xml` / 0 | included | 1,679 / `a0b0e0999af2ea2b229bda1605ced9e2b3d6f032acee3fb0321006917e88c7c2` |
| `coverage.xml` / 1 | unavailable, `extraction_byte` | 2,551,782 / `cf5f412e919487acf8b1249884174c3f4b69906419a60d681ce436fddcbe799e` |
| `coverage.json` / 2 | unavailable, `extraction_byte` | 3,899,648 / `e161e4423ef2eb296c6ec58eb2885ceaa785f3b28faf746583bc72f52e3d6c54` |

The coverage member sizes/hashes were recovered from the authenticated ZIP in
this investigation; they were **unknown in the original incomplete capture**.
The original standard limit was 60,000 characters, with a 240,000-byte extraction
allowance. The existing extractor additionally bounds each non-capture `unzip -p`
read by remaining rendered characters. `coverage.xml` exceeds those limits.
The faithful regression passes the exact archive bytes and original limits to
both source/template extractors and matches every original member record and
listing hash. This is a demonstrated bound, not evidence of corrupt ZIP bytes.

A second regression exercises the already-existing raw capture directory path,
with its existing 67,108,864-byte cumulative allowance. It retains and independently
hashes all three exact members. The rendered view still reports `character`
truncation. This proves recovery of **this archive's raw bytes only**, not all
original inputs, semantic acceptance, or a complete original capture. It justifies
no production collector change or global budget increase.

Other original incomplete artifacts remain recorded without being silently
cleared: `13555815325`, `13556432562`, `13555867095`, `13555456977`, and
`13555184662`. The frozen contract retains four truncated selftest evidence
sources plus `acceptance_evidence:artifacts:integrity_failure_or_unknown_kind`
and `acceptance_evidence:artifacts:unavailable`.

## Provider-free recovery validation

The existing `acquireRetainedExecution` path was invoked with authenticated
read-only `gh api` transport, original event/assessment and selector
`{"run_id":42330898168,"run_attempt":1,"artifact_id":13556839741}`.
Its `currentRun=42330898169` was explicitly a **local sequence sentinel**, not a
claim that this investigation ran in or authenticated a new Actions job. No
origin file was manufactured and no publication authority was acquired.
The adapter called only these native endpoints before refusing:

```text
repos/stranske/workflows/actions/runs/42330898168
repos/stranske/workflows/actions/runs/42330898168/attempts/1
repos/stranske/workflows
repos/stranske/workflows/commits/main
repos/stranske/workflows/compare/aa7fe9537cb9c448a50b51ff6eb5da162fd819b1...e99195408b0d916c14c2c2f34a4b7a0a91ef8fb9
```

Process exit: **1**. First broken recovery step:
`Retained helper/workflow revision is not canonical merged source`.
The authenticated comparison is `diverged`, with base
`aa7fe9537cb9c448a50b51ff6eb5da162fd819b1` and merge base
`75d4c8360c7a31db51366ca08d736cf4be1bc894`. The original is a
`pull_request_target` run reporting a squash-merged PR head. The retained-recovery
path deliberately keeps its strict canonical-origin check, as documented in
[verification events](../keepalive/VERIFICATION_EVENTS.md#provider-free-retained-output-recovery).
The separate provenance path's opt-in origin witness was not used to weaken
recovery. This refusal precedes Python revalidation/publication; no end-to-end
native recovery success is claimed.

Independently, these existing provider-free validators were applied to the exact
retained archive's members using `/opt/anaconda3/bin/python3` at source
`e99195408b0d916c14c2c2f34a4b7a0a91ef8fb9`:

```python
from pathlib import Path
import json
from tools.verifier_capture_obligation_manifest import (
    build_capture_obligation_manifest, validate_capture_byte_inventory,
)
from tools.verifier_corpus_evidence import event_metadata, validated_payload

p = Path('/private/tmp/issue-4630/original')  # extracted unchanged retained ZIP
snapshot = json.loads((p / 'verifier-input-manifest.json').read_text())
context = (p / 'verifier-context.md').read_bytes()
diff = (p / 'verifier-pr-diff.patch').read_bytes()
validate_capture_byte_inventory(snapshot['capture_byte_inventory'],
                                {'context': context, 'diff': diff})
obligations = build_capture_obligation_manifest(context.decode(), full_diff_bytes=diff)
event = event_metadata(p / 'verification-event-manifest.json')
rows, verdict, available = validated_payload(
    json.loads((p / 'comparison.json').read_text()), mode='compare')
print(obligations['sufficient'], verdict, available)
print(event['verification_event']['event_id'])
```

Exit 0; printed `False UNVERIFIABLE_INPUT False` and the unchanged original event
ID. Byte inventory validation succeeded; required capture integrity did not.
These functions parse retained evidence and construct no provider clients.

## Actual provider coverage and remaining acceptance

| Retained provider | Provider invoked | `scripts/ci_history.py` | `tests/scripts/test_ci_history.py` | Verdict |
| --- | --- | --- | --- | --- |
| openai / gpt-6.1-sol | `used_llm=false` | not reviewed | not reviewed | UNVERIFIABLE_INPUT |
| anthropic / claude-sonnet-5-5 | `used_llm=false` | not reviewed | not reviewed | UNVERIFIABLE_INPUT |

For each provider `files_reviewed=null` and `files_not_reviewed` names both files:
actual coverage is **0 of 2**, despite both changed-code patches being included
in the capture. The present investigation adds zero provider calls. It preserves
the original comparison, execution receipt, event, gaps and non-PASS verdict.
The original CI material also records a cancelled `selftest-ci.yml` run; successful
archive transport cannot clear that independent historical acceptance boundary.

- Retrieved capture/diagnostics, authenticated both run endpoints, and recorded
  first failure identities/hashes: complete.
- Faithful bounded production-archive regressions: complete; no production change
  warranted by the reproduced extraction limit.
- Named test command: 325 passed, exit 0, 4.961 seconds during implementation;
  baseline before changes: 320 passed, exit 0, 4.966 seconds.
- Provider-free validation and actual provider coverage recorded: complete as a
  **non-PASS investigation**, not an accepted recovery.
- **Unmet #4630 acceptance:** complete required capture and successful native
  recovery admission have not been established. No provider evaluation was
  attempted while those gaps remain. This PR must not be treated as proof that
  the exact #4509 operational recovery succeeded.
