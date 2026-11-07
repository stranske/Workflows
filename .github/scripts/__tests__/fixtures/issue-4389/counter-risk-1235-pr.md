### Keepalive: ON
<!-- meta:issue:1183 -->

### Source Issue #1183: [P2] Runner.xlsm Dry-Run and Ask-about labels have no Form Control or VBA handler

Closes #1183

Head: cursor/issue-1183

Opened by opener-core so cursor engages (invite-mode intake).

<!-- pr-preamble:start -->
<!-- meta:issue:1183 -->
> **Source:** Issue #1183

Closes #1183

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [x] Add `RunnerActionButton` entries in `scripts/build_runner_workbook.py:94-102` for `D5` (`DryRunDiscovery_Click`) and `I5` (`AskAbout_Click`), updating VML/control counts consistently with existing buttons.
- [x] Implement `Public Sub DryRunDiscovery_Click()` in `assets/vba/RunnerLaunch.bas` that launches the same CLI dry-run discovery path the Tk GUI uses (`counter-risk run --dry-run-discovery` with runner settings JSON), surfacing errors via existing `LaunchStatus` formatting.
- [x] Implement `Public Sub AskAbout_Click()` in `assets/vba/RunnerLaunch.bas` that opens operator-facing run Q&A for the latest run folder (reuse the chat/session entry point the repo documents for run review; if only maintainer CLI exists, show a clear message naming `counter-risk gui` rather than a no-op).
- [x] Extend `tests/test_runner_workbook.py` `EXPECTED_RUNNER_BUTTONS` to require macros on D5 and I5 and assert the VBA project exports the two new `Public Sub` names.

#### Acceptance criteria
- [x] Named test: `pytest tests/test_runner_workbook.py -q` passes (including updated button expectations for D5 and I5).
- [x] Deliberate-break → revert: remove the new `RunnerActionButton` for `I5` from `scripts/build_runner_workbook.py` → confirm `tests/test_runner_workbook.py` FAILS → revert → passes.

<!-- auto-status-summary:end -->
