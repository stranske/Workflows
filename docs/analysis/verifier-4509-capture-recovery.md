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

Final named-command readback on committed test source
`b38f75409ac41e17baff6a13f1f4e6086ac8d85b` (2026-11-10): **exit 0,
325 passed / 0 failed, total wall time 5.025 seconds**. `PATH` selected
`/opt/anaconda3/bin/python3`. The subsequent documentation-only commit records
this result; test/fixture/collector bytes are unchanged. No full suite was run.

## Managed-runner regression follow-up (2026-11-10)

Two executable regressions now cover the previously recorded provider-free
investigation. The Node regression in
[`verifier-cross-repository-evidence.test.js`](../../.github/scripts/__tests__/verifier-cross-repository-evidence.test.js)
replays the five recorded native observations through `acquireRetainedExecution`.
It checks the exact canonical-origin refusal and confirms that no recovery archive
or origin receipt is written. These are offline observations, not a fresh native
admission. The source and consumer collectors remain unchanged.

The Python regression in
[`test_retained_verification_recovery.py`](../../tests/tools/test_retained_verification_recovery.py)
validates the exact retained ZIP digest and byte inventory, recomputes its required
gaps, checks the original event/assessment, and classifies both retained provider
slots through `validated_payload`. Provider-client builders fail the test if called.
The actual coverage remains **0 of 2 files for each provider**, with
`UNVERIFIABLE_INPUT` and output unavailable. Passing the exact archive to
`revalidate_retained` without an authenticated origin raises `FileNotFoundError`
for `verification-recovery-origin.json`; every original member remains unchanged.
This verifies the refusal, not successful native admission or complete capture.

This runner mounts `.git` read-only. `git add` failed before staging with
`Unable to create .../.git/index.lock: Read-only file system`, so no new commit
was created. The tested working tree is based on
`70bae977e1491aa29b979e449bea12b53d7e2bde`, with these changed test identities:

| File | Working-tree SHA-256 |
| --- | --- |
| `.github/scripts/__tests__/verifier-cross-repository-evidence.test.js` | `3ae023d133cf6b0a1ca56776caa0f958359bd97ad2bb3f6d10d81c6a9994edd6` |
| `tests/tools/test_retained_verification_recovery.py` | `13284226db4f0c1eb5512ec0beadc74c8bbdb1398cfa6d4faae2690206d13758` |

Validation in this runner:

- `PATH=/opt/hostedtoolcache/Python/3.14.10/x64/bin:$PATH node --test .github/scripts/__tests__/agents-verifier-context.test.js .github/scripts/__tests__/verifier-cross-repository-evidence.test.js`:
  **exit 1, total wall time 2.74 seconds**. The cross-repository file passes;
  the existing context file fails. Direct execution of the context file exposes
  `spawnSync git EPERM` and `spawnSync python3 EPERM` from existing subprocess
  tests. The pre-edit named-command baseline also failed (exit 1, 3.01 seconds,
  approved Python 3.13.18). This runner result does not replace the historical
  passing result on `b38f75409ac41e17baff6a13f1f4e6086ac8d85b` above.
- `PATH=/opt/hostedtoolcache/Python/3.14.10/x64/bin:$PATH node .github/scripts/__tests__/verifier-cross-repository-evidence.test.js`:
  exit 0, **116 passed**, 0 failed.
- `python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q`:
  exit 0, **1 passed**. Running the entire recovery test file gives 20 passed,
  6 failed; its unchanged HEAD version reproduces the same six lifecycle
  failures (19 passed, 6 failed). No existing test was disabled or changed.
- `python3 -m pytest tests/scripts/test_ci_history.py --cov=scripts.ci_history --cov-report=term-missing -m 'not slow' -q`:
  exit 0, **31 passed**, `scripts/ci_history.py` code coverage **73.55%**
  (95 statements, 23 missed, 26 branches, 3 partial). This supplemental code
  coverage is separate from the retained providers' zero review coverage.
- Black formatted the changed Python file at line length 100. Its default
  worker pool could not open its local socket; a sequential Black API check
  using the same CLI source selection verified all 999 files and populated a
  writable cache. The required full command then passed with
  `BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/verifier-4509-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`:
  exit 0, **999 files unchanged**. `git diff --check` also passed.

Successful native admission and complete required evidence remain unresolved.
No provider evaluation or public verification-state change was attempted, and
no additional operational acceptance checkbox is complete.

The requested `needs-human` label and blocker comment on PR #4631 were both
attempted but rejected by the connector: `MCP tool call requires approval, but
approval policy is never`. This report therefore retains the blocker locally.
Required follow-up is a runner with writable Git metadata and permitted local
subprocess IPC to commit and rerun these changes, plus authenticated canonical
recovery origin and complete required capture evidence before evaluation.
Final readback confirms PR #4631 is open with `draft=false`, still at
`70bae977e1491aa29b979e449bea12b53d7e2bde`.

## Keepalive round 2 readback — 2026-11-10

**Outcome: 0 accepted recoveries; NON_PASS remains.** Stop rule for this round:
two repair attempts or 25 minutes. No production repair was justified by the
reported CI failures. Authenticated run/job readback of
[run 42893223647](https://github.com/stranske/Workflows/actions/runs/42893223647)
shows `Resolve Context` (job `130099474097`) and `Record autofix dispatch
completion` (job `130099486638`) were **cancelled**, with empty step inventories;
the autofix job was skipped. These observations do not identify a script defect
or establish why the workflow was cancelled. A later
[run 42893224277](https://github.com/stranske/Workflows/actions/runs/42893224277)
has successful context resolution and skipped autofix/completion. No workflow
change or rerun was made to turn cancellation into a passing repair claim.

On committed source `70bae977e1491aa29b979e449bea12b53d7e2bde`, the named
Node command above exited **0**, with **325 passed / 0 failed**, in **5.097
seconds** total wall time. Python resolved to `/opt/anaconda3/bin/python3`.
Authenticated GETs at approximately 20:32 UTC reproduced the consumer 200,
wrong-repository 404, and verifier 200 with the same heads and completed/success
identities recorded above. The 404 remains non-authoritative for consumer absence.

The following provider-free readback is runnable from the repository root,
without relying on the investigation's earlier temporary extraction directory:

```sh
/opt/anaconda3/bin/python3 - <<'PY'
from pathlib import Path
import json, tempfile, zipfile
from tools.verifier_capture_obligation_manifest import (
    build_capture_obligation_manifest, validate_capture_byte_inventory,
)
from tools.verifier_corpus_evidence import event_metadata, validated_payload

with tempfile.TemporaryDirectory(prefix='verifier-4509-') as directory:
    p = Path(directory)
    with zipfile.ZipFile('.github/scripts/__tests__/fixtures/verifier-4509-capture.zip') as archive:
        archive.extractall(p)
    snapshot = json.loads((p / 'verifier-input-manifest.json').read_text())
    context = (p / 'verifier-context.md').read_bytes()
    diff = (p / 'verifier-pr-diff.patch').read_bytes()
    validate_capture_byte_inventory(snapshot['capture_byte_inventory'],
                                    {'context': context, 'diff': diff})
    obligations = build_capture_obligation_manifest(context.decode(), full_diff_bytes=diff)
    event = event_metadata(p / 'verification-event-manifest.json')
    comparison = json.loads((p / 'comparison.json').read_text())
    rows, verdict, available = validated_payload(comparison, mode='compare')
    print(obligations['sufficient'], verdict, available)
    print(event['verification_event']['event_id'])
    for result in comparison['results']:
        assert result['used_llm'] is False
        assert result['files_reviewed'] is None
        assert result['files_not_reviewed'] == ['scripts/ci_history.py', 'tests/scripts/test_ci_history.py']
    assert obligations['sufficient'] is False
    assert verdict == 'UNVERIFIABLE_INPUT' and available is False
    print('provider coverage: 0/2 files in both retained slots')
PY
```

This command exited **0** on the same source and printed
`False UNVERIFIABLE_INPUT False`, the unchanged event ID above, and zero coverage
for both provider slots. This is offline validation, **not** successful native
recovery admission. The earlier canonical-source refusal and required capture
gaps remain unresolved; T5's successful-admission requirement and A2 remain
unmet. Blocking/drainable pair: native exact-capture admission remains blocked;
offline hash, event, inventory, coverage and bounded-reproduction checks remain
available. This round made no collector changes, provider calls, original-event
mutations or dependency-pin edits. CodeRabbit's linked-issue objection about
unmet operational acceptance remains valid.

The remote branch advanced during this round to
`52ca352f99b2e1eb4f570400b95c3f9a9fdac031`; this local worktree fast-forwarded
and preserved the hosted runner's two added regressions. On that committed source,
the named Node command exited **0**, **326 passed / 0 failed**, **5.004 seconds**
total wall time with `/opt/anaconda3/bin/python3` selected. This supersedes the
hosted runner's environment-specific named-command failure for these source bytes.
The focused new Python regression was also checked locally:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q -o asyncio_default_fixture_loop_scope=function
```

The initial invocation without the explicit loop scope exited 3 during
pytest-asyncio configuration, before tests, because its unset-scope deprecation
is treated as an error. Selecting the scope in the invocation required no source
or dependency change. The explicit-scope invocation exited **0**, **1 passed**.
Only documentation changes follow this tested source in this round. No full
suite was run. T5 successful admission and A2 are still unmet; passing refusal
regressions do not resolve the captured operational failure.

## Native GET replay follow-up — managed runner (2026-11-10)

Fresh authenticated GitHub connector GETs reproduced all three observations in
the identity table: trip-planner run `42327976097` returned completed/success at
`948406465cf7cd65d1ac92206b4514aaad455443`; the same numeric ID under Workflows
returned 404; Workflows verifier run `42330898168` returned completed/success at
`aa7fe9537cb9c448a50b51ff6eb5da162fd819b1`. Repository and head-repository IDs,
attempts, update times, and reusable-workflow references match the retained
identity fixture. The wrong-repository 404 remains non-authoritative for consumer
absence. This rechecks run identity only, not archive acquisition or admission.

Six new regressions replay these three recorded GETs through both source and
template collectors. They check repository/head/attempt/conclusion, retain the
consumer's separate downstream role and completed status, and preserve the local
404. Artifact-list and discovery observations absent from the fixture explicitly
raise unavailable errors; the tests cannot fabricate an empty complete capture.
Both collectors retain an unavailable acceptance-evidence source and refuse to
download invented bytes. No production or template collector was changed.

Validation on base `65fd5eaa0d66c4c7be4c32141689280a7d68aaa7` plus the new
JavaScript tests (SHA-256
`398572b27391aaa71b3760f4e30160183ddd518cdbdb4c9dab45fe4e4bbd024a`):

- `PATH=/opt/hostedtoolcache/Python/3.14.10/x64/bin:$PATH node .github/scripts/__tests__/verifier-cross-repository-evidence.test.js`:
  exit 0; **122 passed**, including all six new native-GET replays.
- The issue-named combined `node --test` command with that same approved Python
  PATH: **exit 1, 4.89 seconds**. Before edits it also failed: exit 1,
  3.48 seconds. Direct context-file execution reports 193 passed / 17 failed,
  including `spawnSync git EPERM` and `spawnSync python3 EPERM`.
  This runner result does not supersede the recorded historical passing source.
- `python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q`:
  exit 0; **1 passed**, 25 deselected. Exact byte-inventory/event validation
  preserves required gaps, the original event, both unavailable provider slots,
  and the missing-origin refusal. Actual retained provider coverage remains
  **0 of 2 files per provider**; `UNVERIFIABLE_INPUT` remains non-PASS.
- `python3 -m pytest tests/scripts/test_ci_history.py --cov=scripts.ci_history --cov-report=term-missing -m 'not slow' -q`:
  exit 0; **31 passed**, script code coverage **73.55%**. This is separate from
  provider review coverage. Initial attempts with the previously documented
  asyncio loop-scope override exited 4 because this runner does not register
  that option; the successful commands above omit it.
- `git diff --check`: exit 0. No Python source changed.

Reconciliation of the recent commits supports checking the duplicate
endpoint-authentication task and historical named-command acceptance item.
The exact-capture regression also verifies the actual-coverage/non-PASS
acceptance item. Successful native admission and complete required capture
remain unchecked. The connector rejected the PR-body update with
`MCP tool call requires approval, but approval policy is never`; the proposed
reconciled body is retained at `/tmp/verifier-4631-reconciled-body.md`.

The required source commit is blocked: `git add` fails with
`Unable to create .../.git/index.lock: Read-only file system`. The JavaScript
changes remain in the working tree. A runner with writable Git metadata and
permitted subprocess execution must commit and rerun them. Complete required
capture evidence and authenticated canonical recovery origin are still needed
before any provider evaluation; no provider call or original-event mutation
was made.

The requested blocker comment and `needs-human` label were also rejected by the
connector with the same approval-policy error. Remote task state could not be
changed; the evidence and proposed reconciliation remain local.

## Round 3 exact-head validation and Gate attribution (2026-11-10)

Outcome: **0 accepted recoveries; UNVERIFIABLE_INPUT**. Before this round's
documentation edit, the operational target and command remained those at the top
of this report. The stop rule was three attempts at one broken step or 60 minutes.
Blocking/drainable pair: authenticated canonical recovery admission and required
capture completeness remain blocked; exact-byte offline validation and native
run-identity readback remain available. No recovery authority was manufactured.

The supplied failing Gate run
[`42896554486`](https://github.com/stranske/Workflows/actions/runs/42896554486)
belongs to **`65fd5eaa0d66c4c7be4c32141689280a7d68aaa7`**, not the round's
starting head `b9c8729c5bc13b9e1d687931a0dce0671ab0edd2`. Authenticated run/job
readback reports the run cancelled, both main Python matrix jobs cancelled, and
the summary failed at `Enforce explicit Gate success`. The Python 3.13 job log
prints `The operation was canceled`, then `CI checks failed: pytest cancelled`.
This establishes interrupted validation, not a demonstrated source assertion
failure. The cancellation initiator is unknown. No Gate check was weakened and
no workflow, collector or dependency pin was changed in response.

On committed source **`b9c8729c5bc13b9e1d687931a0dce0671ab0edd2`**, the exact
issue-named command above selected `/opt/anaconda3/bin/python3` and exited **0**:
**332 passed, 0 failed, 5.194 seconds** total wall time (Node-reported test
duration 4.997 seconds). This includes all six newly committed native-GET replays
that the previous managed runner could not run through the combined command.
The exact-capture regression also ran:

```sh
/opt/anaconda3/bin/python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q -o asyncio_default_fixture_loop_scope=function
```

Exit **0**, **1 passed, 25 deselected**, 0.28 seconds pytest duration. It verifies
the retained archive digest, inventory, original event, unresolved required gaps,
zero provider coverage of both named files and missing-origin recovery refusal.
No full suite ran. This documentation-only update preserves those tested bytes.

At **20:48 UTC**, fresh authenticated `gh api` GETs again returned consumer run
`42327976097` under trip-planner (repository ID `993784438`, head repository
`stranske/trip-planner`, attempt 1, completed/success, head
`948406465cf7cd65d1ac92206b4514aaad455443`) and verifier run `42330898168`
under Workflows (attempt 1, completed/success, head
`aa7fe9537cb9c448a50b51ff6eb5da162fd819b1`). Their update times match the
identity table above. The same consumer run ID under Workflows returned HTTP
404 again; it remains non-authoritative for consumer absence.

The current-head Gate run
[`42897764849`](https://github.com/stranske/Workflows/actions/runs/42897764849)
was still in progress at this readback. Its outcome is not inferred from the
older cancelled run or local tests. The capture remains incomplete, both retained
provider slots still reviewed **0 of 2 files**, and successful native recovery
admission is unproved. **T5 successful admission and A2 remain unmet.** This
round adds no provider calls or original-event mutations.

## Raw-member admission regression — managed runner follow-up

The exact first failing archive now passes through the existing Python
`load_artifact_capture` validator in
`tests/tools/test_retained_verification_recovery.py`. Five added cases use the
unchanged retained ZIP and independently recorded member hashes: complete raw
sidecars, missing archive, missing coverage member, same-length altered coverage
member, and incorrect member occurrence. No provider client can be constructed.

The successful case verifies all three member inputs and their archive/run/
artifact identities. In a **local derived inventory only**, semantic raw-capture
validation clears exactly
`acceptance_evidence:Run 42326161711: selftest-autofix-3.13:truncated`.
Five other required gaps remain and `sufficient=false`. Every defective case
retains all six original gaps and adds a raw-capture failure. The original
context, event, comparison and ZIP fixtures stay byte-identical; no native
origin or revalidation receipt is created. This advances offline validation of
one recovered archive, not successful exact-capture admission.

Validation on working-tree changes based on
`e4a090cf5f9a7adbf5e044505beece5317c721ea`, Python 3.14.10:

- Exact-capture tests: `python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q`:
  exit 0, **6 passed**, 25 deselected.
- Recovery and artifact tests together: `python3 -m pytest tests/tools/test_retained_verification_recovery.py tests/tools/test_verifier_artifact_capture.py -m 'not slow' --no-cov -q`:
  **36 passed, 6 failed**. The failures are the six previously documented
  authored lifecycle cases; no existing test was disabled or altered.
- `python3 -m pytest tests/scripts/test_ci_history.py --cov=scripts.ci_history --cov-report=term-missing -m 'not slow' -q`:
  exit 0, **31 passed**, **73.55%** script code coverage. Retained provider
  review coverage of both named files remains **0 of 2 per provider**.
- The named Node command, before edits, selected the installed approved Python
  3.14.10 runtime: exit 1, **4.350 seconds** total wall time. The cross-repository
  file passed; direct execution of the existing context tests reports subprocess
  `EPERM`. This does not supersede the historical passing committed-source result.
- Ruff and `git diff --check` pass. Black formatted the changed Python file at
  line length 100; full formatting validation is recorded below.

Acquiring additional archive bytes remains blocked in this runner. The GitHub
connector returned a download reference for artifact `13555815325`, but local
download failed with `URLError`; native `gh api` also cannot connect. No downloaded
bytes or new authenticated member hashes are claimed for that artifact. Canonical
native recovery admission remains unresolved, and no provider evaluation or
acceptance-checkbox update was attempted.

The unchanged HEAD recovery tests were separately replayed from a temporary
sibling test file (removed afterward): **20 passed, the same 6 failed**, exit 1.
Sequential Black validation using the CLI's source selection checked all 999
files, after the parallel command stalled in this restricted runner. With that
verified cache, the required full command passed:

```sh
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/verifier-4509-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Exit 0, **999 files unchanged**. The requested commit was then attempted, but
`git add` exited 128 with `Unable to create .../.git/index.lock: Read-only file
system`; no commit was created. Source and evidence changes remain in the
working tree. Both the `needs-human` label and blocker comment on PR #4631
were rejected by the connector:
`MCP tool call requires approval, but approval policy is never`.

Required follow-up: commit the tested changes on a runner with writable Git
metadata, retrieve the remaining exact archives with working network access,
and establish authenticated canonical admission before provider evaluation.
This round completes no additional operational acceptance checkbox.

## Semantic preflight follow-up — 2026-11-10

Reconciliation of commits through `47a2a605` and the live PR body confirms that
completed tasks are already checked. All four remaining admission/completeness
checkboxes remain unmet. PR #4631 was open with `draft=false` at readback.

The five exact first-archive cases now additionally exercise `_semantic_capture`
and `evaluate_pr_multiple`. Complete recovered members enter the semantic input
hash inventory; missing, altered or misidentified members do not. Every case
retains required gaps, `resource_admitted=false`, and a non-PASS comparison with
`used_llm=false` and no execution ledger. Client construction and invocation are
forbidden by test sentinels. Original event, comparison and archive bytes remain
unchanged. These checks advance partial-capture validation only.

Validation on changes based on `47a2a605`, Python 3.14.10:

- `python3 -m pytest tests/tools/test_retained_verification_recovery.py -k exact_4509 -m 'not slow' --no-cov -q`:
  **6 passed**, 25 deselected, exit 0.
- Recovery/artifact tests together with `-m 'not slow' --no-cov -q --tb=short`:
  **36 passed, 6 failed**, exit 1; the same six authored lifecycle failures
  documented in the preceding round remain. No tests were disabled or changed
  to bypass those failures.
- `python3 -m pytest tests/scripts/test_ci_history.py --cov=scripts.ci_history --cov-report=term-missing -m 'not slow' -q`:
  **31 passed**, exit 0; the `scripts/ci_history.py` row reports **73.55%**.
  Actual retained provider review coverage remains **0 of 2 files per provider**.
- Named Node command: exit 1, **5.423 seconds** elapsed, selecting
  `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3`. The cross-repository
  file passes; direct context-test execution confirms `spawnSync python3 EPERM`.
  This runner result does not supersede the recorded historical passing head.
- Ruff and `git diff --check` pass.

Artifact `13555815325` again returned a connector download reference, but fetching
its bytes failed with `URLError` caused by DNS resolution. No new archive bytes,
hashes, native recovery authority or provider calls are claimed. The connector
rejected the task-reconciliation PR-body update, `needs-human` label and blocker
comment with `MCP tool call requires approval, but approval policy is never`.

Black formatted the changed test at line length 100. The CLI's full source
selection was checked sequentially after its worker scheduling stalled in this
runner. The required command then passed against the verified cache:
`BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/verifier-4509-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
— exit 0, **999 files unchanged**.

The scoped commit was attempted after validation. `git add` exited 128 because
`.git/index.lock` cannot be created on the read-only Git metadata filesystem.
No commit was created; the test and report changes remain in the working tree.
Completion requires a runner with writable Git metadata, working archive
downloads and authenticated canonical recovery admission.

## Persisted capture-manifest validation — 2026-11-10

Reviewed the recent commits through `7824e504` and reconciled the live PR body:
the implemented tasks are already checked. Successful native admission and
complete required capture remain unverified; no additional checkbox is complete.
PR #4631 was open with `draft=false` at readback.

The five exact first-archive cases now also invoke the existing provider-free
`record_capture_obligations` path. They verify the serialized obligation
manifest, byte inventory and reassembly contract, including every raw member's
byte ranges when admitted. Missing, altered or misidentified sidecars contribute
no artifact input ranges. The reassembly contract retains the remaining required
gaps and `sufficient=false` in every case. A derived context paired with the
original input snapshot is rejected before any output is written; the snapshot
remains byte-identical. Standalone derived outputs use a separate temporary
directory and do not replace the original event, comparison or retained ZIP.
Provider construction and invocation remain forbidden by the test sentinels.

Validation on changes based on `7824e504`, Python 3.14.10:

- Exact-capture tests with `-k exact_4509 -m 'not slow' --no-cov -q`:
  **6 passed**, 25 deselected, exit 0.
- Recovery/artifact tests with `-m 'not slow' --no-cov -q --tb=short`:
  **36 passed, 6 failed**, exit 1; the failures are the same two authored
  publisher cases and four authored retry cases documented in preceding rounds.
- `python3 -m pytest tests/scripts/test_ci_history.py --cov=scripts.ci_history --cov-report=term-missing -m 'not slow' -q`:
  **31 passed**, exit 0; `scripts/ci_history.py` code coverage **73.55%**.
  Retained provider review coverage remains **0 of 2 files per provider**.
- Pre-edit named Node command: exit 1, **4.713 seconds** elapsed, selecting
  `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3`. The cross-repository
  file passed and the context file failed, consistent with the preceding
  restricted-runner results. No JavaScript or fixture bytes changed this round.
- Ruff and `git diff --check` pass. Black formatted the changed Python file
  at line length 100; full formatting-gate results follow below.

The connector supplied another download reference for artifact `13555815325`;
retrieving its bytes failed with `URLError` / DNS `gaierror`. No new authenticated
archive bytes, member hashes or native recovery authority were obtained. No
provider evaluation occurred. The PR-body reconciliation update and `needs-human`
label were both rejected: `MCP tool call requires approval, but approval policy
is never`. The operational acceptance remains **NON_PASS**.

Sequential Black validation with the CLI's configured source selection checked
all 999 files after the worker-based invocation stalled. The required full
command then passed with the verified cache:

```sh
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/verifier-4509-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Exit 0, **999 files unchanged**. The scoped staging attempt exited 128:
`.git/index.lock` cannot be created on the read-only Git metadata filesystem.
No commit was created. The blocker comment was also rejected by the connector
with the same approval-policy error. The changed test SHA-256 is
`501b637282bfa82ad2692eac00785c6ae2368cc82a4f53f5dbd40acff49941aa`.
Final PR readback: open, `draft=false`, head
`7824e504730eb715d4654c633acc85b71147a354`. Completion requires writable Git
metadata, functioning archive downloads and authenticated complete-capture native
admission; local test success supplies none of those missing authorities.
