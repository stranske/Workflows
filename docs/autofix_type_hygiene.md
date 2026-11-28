# Automated Autofix & Type Hygiene Pipeline

The maintained autofix implementation is [Reusable Autofix](../.github/workflows/reusable-18-autofix.yml).
Use the [workflow system guide](ci/WORKFLOW_SYSTEM.md) and [tool version guide](ci/TOOL_VERSION_MANAGEMENT.md)
for its current inputs, execution and configuration.

## Result Labels & Status Comment

`autofix:clean` is a trigger, not an outcome label. Depending on the run,
the reusable workflow can report `autofix:applied`, `autofix:patch`,
`autofix:debt` or `autofix:clean-only`; consult the workflow and its summary
for the conditions and actual result.

The [earlier type-hygiene guide](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/autofix_type_hygiene.md) is retained
as historical context, including its old verification examples.
