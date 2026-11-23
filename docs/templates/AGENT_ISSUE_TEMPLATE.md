# Agent Issue Template

Use the [Workflows issue chooser](https://github.com/stranske/Workflows/issues/new/choose)
to file an issue. The [structured Agent task form](../../.github/ISSUE_TEMPLATE/agent_task.yml)
and [Markdown starter](../../.github/ISSUE_TEMPLATE/agent-task.md) show the live
intake fields. The [validator](../../.github/scripts/issue_format.py) defines
the accepted issue format. The [issue format guide](../ci/ISSUE_FORMAT_GUIDE.md)
offers writing guidance.

## ⚠️ Critical Rule: Checkbox Conversion

Use unchecked Markdown checkboxes (`- [ ]`) for Tasks and Acceptance Criteria.
Intake can normalize plain bullets in those sections into checkboxes. Put
background, instructions and notes in Why, Scope or Implementation Notes.

## Template Structure

Describe the problem in **Why** and identify the affected files or behavior in
**Scope**. Use **Non-Goals** to bound the change. Give each **Tasks** item a
concrete target such as a file or symbol. Name at least one runnable check in
**Acceptance Criteria**, such as a named test. Put execution details in
**Implementation Notes**.

## Section Reference

### Required Sections

| Use this heading | What to write |
| --- | --- |
| Tasks | Checkboxes with concrete files, symbols, paths, configuration keys, jobs or commands. |
| Acceptance Criteria | Checkboxes that include at least one named test or runnable verification command. |

### Recommended Sections

Use **Why**, **Scope**, **Non-Goals** and **Implementation Notes** for context.
The validator reports these sections as recommendations.

## Guidelines for Verifier Follow-Up Issues

### 1. Reference the Source

Link the original pull request, parent issue and relevant verifier run.

### 2. Copy Unmet Criteria

Copy the wording of the unmet acceptance checks so the follow-up can verify the
same outcome.

### 3. Update Tasks Based on Gaps

Name the file, test or behavior that needs to change for each unmet criterion.

### 4. Preserve Context

Carry forward the relevant scope and exclusions. Keep the follow-up focused on
the remaining work.

## Example: Complete Issue

```markdown
## Why

A maintainer using the branch-sync recovery link in `docs/agent-automation.md`
needs to reach the current operating procedure.

## Scope

Check the operator guide's branch-sync links and their regression test.

## Non-Goals

Leave workflow behavior and branch protection unchanged.

## Tasks

- [ ] Update the recovery link in `docs/agent-automation.md` to the Orchestrator Contract section in `docs/keepalive/Observability_Contract.md`.
- [ ] Check both branch-sync destinations in `tests/docs/test_archive_plans_index.py`.

## Acceptance Criteria

- [ ] `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -o addopts= -p no:cacheprovider tests/docs/test_archive_plans_index.py::test_operator_guide_links_current_branch_sync_recovery -q` exits 0.
- [ ] The recovery link in `docs/agent-automation.md` opens the Orchestrator Contract section.

## Implementation Notes

Keep the link to the Branch-Sync Gate section in `docs/keepalive/GoalsAndPlumbing.md`.
```

## Example: Verifier Follow-Up Issue

Replace the Source instructions with the links from the real verifier finding.

```markdown
## Source

Paste the original pull request, parent issue and verifier run links here.

## Why

The branch-sync recovery destination needs to reach the Orchestrator Contract
section.

## Scope

Repair the remaining recovery link in `docs/agent-automation.md`.

## Non-Goals

Leave the branch-sync gate and workflow behavior unchanged.

## Tasks

- [ ] Correct the fragment in `docs/agent-automation.md` to reach the Orchestrator Contract section in `docs/keepalive/Observability_Contract.md`.
- [ ] Run `test_operator_guide_links_current_branch_sync_recovery` in `tests/docs/test_archive_plans_index.py`.

## Acceptance Criteria

- [ ] `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -o addopts= -p no:cacheprovider tests/docs/test_archive_plans_index.py::test_operator_guide_links_current_branch_sync_recovery -q` exits 0.
- [ ] The recovery link in `docs/agent-automation.md` opens the Orchestrator Contract section.

## Implementation Notes

Check the rendered section link as well as the file path.
```

## Parsing Notes

Use the Markdown section headings shown above. From the repository root, check
the issue body with the validator before filing:

```sh
python .github/scripts/issue_format.py path/to/issue-body.md
```

Pass only the issue body to the validator, without the surrounding Markdown
fence used to display an example.
