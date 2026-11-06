## Why (verified evidence)

`Runner.xlsm` shows two operator action labels in row 5 that have **no** Form Control button and **no** VBA handler, so Excel operators see affordances that do nothing when clicked (only the adjacent wired buttons work).

- `scripts/build_runner_workbook.py:57-66` writes labels for `D5` ("Dry-Run Discovery") and `I5` ("Ask about this run") via `_ACTION_CELLS`, but `_RUNNER_ACTION_BUTTONS` (`:94-102`) only defines buttons for A5–C5 and E5–H5 — skipping D5 and I5.
- `tests/test_runner_workbook.py:43-63` encodes this: `EXPECTED_RUNNER_ACTION_CELLS` includes D5 and I5, while `EXPECTED_RUNNER_BUTTONS` omits both (only seven macros).
- `assets/vba/RunnerLaunch.bas:30-127` defines `RunAll_Click` … `OpenPPTFolder_Click` only; no `DryRunDiscovery_Click` or `AskAbout_Click`.
- `docs/PRODUCT_CONTRACT.md:20` documents the `Ask about this run` gap for operators.

User-facing consequence: a non-technical operator clicking "Dry-Run Discovery" or "Ask about this run" in Excel gets no action and may assume the runner is broken.

## Reproduction

1. Build or open the shipped `Runner.xlsm` (see `tests/test_runner_workbook.py` builder).
2. On the `Runner` sheet, compare cells D5 and I5 to E5: D5/I5 are plain labels without embedded Form Controls; E5 has a wired button invoking `OpenOutputFolder_Click` (see VML macro list in `tests/test_runner_workbook.py:386-401`).

Expected: every action label in row 5 either launches its macro or is removed. Observed: D5 and I5 are labels only.

## Tasks

- [ ] Add `RunnerActionButton` entries in `scripts/build_runner_workbook.py:94-102` for `D5` (`DryRunDiscovery_Click`) and `I5` (`AskAbout_Click`), updating VML/control counts consistently with existing buttons.
- [ ] Implement `Public Sub DryRunDiscovery_Click()` in `assets/vba/RunnerLaunch.bas` that launches the same CLI dry-run discovery path the Tk GUI uses (`counter-risk run --dry-run-discovery` with runner settings JSON), surfacing errors via existing `LaunchStatus` formatting.
- [ ] Implement `Public Sub AskAbout_Click()` in `assets/vba/RunnerLaunch.bas` that opens operator-facing run Q&A for the latest run folder (reuse the chat/session entry point the repo documents for run review; if only maintainer CLI exists, show a clear message naming `counter-risk gui` rather than a no-op).
- [ ] Extend `tests/test_runner_workbook.py` `EXPECTED_RUNNER_BUTTONS` to require macros on D5 and I5 and assert the VBA project exports the two new `Public Sub` names.

## Acceptance Criteria

- Named test: `pytest tests/test_runner_workbook.py -q` passes (including updated button expectations for D5 and I5).
- Deliberate-break → revert: remove the new `RunnerActionButton` for `I5` from `scripts/build_runner_workbook.py` → confirm `tests/test_runner_workbook.py` FAILS → revert → passes.

## Non-Goals

- Do NOT remove the seven existing wired buttons or change their macro names.
- Do NOT add network egress in CI; VBA/OOXML tests stay headless as today.
- No scaffolding / TODO-only changes; every task is a concrete edit verified by the gate above.

_Surfaced by Track D audit 2026-10-24; verified by reading cited paths on tip `affd8bf`._

## Owner clarification (2026-11-06)

Decided under the owner's delegation during the needs-human catalog review; it resolves the earlier park.

The acceptance criteria are `pytest tests/test_runner_workbook.py -q` and its deliberate break, which run without Excel. Native Excel validation is out of scope for this issue.

