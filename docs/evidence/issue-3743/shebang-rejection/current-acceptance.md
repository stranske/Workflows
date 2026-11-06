# Current shebang-rejection acceptance

Historical receipts are `README.md`, `summary.json`, `proof.tar.gz`, `path-lookup/`, and `replay-validation/`.
Their input hashes describe earlier bytes and are not current acceptance.
Historical summary input rows that differ from the tree: 7.
Archive-internal copies in those historical receipts still match their own summaries.

Current acceptance is `acceptance-run/`, `validation-run/`, and `matched-comparison/`.
`raw-comparison-validation/` binds the current verifier and its regression tests; its literal command attempts returned 127 because the required interpreter is absent.
Current input bindings in those records match the files in this tree.
`main-acceptance-map.json` remains the pre-change inspection record.

## Actual interpreter paths

- Acceptance-run receipt interpreter: `/opt/anaconda3/bin/python3`
- Matched-comparison interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3`
- Validation Python: `/opt/anaconda3/bin/python3`
- Validation Black: `/opt/anaconda3/bin/black`
- Validation Ruff: `/opt/anaconda3/bin/ruff`

## Measured validation file counts

- Black files left unchanged: 928
- Focused Ruff paths: 15
- Workflow directory YAML files: 130
- Template workflow YAML files: 35
- Manifest workflow targets: 35
- Strict validation input files: 166

## Delivered archives

- historical `docs/evidence/issue-3743/shebang-rejection/proof.tar.gz`: 122 members, verified True
- historical `docs/evidence/issue-3743/shebang-rejection/path-lookup/proof.tar.gz`: 151 members, verified True
- historical `docs/evidence/issue-3743/shebang-rejection/replay-validation/proof.tar.gz`: 316 members, verified True
- current `docs/evidence/issue-3743/shebang-rejection/matched-comparison/proof.tar.gz`: 19 members, verified True
- current `docs/evidence/issue-3743/shebang-rejection/raw-comparison-validation/proof.tar.gz`: 37 members, verified True

## Matched comparison

Added passing nodes: 8. Removed nodes: 0. Changed old outcomes: 0. Universes identical: True. Exclusions: 0. Covered-line regressions: 0. Covered-branch regressions: 0.
