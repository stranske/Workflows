# Output substrate v1

`output-substrate/v1` separates **regenerable view/data artifacts** from a
**vendored static renderer** so published HTML does not fuse presentation with
proprietary data. Validate against
[output-substrate-v1.schema.json](schemas/output-substrate-v1.schema.json) with a
Draft 2020-12 validator. `schema_version` is always `output-substrate/v1`.
Unknown additive fields are allowed for v1 extensions.

This contract generalizes the Pension-Data reference renderer without extracting
`apps/web/` (B2-029). The embryonic workspace-bundle shape is declared in
[`stranske/Pension-Data` `apps/contracts/runtime-contract.json`](https://github.com/stranske/Pension-Data/blob/main/apps/contracts/runtime-contract.json):
required top-level fields `contractVersion`, `data_origin`, and `datasets`;
allowed `data_origin` values `fixture`, `generated`, and `live`; dataset rows
with recommended provenance fields. Pension-Data enforces those constraints in
`tests/web/test_workspace_contract.py`.

## Renderer profiles

| `renderer_profile` | View bundle | Primary use |
| --- | --- | --- |
| `investment_review` | Workspace bundle (`workspace.json` pattern) | Pension fact review drilldowns, charts, and PWA shell |
| `blackline_bundle` | Blackline / diff snapshot bundle | Consultant and legal YoY blacklines (Doc-Lineage lane) |
| `mosaic_book` | Comms mosaic bundle | Manager-comms thesis monitor (`fund`, `periods`, `entries`, `themes`) |

Profiles select renderer wiring and the expected view-bundle vocabulary. They do
not change the wire shape of this document.

## Required fields

| Field | Requirement |
| --- | --- |
| `schema_version` | Must be the literal `output-substrate/v1`. |
| `renderer_profile` | One of `investment_review`, `blackline_bundle`, `mosaic_book`. |
| `workspace_bundle_ref` | Run-dir-relative POSIX pointer to the view bundle JSON (`path` required; `sha256` and `artifact_id` recommended). Rejects absolute paths, `..` traversal, backslashes, drive-letter roots (`C:`), and UNC paths (`//server/share`). |
| `manifest_ref` | Reference to the run's [`artifact-manifest/v1`](schemas/artifact-manifest-v1.schema.json) manifest. Named artifacts live there, not inline. |
| `manifest_csv_exports` | Array (possibly empty) of manifest-gated CSV export specs for Excel refresh. |

Optional `link_profile` selects evidence-link resolution: `local-file` for
synced-folder `file://` deep links (work-PC default) or `artifact-http` for
Pension-Data-style `artifactBaseUrl` resolution.

## Manifest CSV exports

Each `manifest_csv_exports[]` entry names a generated CSV file, its encoding
(`utf-8` or `utf-16-le`), and a nonempty `columns[]` list. Every column
requires `name`, `type` (`string`, `number`, `boolean`, or `date`), and
`source_path` (JSONPath or consumer-defined pointer into the workspace bundle).
Producers regenerate CSV files when the workspace bundle changes; Excel workbooks
refresh from the manifest-listed exports without embedding data in HTML.

## Manifest and delivery

`artifact-manifest/v1` adds `output_substrate` to its `kind` enum. A run may
publish this document as an artifact with `kind: "output_substrate"`. Existing
kinds and path/hash rules are unchanged.

The schema and this specification are distributed from the Workflows root via
`.github/sync-manifest.yml` (`source_tree: root`), matching the existing backplane
contract delivery.

## Consumer validation

Declare `output-substrate/v1` in an active consumer registry entry's `ingests`
list and pass one document to `scripts/validate_run_contract.py`. The production
validator enforces the schema, including POSIX path rules on
`workspace_bundle_ref.path` and `manifest_csv_exports[].filename`.

## Validation evidence

Synthetic fixture: `tests/fixtures/backplane/valid_output_substrate.json`.
Run `python -m pytest tests/contracts/test_backplane_schemas.py::test_output_substrate_fixture_validates -q`.

Deliberate break: remove `renderer_profile` from the fixture, rerun the named
test, observe failure, restore the fixture, and observe success.
